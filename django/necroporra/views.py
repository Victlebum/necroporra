from datetime import timedelta, date
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User

from .models import (
    Pool, PoolMembership, Celebrity, PoolCelebrity, Prediction, MAX_POOL_MEMBERS,
    score_pool_celebrity, unscore_pool_celebrity,
)
from .forms import LoginForm, RegisterForm, CreatePoolForm, ChangePasswordForm
from . import wikidata_utils
from .serializers_utils import serialize_celebrity_payload, build_celebrity_display_fields


# ========== Django Template Views ==========

def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Invalid username or password')
    else:
        form = LoginForm()
    
    return render(request, 'necroporra/login.html', {'form': form})


def register_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Auto-login after registration
            login(request, user)
            messages.success(request, f'Welcome to Necroporra, {user.username}!')
            return redirect('dashboard')
    else:
        form = RegisterForm()
    
    return render(request, 'necroporra/register.html', {'form': form})


def logout_view(request):
    """Handle user logout."""
    if request.method == 'POST':
        auth_logout(request)
        messages.info(request, 'You have been logged out.')
        return redirect('login')
    return redirect('dashboard')


@login_required
def dashboard_view(request):
    """Display user's pools and join pool functionality."""
    pools = Pool.objects.filter(memberships__user=request.user)
    
    # Annotate with member count
    pools_data = []
    for pool in pools:
        pools_data.append({
            'pool': pool,
            'member_count': pool.memberships.count()
        })
    
    return render(request, 'necroporra/dashboard.html', {
        'pools': pools_data
    })


@login_required
def create_pool_view(request):
    """Handle pool creation."""
    if request.method == 'POST':
        form = CreatePoolForm(request.POST)
        if form.is_valid():
            pool = form.save(commit=False)
            pool.creator = request.user
            pool.slug = Pool.generate_slug()
            now = timezone.now()
            
            # Calculate limit_date based on timeframe_choice
            pool.limit_date = Pool.calculate_limit_date(
                pool.timeframe_choice,
                now
            )
            
            # New pools start unlocked, then lock after N days.
            lock_after_days = form.cleaned_data.get('lock_after_days')
            pool.is_locked = False
            pool.lock_after_days = lock_after_days
            pool.lock_date = now + timedelta(days=lock_after_days)
            
            pool.admin = request.user
            pool.save()
            
            # Add creator as first member
            PoolMembership.objects.create(pool=pool, user=request.user)
            
            messages.success(request, f'Pool "{pool.name}" created successfully!')
            return redirect('pool_detail', slug=pool.slug)
    else:
        form = CreatePoolForm()
    
    return render(request, 'necroporra/create_pool.html', {'form': form})


@login_required
def pool_detail_view(request, slug):
    """Display pool details, leaderboard, and predictions."""
    pool = get_object_or_404(Pool, slug=slug)
    
    # Check if user is a member
    is_member = pool.memberships.filter(user=request.user).exists()
    
    # Access control for private pools
    if not pool.is_public and not is_member:
        messages.error(request, 'This is a private pool. You need an invitation to join.')
        return redirect('dashboard')
    
    if not is_member:
        messages.warning(request, 'You are not a member of this pool.')
        return redirect('dashboard')
    
    # Check if pool is active
    is_active = pool.is_pool_active()
    days_remaining = pool.days_remaining()
    
    # Get leaderboard (ordered by total_points for distributed, wins for simple)
    if pool.scoring_mode == 'distributed':
        leaderboard = pool.memberships.all().order_by('-total_points', '-wins')
    else:
        leaderboard = pool.memberships.all().order_by('-wins')
    
    # Determine what predictions to show based on lock state.
    if pool.picks_publicly_visible():
        # Locked pools show all predictions.
        all_predictions = Prediction.objects.filter(pool=pool).select_related('celebrity', 'user')
    else:
        # Unlocked pools hide other members' predictions.
        all_predictions = Prediction.objects.filter(pool=pool, user=request.user).select_related('celebrity')
    
    # Get user's predictions
    user_predictions = Prediction.objects.filter(pool=pool, user=request.user).select_related('celebrity')

    # Attach display metadata using shared serializer helpers.
    for prediction in user_predictions:
        display_fields = build_celebrity_display_fields(
            prediction.celebrity.birth_date,
            prediction.celebrity.death_date,
            locale=getattr(request, 'LANGUAGE_CODE', 'en'),
        )
        prediction.celebrity_subtitle_display = display_fields['subtitle_display']
    
    # Calculate user's prediction count and remaining
    user_prediction_count = user_predictions.count()
    remaining_predictions = pool.max_predictions_per_user - user_prediction_count
    
    # Calculate total weight used (for distributed scoring)
    total_weight_used = 0
    remaining_weight = 10
    if pool.scoring_mode == 'distributed':
        total_weight_used = user_predictions.aggregate(total=Sum('weight'))['total'] or 0
        remaining_weight = 10 - total_weight_used
    
    # Get pool statistics
    stats = {
        'member_count': pool.memberships.count(),
        'celebrity_count': pool.celebrities.count(),
        'prediction_count': pool.predictions.count(),
    }
    
    return render(request, 'necroporra/pool_detail.html', {
        'pool': pool,
        'leaderboard': leaderboard,
        'predictions': all_predictions,
        'user_predictions': user_predictions,
        'stats': stats,
        'is_active': is_active,
        'days_remaining': days_remaining,
        'user_prediction_count': user_prediction_count,
        'remaining_predictions': remaining_predictions,
        'total_weight_used': total_weight_used,
        'remaining_weight': remaining_weight,
    })


def index(request):
    """Redirect to dashboard if authenticated, otherwise to login."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


# ========== API Views (for AJAX interactions) ==========


@require_http_methods(["POST"])
@login_required
def join_pool_api(request, slug):
    """Join a pool using its slug."""
    pool = get_object_or_404(Pool, slug=slug)
    
    # Check if pool is active
    if not pool.is_pool_active():
        return JsonResponse(
            {'detail': 'This pool has ended and is no longer accepting new members'},
            status=400
        )

    # Check member cap
    if pool.memberships.count() >= MAX_POOL_MEMBERS:
        return JsonResponse(
            {'detail': f'This pool has reached its maximum capacity of {MAX_POOL_MEMBERS} members.'},
            status=400
        )

    membership, created = PoolMembership.objects.get_or_create(
        pool=pool,
        user=request.user
    )
    if created:
        return JsonResponse(
            {
                'id': membership.id,
                'user': {
                    'id': request.user.id,
                    'username': request.user.username,
                },
                'joined_at': membership.joined_at.isoformat(),
                'wins': membership.wins,
                'total_points': membership.total_points,
            },
            status=201
        )
    return JsonResponse(
        {'detail': 'Already a member of this pool'},
        status=400
    )


@require_http_methods(["POST"])
@login_required
def add_celebrity_to_pool_api(request, slug):
    """Add a celebrity to the pool and create a prediction."""
    pool = get_object_or_404(Pool, slug=slug)
    
    # Parse JSON body
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON'}, status=400)
    
    # Check if pool is active
    if not pool.is_pool_active():
        return JsonResponse(
            {'detail': 'This pool has ended and is no longer accepting predictions'},
            status=400
        )

    if pool.is_locked:
        return JsonResponse(
            {'detail': 'This pool is locked. You can no longer add predictions.'},
            status=400
        )
    
    # Check if user is pool member
    if not pool.memberships.filter(user=request.user).exists():
        return JsonResponse(
            {'detail': 'You are not a member of this pool'},
            status=403
        )
    
    # Check prediction limit
    user_prediction_count = Prediction.objects.filter(
        pool=pool,
        user=request.user
    ).count()
    
    if user_prediction_count >= pool.max_predictions_per_user:
        return JsonResponse(
            {'detail': f'You have reached the maximum of {pool.max_predictions_per_user} predictions for this pool'},
            status=400
        )

    celebrity_id = data.get('celebrity_id')
    wikidata_id = data.get('wikidata_id')

    # In distributed pools, weight is required and must be valid.
    is_distributed = pool.scoring_mode == 'distributed'
    if is_distributed and 'weight' not in data:
        return JsonResponse(
            {'detail': 'Weight is required for distributed scoring pools'},
            status=400
        )

    raw_weight = data.get('weight', 1)

    # Validate weight
    try:
        weight = int(raw_weight)
    except (ValueError, TypeError):
        if is_distributed:
            return JsonResponse(
                {'detail': 'Weight must be a valid integer between 1 and 10'},
                status=400
            )
        weight = 1

    if weight < 1 or weight > 10:
        return JsonResponse(
            {'detail': 'Weight must be between 1 and 10'},
            status=400
        )
    
    # Check total weight for distributed scoring
    if is_distributed:
        total_weight = Prediction.objects.filter(
            pool=pool,
            user=request.user
        ).aggregate(total=Sum('weight'))['total'] or 0
        
        if total_weight + weight > 10:
            return JsonResponse(
                {'detail': f'Total weight cannot exceed 10. Current: {total_weight}, attempting to add: {weight}'},
                status=400
            )
    
    # Must provide either celebrity_id or wikidata_id
    if not celebrity_id and not wikidata_id:
        return JsonResponse(
            {'detail': 'celebrity_id or wikidata_id is required'},
            status=400
        )
    
    # If wikidata_id provided, fetch from Wikidata and create in database
    if wikidata_id:
        # Check if celebrity already exists with this wikidata_id
        celebrity = Celebrity.objects.filter(wikidata_id=wikidata_id).first()
        
        if not celebrity:
            # Fetch from Wikidata
            entity_data = wikidata_utils.get_wikidata_entity(wikidata_id)
            
            if not entity_data:
                return JsonResponse(
                    {'detail': 'Could not fetch celebrity data from Wikidata'},
                    status=400
                )
            
            # Create new celebrity in database
            celebrity = Celebrity.objects.create(
                name=entity_data['name'],
                bio=entity_data['bio'],
                birth_date=entity_data['birth_date'],
                death_date=entity_data['death_date'],
                wikidata_id=entity_data['wikidata_id'],
                image_url=entity_data['image_url']
            )
    else:
        # Use existing celebrity from database
        celebrity = get_object_or_404(Celebrity, id=celebrity_id)
    
    # Reject deceased celebrities
    if celebrity.death_date:
        return JsonResponse(
            {'detail': 'This celebrity is already deceased and cannot be picked.'},
            status=400
        )

    # Add celebrity to pool
    pool_celebrity, _ = PoolCelebrity.objects.get_or_create(
        pool=pool,
        celebrity=celebrity,
        defaults={'added_by': request.user}
    )
    
    # Create prediction with weight
    prediction, created = Prediction.objects.get_or_create(
        pool=pool,
        celebrity=celebrity,
        user=request.user,
        defaults={'weight': weight}
    )
    
    if not created:
        return JsonResponse(
            {'detail': 'You have already predicted this celebrity'},
            status=400
        )
    
    # Calculate remaining predictions and weight
    remaining_predictions = pool.max_predictions_per_user - user_prediction_count - 1
    remaining_weight = 10
    if pool.scoring_mode == 'distributed':
        total_weight = Prediction.objects.filter(
            pool=pool,
            user=request.user
        ).aggregate(total=Sum('weight'))['total'] or 0
        remaining_weight = 10 - total_weight
    
    # Build response
    response_data = {
        'id': pool_celebrity.id,
        'celebrity': serialize_celebrity_payload(
            celebrity,
            locale=getattr(request, 'LANGUAGE_CODE', 'en'),
        ),
        'added_by': {
            'id': request.user.id,
            'username': request.user.username,
        },
        'added_at': pool_celebrity.added_at.isoformat(),
        'is_death_recorded': pool_celebrity.is_death_recorded,
        'remaining_predictions': remaining_predictions,
        'remaining_weight': remaining_weight,
    }
    
    return JsonResponse(response_data, status=201)


@require_http_methods(["GET"])
@login_required
def get_user_picks_api(request, slug):
    """Get a specific user's picks for a pool."""
    pool = get_object_or_404(Pool, slug=slug)
    
    # Get user_id from query parameters
    user_id = request.GET.get('user_id')
    if not user_id:
        return JsonResponse(
            {'detail': 'user_id query parameter is required'},
            status=400
        )
    
    # Check if user is a member of this pool
    if not pool.memberships.filter(user=request.user).exists():
        return JsonResponse(
            {'detail': 'You are not a member of this pool'},
            status=403
        )
    
    # Check if picks are visible (only when locked).
    if not pool.picks_publicly_visible():
        return JsonResponse(
            {'detail': 'Picks are not visible until this pool locks.'},
            status=403
        )
    
    # Get the target user
    target_user = get_object_or_404(User, id=user_id)
    
    # Check if target user is a member of this pool
    membership = pool.memberships.filter(user=target_user).first()
    if not membership:
        return JsonResponse(
            {'detail': 'User is not a member of this pool'},
            status=404
        )
    
    # Get predictions for this user in this pool
    predictions = Prediction.objects.filter(
        pool=pool,
        user=target_user
    ).select_related('celebrity').order_by('-weight', 'celebrity__name')
    
    # Build predictions data manually
    predictions_data = []
    for pred in predictions:
        predictions_data.append({
            'id': pred.id,
            'celebrity': serialize_celebrity_payload(
                pred.celebrity,
                locale=getattr(request, 'LANGUAGE_CODE', 'en'),
            ),
            'created_at': pred.created_at.isoformat(),
            'is_correct': pred.is_correct,
            'weight': pred.weight,
            'points_earned': pred.points_earned,
        })
    
    # Return user info along with predictions
    return JsonResponse({
        'user': {
            'id': target_user.id,
            'username': target_user.username,
        },
        'membership': {
            'wins': membership.wins,
            'total_points': membership.total_points,
        },
        'predictions': predictions_data,
        'prediction_count': predictions.count(),
    })


@require_http_methods(["DELETE"])
@login_required
def delete_prediction_api(request, slug, prediction_id):
    """Delete a user's own prediction from a pool."""
    pool = get_object_or_404(Pool, slug=slug)

    if pool.is_locked:
        return JsonResponse(
            {'detail': 'This pool is locked. You can no longer edit predictions.'},
            status=400
        )

    prediction = get_object_or_404(Prediction, id=prediction_id, pool=pool, user=request.user)

    celebrity = prediction.celebrity
    weight_refund = prediction.weight

    # If the prediction was scored correct, reverse it from the membership totals
    if prediction.is_correct is True:
        try:
            membership = PoolMembership.objects.get(pool=pool, user=request.user)
            if prediction.points_earned:
                membership.total_points = max(0, membership.total_points - prediction.points_earned)
            membership.wins = max(0, membership.wins - 1)
            membership.save()
        except PoolMembership.DoesNotExist:
            pass

    prediction.delete()

    # Clean up PoolCelebrity if no other predictions exist for this celebrity in this pool
    if not Prediction.objects.filter(pool=pool, celebrity=celebrity).exists():
        PoolCelebrity.objects.filter(pool=pool, celebrity=celebrity).delete()

    # Recalculate remaining predictions and weight
    user_predictions = Prediction.objects.filter(pool=pool, user=request.user)
    remaining_predictions = pool.max_predictions_per_user - user_predictions.count()
    remaining_weight = 10
    if pool.scoring_mode == 'distributed':
        total_weight_used = user_predictions.aggregate(total=Sum('weight'))['total'] or 0
        remaining_weight = 10 - total_weight_used

    return JsonResponse({
        'success': True,
        'remaining_predictions': remaining_predictions,
        'remaining_weight': remaining_weight,
        'weight_refunded': weight_refund,
    })


@require_http_methods(["GET"])
@login_required
def search_wikidata_api(request):
    """Search for celebrities on Wikidata by name."""
    query = request.GET.get('q', '')
    if not query or len(query) < 2:
        return JsonResponse(
            {'detail': 'Query must be at least 2 characters'},
            status=400
        )
    
    # Search Wikidata for people
    results = wikidata_utils.search_wikidata_people(query, limit=20)

    # Normalize with shared serializer contract for consistent frontend rendering.
    serialized_results = [
        serialize_celebrity_payload(result, locale=getattr(request, 'LANGUAGE_CODE', 'en'))
        for result in results
    ]
    
    # Return results (safe=False because results is a list)
    return JsonResponse(serialized_results, safe=False)


# ========== Pool Admin Panel ==========


@login_required
def pool_admin_view(request, slug):
    """Display the admin panel for a pool (accessible only by the pool admin)."""
    pool = get_object_or_404(Pool, slug=slug)

    if request.user != pool.admin:
        messages.error(request, 'You do not have admin rights for this pool.')
        return redirect('pool_detail', slug=slug)

    memberships = pool.memberships.select_related('user').order_by('-total_points', '-wins')
    pool_celebrities = pool.celebrities.select_related('celebrity').order_by('celebrity__name')

    return render(request, 'necroporra/pool_admin.html', {
        'pool': pool,
        'memberships': memberships,
        'pool_celebrities': pool_celebrities,
    })


@require_http_methods(["POST"])
@login_required
def mark_celebrity_dead_api(request, slug):
    """Manually mark (or unmark) a celebrity as dead within a specific pool (admin only)."""
    pool = get_object_or_404(Pool, slug=slug)

    if request.user != pool.admin:
        return JsonResponse({'detail': 'You are not the admin of this pool.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)

    celebrity_id = data.get('celebrity_id')
    action = data.get('action')  # 'mark' or 'unmark'

    if not celebrity_id or action not in ('mark', 'unmark'):
        return JsonResponse({'detail': 'celebrity_id and action ("mark" or "unmark") are required.'}, status=400)

    pool_celebrity = PoolCelebrity.objects.filter(pool=pool, celebrity_id=celebrity_id).select_related('celebrity').first()
    if not pool_celebrity:
        return JsonResponse({'detail': 'Celebrity is not in this pool.'}, status=404)

    celebrity = pool_celebrity.celebrity

    if action == 'mark':
        # Cannot manually mark if Wikidata already has a death date
        if celebrity.death_date:
            return JsonResponse(
                {'detail': 'This celebrity already has a Wikidata death date and cannot be manually overridden.'},
                status=400,
            )
        if pool_celebrity.manual_death_date:
            return JsonResponse({'detail': 'Celebrity is already manually marked as dead.'}, status=400)

        pool_celebrity.manual_death_date = date.today()
        pool_celebrity.save(update_fields=['manual_death_date'])
        score_pool_celebrity(pool_celebrity)

        return JsonResponse({
            'detail': f'{celebrity.name} has been marked as dead in this pool.',
            'manual_death_date': str(pool_celebrity.manual_death_date),
        })

    else:  # action == 'unmark'
        if not pool_celebrity.manual_death_date:
            return JsonResponse({'detail': 'Celebrity has no manual death date to remove.'}, status=400)
        if celebrity.death_date:
            return JsonResponse(
                {'detail': 'Cannot unmark: this celebrity has a Wikidata death date that takes precedence.'},
                status=400,
            )

        unscore_pool_celebrity(pool_celebrity)
        pool_celebrity.manual_death_date = None
        pool_celebrity.save(update_fields=['manual_death_date'])

        return JsonResponse({'detail': f'{celebrity.name} death has been unmarked in this pool.'})


@require_http_methods(["POST"])
@login_required
def transfer_admin_api(request, slug):
    """Transfer pool admin rights to another member."""
    pool = get_object_or_404(Pool, slug=slug)

    if request.user != pool.admin:
        return JsonResponse({'detail': 'You are not the admin of this pool.'}, status=403)

    try:
        data = json.loads(request.body)
        user_id = int(data.get('user_id', 0))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'detail': 'Invalid request body.'}, status=400)

    if user_id == request.user.id:
        return JsonResponse({'detail': 'You are already the admin.'}, status=400)

    if not pool.memberships.filter(user_id=user_id).exists():
        return JsonResponse({'detail': 'That user is not a member of this pool.'}, status=400)

    new_admin = get_object_or_404(User, id=user_id)
    pool.admin = new_admin
    pool.save(update_fields=['admin'])

    return JsonResponse({
        'detail': f'{new_admin.username} is now the admin.',
        'new_admin_id': new_admin.id,
        'new_admin_username': new_admin.username,
    })


@require_http_methods(["POST"])
@login_required
def remove_member_api(request, slug):
    """Remove a member from the pool (admin only). Also deletes their predictions."""
    pool = get_object_or_404(Pool, slug=slug)

    if request.user != pool.admin:
        return JsonResponse({'detail': 'You are not the admin of this pool.'}, status=403)

    try:
        data = json.loads(request.body)
        user_id = int(data.get('user_id', 0))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'detail': 'Invalid request body.'}, status=400)

    if user_id == request.user.id:
        return JsonResponse({'detail': 'You cannot remove yourself. Transfer admin first.'}, status=400)

    membership = pool.memberships.filter(user_id=user_id).first()
    if not membership:
        return JsonResponse({'detail': 'That user is not a member of this pool.'}, status=400)

    # Delete predictions first, then membership
    Prediction.objects.filter(pool=pool, user_id=user_id).delete()
    membership.delete()

    # Clean up orphaned PoolCelebrities (celebrities with no remaining predictions in this pool)
    orphaned = PoolCelebrity.objects.filter(pool=pool).exclude(
        celebrity__in=Prediction.objects.filter(pool=pool).values('celebrity')
    )
    orphaned.delete()

    return JsonResponse({'detail': 'Member removed successfully.'})


@require_http_methods(["POST"])
@login_required
def delete_pool_api(request, slug):
    """Delete the pool entirely (admin only)."""
    pool = get_object_or_404(Pool, slug=slug)

    if request.user != pool.admin:
        return JsonResponse({'detail': 'You are not the admin of this pool.'}, status=403)

    pool.delete()

    return JsonResponse({'detail': 'Pool deleted.', 'redirect': '/dashboard/'})


@require_http_methods(["POST"])
@login_required
def lock_pool_api(request, slug):
    """Lock a pool immediately (admin only)."""
    pool = get_object_or_404(Pool, slug=slug)

    if request.user != pool.admin:
        return JsonResponse({'detail': 'You are not the admin of this pool.'}, status=403)

    if pool.is_locked:
        return JsonResponse({'detail': 'Pool is already locked.'}, status=400)

    pool.is_locked = True
    pool.lock_date = timezone.now()
    pool.save(update_fields=['is_locked', 'lock_date'])

    return JsonResponse({'detail': 'Pool locked. Picks are now visible and prediction edits are closed.'})


# ========== User Settings ==========


@login_required
def user_settings_view(request):
    """Display user settings page: pool memberships, password change, account deletion."""
    memberships = (
        PoolMembership.objects.filter(user=request.user)
        .select_related('pool', 'pool__admin')
        .annotate(member_count=Count('pool__memberships'))
        .order_by('pool__name')
    )

    form = ChangePasswordForm(user=request.user)

    return render(request, 'necroporra/settings.html', {
        'memberships': memberships,
        'password_form': form,
    })


@require_http_methods(["POST"])
@login_required
def change_password_view(request):
    """Handle password change form submission."""
    form = ChangePasswordForm(user=request.user, data=request.POST)

    if form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, 'Your password has been changed.')
        return redirect('user_settings')

    # Re-query memberships for the template context on form error
    memberships = (
        PoolMembership.objects.filter(user=request.user)
        .select_related('pool', 'pool__admin')
        .annotate(member_count=Count('pool__memberships'))
        .order_by('pool__name')
    )

    return render(request, 'necroporra/settings.html', {
        'memberships': memberships,
        'password_form': form,
    })


@require_http_methods(["POST"])
@login_required
def leave_pool_api(request):
    """Leave a pool. If the user is the pool admin, the pool is deleted entirely."""
    try:
        data = json.loads(request.body)
        pool_id = int(data.get('pool_id', 0))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'detail': 'Invalid request body.'}, status=400)

    pool = get_object_or_404(Pool, id=pool_id)

    if not pool.memberships.filter(user=request.user).exists():
        return JsonResponse({'detail': 'You are not a member of this pool.'}, status=400)

    if pool.admin == request.user:
        pool_name = pool.name
        pool.delete()
        return JsonResponse({'detail': f'Pool "{pool_name}" has been deleted.'})

    # Regular member: remove predictions, membership, and orphaned pool celebrities
    Prediction.objects.filter(pool=pool, user=request.user).delete()
    PoolMembership.objects.filter(pool=pool, user=request.user).delete()

    # Clean up orphaned PoolCelebrities
    orphaned = PoolCelebrity.objects.filter(pool=pool).exclude(
        celebrity__in=Prediction.objects.filter(pool=pool).values('celebrity')
    )
    orphaned.delete()

    return JsonResponse({'detail': f'You have left "{pool.name}".'})


@require_http_methods(["POST"])
@login_required
def delete_account_api(request):
    """Permanently delete the authenticated user's account."""
    user = request.user
    auth_logout(request)
    user.delete()
    return JsonResponse({'detail': 'Account deleted.', 'redirect': '/login/'})
