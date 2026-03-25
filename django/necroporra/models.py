import secrets
import string
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db import models, transaction
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


MAX_POOL_MEMBERS = 20
INVITATION_EXPIRATION_DAYS = 7


def get_default_timeframe():
    """Return 'end_of_next_year' if current month is November or December, otherwise 'end_of_year'."""
    current_month = timezone.now().month
    if current_month in (11, 12):
        return 'end_of_next_year'
    return 'end_of_year'


class Pool(models.Model):
    """A dead pool where users make predictions about celebrities."""
    
    TIMEFRAME_CHOICES = [
        ('end_of_year', 'End of current year'),
        ('end_of_next_year', 'End of next year'),
        ('1_month', '1 month from now'),
        ('3_months', '3 months from now'),
        ('6_months', '6 months from now'),
        ('1_year', '1 year from now'),
    ]
    
    SCORING_MODES = [
        ('simple', 'Simple - 1 point per correct prediction'),
        ('distributed', 'Distributed - Allocate 10 points across predictions'),
    ]
    
    creator = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pools_created',
        help_text="The user who originally created the pool."
    )
    admin = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='pools_administered',
        help_text="The current admin of the pool. Deleting this user deletes the pool."
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(
        max_length=5,
        unique=True,
        validators=[RegexValidator(r'^[a-zA-Z0-9]{5}$', 'Slug must be exactly 5 alphanumeric characters')]
    )
    
    # Timeframe and limit date
    timeframe_choice = models.CharField(
        max_length=20,
        choices=TIMEFRAME_CHOICES,
        default=get_default_timeframe,
        help_text="When the pool will end"
    )
    limit_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date when the pool becomes inactive"
    )
    
    # Access control
    is_public = models.BooleanField(
        default=True,
        help_text="Public pools can be discovered by slug code; private pools require a valid invitation link"
    )
    allow_member_invite_links = models.BooleanField(
        default=True,
        help_text="For private pools, allow non-admin members to copy invitation links"
    )
    
    # Prediction limits
    max_predictions_per_user = models.IntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Maximum number of predictions each user can make"
    )
    
    # Pool lock settings
    is_locked = models.BooleanField(
        default=False,
        help_text="Whether this pool is locked (picks are visible and predictions are frozen)"
    )
    lock_after_days = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        help_text="Days after pool creation when the pool locks (1-7)"
    )
    lock_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date when the pool will lock"
    )
    
    # Scoring mode
    scoring_mode = models.CharField(
        max_length=20,
        choices=SCORING_MODES,
        default='simple',
        help_text="How points are calculated for correct predictions"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @staticmethod
    def generate_slug():
        """Generate a unique 5-character alphanumeric slug."""
        chars = string.ascii_letters + string.digits
        while True:
            slug = ''.join(secrets.choice(chars) for _ in range(5))
            if not Pool.objects.filter(slug=slug).exists():
                return slug
    
    @staticmethod
    def calculate_limit_date(timeframe_choice, start_date):
        """Calculate the limit date based on the timeframe choice."""
        if timeframe_choice == '1_month':
            return start_date + relativedelta(months=1)
        elif timeframe_choice == '3_months':
            return start_date + relativedelta(months=3)
        elif timeframe_choice == '6_months':
            return start_date + relativedelta(months=6)
        elif timeframe_choice == '1_year':
            return start_date + relativedelta(years=1)
        elif timeframe_choice == 'end_of_year':
            return timezone.datetime(start_date.year, 12, 31, 23, 59, 59, tzinfo=start_date.tzinfo)
        elif timeframe_choice == 'end_of_next_year':
            return timezone.datetime(start_date.year + 1, 12, 31, 23, 59, 59, tzinfo=start_date.tzinfo)
        else:
            # Default to 1 year
            return start_date + relativedelta(years=1)
    
    def calculate_lock_date(self):
        """Calculate when the pool should lock."""
        if self.is_locked or self.lock_after_days is None:
            return None
        return self.created_at + timedelta(days=self.lock_after_days)

    def picks_publicly_visible(self):
        """Picks are visible to all members only after the pool locks."""
        return self.is_locked

    def predictions_editable(self):
        """Predictions can only be edited while the pool is unlocked."""
        return not self.is_locked
    
    def is_pool_active(self):
        """Check if the pool is still active based on limit_date."""
        if not self.limit_date:
            return True  # During migration, assume active
        return timezone.now() < self.limit_date
    
    def days_remaining(self):
        """Calculate days remaining until limit_date."""
        if not self.limit_date or not self.is_pool_active():
            return 0
        delta = self.limit_date - timezone.now()
        return max(0, delta.days)

    def get_active_invitation(self):
        """Return the currently active invitation, if any."""
        return self.invitations.filter(is_active=True).order_by('-created_at').first()

    def ensure_active_invitation(self, created_by=None):
        """Ensure there is a currently valid active invitation for this pool."""
        invitation = self.get_active_invitation()
        if invitation and invitation.is_valid():
            return invitation
        return PoolInvitation.issue_for_pool(self, created_by=created_by)


class PoolInvitation(models.Model):
    """Invitation tokens used to access browser join links for a pool."""

    pool = models.ForeignKey(Pool, on_delete=models.CASCADE, related_name='invitations')
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='pool_invitations_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['pool'],
                condition=Q(is_active=True),
                name='unique_active_invitation_per_pool',
            ),
        ]

    def __str__(self):
        return f"Invitation for {self.pool.slug} ({'active' if self.is_active else 'inactive'})"

    @staticmethod
    def generate_token(length=32):
        """Generate a unique URL-safe invitation token."""
        alphabet = string.ascii_letters + string.digits
        while True:
            token = ''.join(secrets.choice(alphabet) for _ in range(length))
            if not PoolInvitation.objects.filter(token=token).exists():
                return token

    def is_valid(self):
        """Return whether this invitation can still be used."""
        return self.is_active and timezone.now() < self.expires_at

    @classmethod
    def issue_for_pool(cls, pool, created_by=None):
        """Create a new active invitation and deactivate previous active ones."""
        with transaction.atomic():
            cls.objects.filter(pool=pool, is_active=True).update(is_active=False)
            return cls.objects.create(
                pool=pool,
                token=cls.generate_token(),
                created_by=created_by,
                expires_at=timezone.now() + timedelta(days=INVITATION_EXPIRATION_DAYS),
                is_active=True,
            )


class PoolMembership(models.Model):
    """Tracks users in pools and their scores."""
    pool = models.ForeignKey(Pool, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pool_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    wins = models.IntegerField(default=0, help_text="Number of correct predictions (for simple mode)")
    total_points = models.IntegerField(default=0, help_text="Total points earned (for distributed mode)")

    class Meta:
        unique_together = ['pool', 'user']
        ordering = ['-total_points', '-wins']

    def __str__(self):
        return f"{self.user.username} in {self.pool.name}"


class Celebrity(models.Model):
    """A celebrity that can be added to pools."""
    name = models.CharField(max_length=255)
    bio = models.TextField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    death_date = models.DateField(null=True, blank=True)
    wikidata_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    image_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def is_deceased(self):
        """Check if celebrity has a recorded death date."""
        return self.death_date is not None


class PoolCelebrity(models.Model):
    """Links celebrities to specific pools."""
    pool = models.ForeignKey(Pool, on_delete=models.CASCADE, related_name='celebrities')
    celebrity = models.ForeignKey(Celebrity, on_delete=models.CASCADE, related_name='pool_lists')
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    added_at = models.DateTimeField(auto_now_add=True)
    is_death_recorded = models.BooleanField(default=False, help_text="Has this celebrity's death been recorded?")
    manual_death_date = models.DateField(
        null=True,
        blank=True,
        help_text="Death date manually set by the pool admin. Ignored once Celebrity.death_date is set by Wikidata."
    )

    class Meta:
        unique_together = ['pool', 'celebrity']

    def __str__(self):
        return f"{self.celebrity.name} in {self.pool.name}"

    @property
    def effective_death_date(self):
        """The death date used for scoring. Wikidata global date always takes precedence."""
        return self.celebrity.death_date or self.manual_death_date

    @property
    def is_manually_marked_dead(self):
        """True only when the admin set a manual date AND Wikidata has not confirmed a death."""
        return self.manual_death_date is not None and self.celebrity.death_date is None


class Prediction(models.Model):
    """A user's prediction about a celebrity dying within a pool's timeframe."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='predictions')
    pool = models.ForeignKey(Pool, on_delete=models.CASCADE, related_name='predictions')
    celebrity = models.ForeignKey(Celebrity, on_delete=models.CASCADE, related_name='predictions')
    created_at = models.DateTimeField(auto_now_add=True)
    is_correct = models.BooleanField(null=True, help_text="None=undecided, True=correct, False=wrong")
    weight = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Weight assigned to this prediction (for distributed scoring)"
    )
    points_earned = models.IntegerField(
        null=True,
        blank=True,
        help_text="Points earned from this prediction after scoring"
    )

    class Meta:
        unique_together = ['user', 'pool', 'celebrity']
        ordering = ['-created_at']

    def __str__(self):
        status = "✓" if self.is_correct is True else ("✗" if self.is_correct is False else "?")
        return f"{self.user.username} predicts {self.celebrity.name} {status}"

    def clean(self):
        """Validate prediction constraints."""
        super().clean()

        # Check if pool is active
        if self.pool and not self.pool.is_pool_active():
            raise ValidationError("Cannot create predictions for an inactive pool.")

        # Check max predictions per user
        if self.pool and self.user:
            existing_predictions = Prediction.objects.filter(
                pool=self.pool,
                user=self.user
            ).exclude(pk=self.pk).count()

            if existing_predictions >= self.pool.max_predictions_per_user:
                raise ValidationError(
                    f"Maximum {self.pool.max_predictions_per_user} predictions allowed per user."
                )

        # For distributed scoring, check total weight budget
        if self.pool and self.pool.scoring_mode == 'distributed' and self.user:
            total_weight = Prediction.objects.filter(
                pool=self.pool,
                user=self.user
            ).exclude(pk=self.pk).aggregate(
                total=models.Sum('weight')
            )['total'] or 0

            if total_weight + self.weight > 10:
                raise ValidationError(
                    f"Total weight cannot exceed 10. Current: {total_weight}, attempting to add: {self.weight}"
                )


# ========== Pool-level scoring helpers ==========


def score_pool_celebrity(pool_celebrity):
    """
    Mark pending predictions for a celebrity in a pool as correct/incorrect
    based on their effective_death_date, and update member scores.
    """
    effective_date = pool_celebrity.effective_death_date
    if not effective_date:
        return

    pool = pool_celebrity.pool
    celebrity = pool_celebrity.celebrity

    predictions = Prediction.objects.filter(
        pool=pool,
        celebrity=celebrity,
        is_correct__isnull=True,
    )

    for prediction in predictions:
        if effective_date <= pool.limit_date.date():
            prediction.is_correct = True
            points = 1 if pool.scoring_mode == 'simple' else prediction.weight
            prediction.points_earned = points
            prediction.save()

            membership = PoolMembership.objects.get(pool=pool, user=prediction.user)
            membership.wins += 1
            membership.total_points += points
            membership.save()
        else:
            prediction.is_correct = False
            prediction.points_earned = 0
            prediction.save()


def unscore_pool_celebrity(pool_celebrity):
    """
    Reverse all scoring for a celebrity in a pool, resetting predictions to pending
    and subtracting previously earned wins/points from memberships.
    """
    pool = pool_celebrity.pool
    celebrity = pool_celebrity.celebrity

    predictions = Prediction.objects.filter(
        pool=pool,
        celebrity=celebrity,
    ).exclude(is_correct__isnull=True)

    for prediction in predictions:
        if prediction.is_correct is True and prediction.points_earned is not None:
            membership = PoolMembership.objects.filter(pool=pool, user=prediction.user).first()
            if membership:
                membership.wins = max(0, membership.wins - 1)
                membership.total_points = max(0, membership.total_points - prediction.points_earned)
                membership.save()

        prediction.is_correct = None
        prediction.points_earned = None
        prediction.save()
