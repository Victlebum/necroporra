"""
Comprehensive tests for necroporra.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import json

from .models import Pool, PoolInvitation, PoolMembership, Celebrity, PoolCelebrity, Prediction, MAX_POOL_MEMBERS
from .forms import CreatePoolForm, RegisterForm
from . import wikidata_utils


class PoolModelTest(TestCase):
    """Test Pool model functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
    
    def test_pool_creation(self):
        """Test creating a basic pool."""
        pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Test Pool',
            slug='ABCDE',
            timeframe_choice='1_year',
            limit_date=timezone.now() + timedelta(days=365)
        )
        self.assertEqual(pool.name, 'Test Pool')
        self.assertTrue(pool.is_pool_active())
    
    def test_generate_unique_slug(self):
        """Test slug generation creates unique 5-char codes."""
        slug1 = Pool.generate_slug()
        slug2 = Pool.generate_slug()
        
        self.assertEqual(len(slug1), 5)
        self.assertEqual(len(slug2), 5)
        self.assertNotEqual(slug1, slug2)
    
    def test_calculate_limit_date(self):
        """Test limit date calculation for different timeframes."""
        start = timezone.now()
        
        # Test 1 month
        limit = Pool.calculate_limit_date('1_month', start)
        self.assertGreater(limit, start)
        
        # Test 1 year
        limit = Pool.calculate_limit_date('1_year', start)
        self.assertGreater(limit, start)
    
    def test_pool_active_status(self):
        """Test is_pool_active() method."""
        # Active pool
        pool_active = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Active Pool',
            slug='ACTIV',
            limit_date=timezone.now() + timedelta(days=30)
        )
        self.assertTrue(pool_active.is_pool_active())
        
        # Expired pool
        pool_expired = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Expired Pool',
            slug='EXPIR',
            limit_date=timezone.now() - timedelta(days=1)
        )
        self.assertFalse(pool_expired.is_pool_active())
    
    def test_days_remaining(self):
        """Test days_remaining calculation."""
        pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Test Pool',
            slug='DAYSZ',
            limit_date=timezone.now() + timedelta(days=10)
        )
        self.assertGreaterEqual(pool.days_remaining(), 9)  # Account for time passing
        self.assertLessEqual(pool.days_remaining(), 10)


class CelebrityModelTest(TestCase):
    """Test Celebrity model functionality."""
    
    def test_celebrity_creation(self):
        """Test creating a celebrity."""
        celeb = Celebrity.objects.create(
            name='Test Celebrity',
            bio='Famous person',
            wikidata_id='Q12345'
        )
        self.assertEqual(celeb.name, 'Test Celebrity')
        self.assertFalse(celeb.is_deceased())
    
    def test_is_deceased(self):
        """Test is_deceased() method."""
        # Living celebrity
        living = Celebrity.objects.create(name='Living Person')
        self.assertFalse(living.is_deceased())
        
        # Deceased celebrity
        deceased = Celebrity.objects.create(
            name='Deceased Person',
            death_date=timezone.now().date()
        )
        self.assertTrue(deceased.is_deceased())


class PredictionModelTest(TestCase):
    """Test Prediction model and validation."""
    
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Test Pool',
            slug='PRED1',
            limit_date=timezone.now() + timedelta(days=365),
            max_predictions_per_user=3,
            scoring_mode='simple'
        )
        self.celebrity = Celebrity.objects.create(
            name='Test Celebrity',
            wikidata_id='Q99999'
        )
        PoolMembership.objects.create(pool=self.pool, user=self.user)
    
    def test_prediction_creation(self):
        """Test creating a valid prediction."""
        prediction = Prediction.objects.create(
            user=self.user,
            pool=self.pool,
            celebrity=self.celebrity
        )
        self.assertIsNone(prediction.is_correct)
        self.assertEqual(prediction.weight, 1)
    
    def test_max_predictions_validation(self):
        """Test that max predictions per user is enforced."""
        # Create max predictions (3)
        for i in range(3):
            celeb = Celebrity.objects.create(
                name=f'Celebrity {i}',
                wikidata_id=f'Q{i}'
            )
            Prediction.objects.create(
                user=self.user,
                pool=self.pool,
                celebrity=celeb
            )
        
        # Try to create one more (should fail validation)
        extra_celeb = Celebrity.objects.create(
            name='Extra Celebrity',
            wikidata_id='QEXTRA'
        )
        prediction = Prediction(
            user=self.user,
            pool=self.pool,
            celebrity=extra_celeb
        )
        
        with self.assertRaises(ValidationError):
            prediction.clean()
    
    def test_distributed_scoring_weight_validation(self):
        """Test weight budget validation for distributed scoring."""
        self.pool.scoring_mode = 'distributed'
        self.pool.save()
        
        # Create predictions with weights totaling 8
        for i in range(2):
            celeb = Celebrity.objects.create(
                name=f'Celebrity {i}',
                wikidata_id=f'Q{i}'
            )
            Prediction.objects.create(
                user=self.user,
                pool=self.pool,
                celebrity=celeb,
                weight=4
            )
        
        # Try to add prediction with weight 3 (total would be 11 > 10)
        extra_celeb = Celebrity.objects.create(
            name='Extra Celebrity',
            wikidata_id='QEXTRA'
        )
        prediction = Prediction(
            user=self.user,
            pool=self.pool,
            celebrity=extra_celeb,
            weight=3
        )
        
        with self.assertRaises(ValidationError):
            prediction.clean()
    
    def test_inactive_pool_prediction(self):
        """Test that predictions cannot be created for inactive pools."""
        expired_pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Expired Pool',
            slug='EXPIR',
            limit_date=timezone.now() - timedelta(days=1)
        )
        
        prediction = Prediction(
            user=self.user,
            pool=expired_pool,
            celebrity=self.celebrity
        )
        
        with self.assertRaises(ValidationError):
            prediction.clean()


class CreatePoolFormTest(TestCase):
    """Test CreatePoolForm validation."""

    @staticmethod
    def _base_form_data():
        return {
            'name': 'Test Pool',
            'timeframe_choice': '1_year',
            'is_public': True,
            'max_predictions_per_user': 5,
            'scoring_mode': 'simple',
            'lock_after_days': 3,
        }
    
    def test_valid_form(self):
        """Test form with valid data."""
        form_data = self._base_form_data()
        form = CreatePoolForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_lock_after_days_validation(self):
        """Test that lock window settings are validated."""
        form_data = self._base_form_data()
        form_data['lock_after_days'] = None
        form = CreatePoolForm(data=form_data)
        self.assertFalse(form.is_valid())

        form_data['lock_after_days'] = 0
        form = CreatePoolForm(data=form_data)
        self.assertFalse(form.is_valid())

        form_data['lock_after_days'] = 3
        form = CreatePoolForm(data=form_data)
        self.assertTrue(form.is_valid())

    @patch('necroporra.forms.timezone.now')
    def test_rejects_combination_with_less_than_one_active_day(self, mock_now):
        """Late-year end_of_year + long lock window should be rejected."""
        mock_now.return_value = timezone.make_aware(datetime(2026, 12, 31, 12, 0, 0))

        form_data = self._base_form_data()
        form_data['timeframe_choice'] = 'end_of_year'
        form_data['lock_after_days'] = 1

        form = CreatePoolForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    @patch('necroporra.forms.timezone.now')
    def test_accepts_exactly_one_day_active_window(self, mock_now):
        """Exactly a 24-hour gap between lock_date and limit_date should pass."""
        mock_now.return_value = timezone.make_aware(datetime(2026, 12, 29, 23, 59, 59))

        form_data = self._base_form_data()
        form_data['timeframe_choice'] = 'end_of_year'
        form_data['lock_after_days'] = 1
        form = CreatePoolForm(data=form_data)
        self.assertTrue(form.is_valid())

    @patch('necroporra.forms.timezone.now')
    def test_rejects_under_one_day_active_window(self, mock_now):
        """A remaining active window smaller than 24 hours should fail."""
        mock_now.return_value = timezone.make_aware(datetime(2026, 12, 30, 0, 0, 0))

        form_data = self._base_form_data()
        form_data['timeframe_choice'] = 'end_of_year'
        form_data['lock_after_days'] = 1

        form = CreatePoolForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)


class RegisterFormTest(TestCase):
    """Test RegisterForm validation."""
    
    def test_valid_registration(self):
        """Test valid registration form."""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
            'password_confirm': 'securepass123'
        }
        form = RegisterForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_password_mismatch(self):
        """Test password confirmation validation."""
        form_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'securepass123',
            'password_confirm': 'differentpass'
        }
        form = RegisterForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('password_confirm', form.errors)
    
    def test_duplicate_email(self):
        """Test that duplicate emails are rejected."""
        User.objects.create_user(
            username='existing',
            email='existing@example.com',
            password='pass123'
        )
        
        form_data = {
            'username': 'newuser',
            'email': 'existing@example.com',
            'password': 'securepass123',
            'password_confirm': 'securepass123'
        }
        form = RegisterForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)


class ViewsTest(TestCase):
    """Test views and endpoints."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Test Pool',
            slug='TEST1',
            limit_date=timezone.now() + timedelta(days=365)
        )
        PoolMembership.objects.create(pool=self.pool, user=self.user)

    def _issue_invite(self, pool=None):
        """Create and return an active invitation token for a pool."""
        target_pool = pool or self.pool
        invitation = PoolInvitation.issue_for_pool(target_pool, created_by=target_pool.admin)
        return invitation.token
    
    def test_dashboard_view(self):
        """Test dashboard view requires login."""
        # Not logged in - should redirect
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        
        # Logged in - should work
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_pool_detail_view(self):
        """Test pool detail view."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('pool_detail', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.pool.name)
    
    def test_create_pool_view(self):
        """Test pool creation view."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('create_pool'))
        self.assertEqual(response.status_code, 200)

    def test_join_pool_invite_view_redirects_if_already_member(self):
        """Existing members should be redirected to pool detail from invite join page."""
        token = self._issue_invite()
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('join_pool_invite', args=[self.pool.slug, token]))
        self.assertRedirects(response, reverse('pool_detail', args=[self.pool.slug]))

    def test_join_pool_invite_view_renders_confirmation_for_non_member(self):
        """Non-members should see the browser join confirmation page when invite token is valid."""
        token = self._issue_invite()
        guest = User.objects.create_user(username='guest', password='testpass123')
        self.client.login(username=guest.username, password='testpass123')

        response = self.client.get(reverse('join_pool_invite', args=[self.pool.slug, token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.pool.name)
        self.assertContains(response, 'Confirm and Join Pool')

    def test_private_join_pool_invite_view_rejects_invalid_invitation_token(self):
        """Unknown invitation tokens should not reveal private pool join page."""
        self.pool.is_public = False
        self.pool.save(update_fields=['is_public'])

        response = self.client.get(reverse('join_pool_invite', args=[self.pool.slug, 'NOTVALIDTOKEN']))
        self.assertEqual(response.status_code, 404)

    def test_private_join_pool_invite_view_rejects_expired_invitation_token(self):
        """Expired invitation tokens should return 404."""
        self.pool.is_public = False
        self.pool.save(update_fields=['is_public'])
        invitation = PoolInvitation.issue_for_pool(self.pool, created_by=self.user)
        invitation.expires_at = timezone.now() - timedelta(minutes=1)
        invitation.save(update_fields=['expires_at'])

        response = self.client.get(reverse('join_pool_invite', args=[self.pool.slug, invitation.token]))
        self.assertEqual(response.status_code, 404)

    def test_slug_only_join_route_is_not_available(self):
        """Slug-only join URLs should not be available anymore."""
        response = self.client.get(f'/join/{self.pool.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_join_pool_invite_post_redirects_to_login_when_logged_out(self):
        """Submitting invite-join confirmation while logged out should redirect to login with next."""
        token = self._issue_invite()
        response = self.client.post(reverse('join_pool_invite', args=[self.pool.slug, token]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
        self.assertIn('next=', response.url)

    def test_join_pool_invite_post_joins_for_authenticated_user(self):
        """Authenticated non-members should join successfully and be redirected."""
        token = self._issue_invite()
        joiner = User.objects.create_user(username='joiner', password='testpass123')
        self.client.login(username=joiner.username, password='testpass123')

        response = self.client.post(reverse('join_pool_invite', args=[self.pool.slug, token]))
        self.assertRedirects(response, reverse('pool_detail', args=[self.pool.slug]))
        self.assertTrue(
            PoolMembership.objects.filter(pool=self.pool, user=joiner).exists()
        )

    def test_join_pool_invite_full_pool_disables_join(self):
        """Full pools should not allow joining from browser flow."""
        owner = User.objects.create_user(username='owner', password='testpass123')
        full_pool = Pool.objects.create(
            creator=owner,
            admin=owner,
            name='Full Pool',
            slug='FULL1',
            limit_date=timezone.now() + timedelta(days=30),
        )
        PoolMembership.objects.create(pool=full_pool, user=owner)

        for i in range(MAX_POOL_MEMBERS - 1):
            member = User.objects.create_user(username=f'fullmember{i}', password='testpass123')
            PoolMembership.objects.create(pool=full_pool, user=member)

        late_user = User.objects.create_user(username='latecomer', password='testpass123')
        self.client.login(username='latecomer', password='testpass123')
        token = self._issue_invite(pool=full_pool)

        response = self.client.post(reverse('join_pool_invite', args=[full_pool.slug, token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This pool is full')
        self.assertFalse(
            PoolMembership.objects.filter(pool=full_pool, user=late_user).exists()
        )

    def test_join_pool_api_post_is_denied(self):
        """Slug-based API joins should be blocked in favor of invitation links."""
        joiner = User.objects.create_user(username='apijoiner', password='testpass123')
        self.client.login(username='apijoiner', password='testpass123')

        response = self.client.post(reverse('api_join_pool', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 403)
        self.assertIn('invitation link', response.json()['detail'])
        self.assertFalse(
            PoolMembership.objects.filter(pool=self.pool, user=joiner).exists()
        )

    def test_regenerate_invite_requires_pool_admin(self):
        """Only the pool admin should be able to rotate invitation links."""
        self.pool.is_public = False
        self.pool.save(update_fields=['is_public'])
        PoolInvitation.issue_for_pool(self.pool, created_by=self.user)

        member = User.objects.create_user(username='member', password='testpass123')
        PoolMembership.objects.create(pool=self.pool, user=member)
        self.client.login(username='member', password='testpass123')

        response = self.client.post(reverse('api_regenerate_invite', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 403)

    def test_regenerate_invite_invalidates_old_token(self):
        """Regenerating invitation links should deactivate the previous token."""
        self.pool.is_public = False
        self.pool.save(update_fields=['is_public'])
        pool_invitation = PoolInvitation.issue_for_pool(self.pool, created_by=self.user)

        self.client.login(username='testuser', password='testpass123')

        old_token = pool_invitation.token
        response = self.client.post(reverse('api_regenerate_invite', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 200)

        pool_invitation.refresh_from_db()
        self.assertFalse(pool_invitation.is_active)

        payload = json.loads(response.content)
        new_token = payload['token']
        self.assertNotEqual(new_token, old_token)

        stale_join = self.client.get(reverse('join_pool_invite', args=[self.pool.slug, old_token]))
        self.assertEqual(stale_join.status_code, 404)

        valid_join = self.client.get(reverse('join_pool_invite', args=[self.pool.slug, new_token]))
        self.assertEqual(valid_join.status_code, 302)
        self.assertRedirects(valid_join, reverse('pool_detail', args=[self.pool.slug]))

    def test_toggle_member_invite_links_requires_pool_admin(self):
        """Only private pool admins can toggle member invite-link sharing."""
        self.pool.is_public = False
        self.pool.save(update_fields=['is_public'])

        member = User.objects.create_user(username='member2', password='testpass123')
        PoolMembership.objects.create(pool=self.pool, user=member)
        self.client.login(username='member2', password='testpass123')

        response = self.client.post(reverse('api_toggle_member_invite_links', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 403)

    def test_toggle_member_invite_links_updates_private_pool_setting(self):
        """Admin toggling should flip member invite-link access on private pools."""
        self.pool.is_public = False
        self.pool.allow_member_invite_links = True
        self.pool.save(update_fields=['is_public', 'allow_member_invite_links'])

        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('api_toggle_member_invite_links', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 200)

        self.pool.refresh_from_db()
        self.assertFalse(self.pool.allow_member_invite_links)

    def test_toggle_member_invite_links_rejected_for_public_pool(self):
        """Public pools should reject private invite-sharing toggle API."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('api_toggle_member_invite_links', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 400)

    def test_api_join_pool_get_still_returns_405(self):
        """API join route should remain POST-only for AJAX callers."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('api_join_pool', args=[self.pool.slug]))
        self.assertEqual(response.status_code, 405)

    def test_login_view_respects_next_redirect(self):
        """Custom login view should redirect to a safe next URL after login."""
        token = self._issue_invite()
        target = reverse('join_pool_invite', args=[self.pool.slug, token])
        response = self.client.post(
            reverse('login'),
            {
                'username': 'testuser',
                'password': 'testpass123',
                'next': target,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, target)

    @patch('necroporra.forms.timezone.now')
    @patch('necroporra.views.timezone.now')
    def test_create_pool_rejects_invalid_lock_window(self, mock_view_now, mock_form_now):
        """Pool creation should fail when lock timing leaves less than one active day."""
        fixed_now = timezone.make_aware(datetime(2026, 12, 31, 12, 0, 0))
        mock_view_now.return_value = fixed_now
        mock_form_now.return_value = fixed_now

        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('create_pool'), {
            'name': 'Invalid End Of Year Pool',
            'timeframe_choice': 'end_of_year',
            'is_public': True,
            'max_predictions_per_user': 5,
            'scoring_mode': 'simple',
            'lock_after_days': 1,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'at least one full active day')
        self.assertFalse(Pool.objects.filter(name='Invalid End Of Year Pool').exists())


class WikidataUtilsTest(TestCase):
    """Test wikidata_utils functions with mocking."""
    
    @patch('necroporra.wikidata_utils.requests.get')
    def test_get_wikidata_entity(self, mock_get):
        """Test fetching Wikidata entity."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'entities': {
                'Q123': {
                    'labels': {'en': {'value': 'Test Person'}},
                    'descriptions': {'en': {'value': 'Test description'}},
                    'claims': {
                        'P31': [{
                            'mainsnak': {
                                'datavalue': {
                                    'value': {'id': 'Q5'}
                                }
                            }
                        }],
                        'P569': [{
                            'mainsnak': {
                                'datavalue': {
                                    'value': {
                                        'time': '+1950-01-01T00:00:00Z'
                                    }
                                }
                            }
                        }]
                    }
                }
            }
        }
        mock_get.return_value = mock_response
        
        result = wikidata_utils.get_wikidata_entity('Q123')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Test Person')
        self.assertEqual(result['wikidata_id'], 'Q123')
        self.assertEqual(result['birth_date'], '1950-01-01')
    
    @patch('necroporra.wikidata_utils.requests.get')
    def test_search_wikidata_people(self, mock_get):
        """Test searching Wikidata for people."""
        # Mock search response (cirrus full-text search via action=query)
        search_response = MagicMock()
        search_response.status_code = 200
        search_response.json.return_value = {
            'query': {
                'search': [
                    {'title': 'Q123'}
                ]
            }
        }
        
        # Mock entity response (wbgetentities batch fetch)
        entity_response = MagicMock()
        entity_response.status_code = 200
        entity_response.json.return_value = {
            'entities': {
                'Q123': {
                    'labels': {'en': {'value': 'Test Person'}},
                    'descriptions': {'en': {'value': 'Test bio'}},
                    'claims': {
                        'P31': [{
                            'mainsnak': {
                                'datavalue': {
                                    'value': {'id': 'Q5'}
                                }
                            }
                        }]
                    }
                }
            }
        }
        
        # Return different responses based on API action
        def side_effect(url, *args, **kwargs):
            params = kwargs.get('params', {})
            if 'srsearch' in params:
                return search_response
            else:
                return entity_response
        
        mock_get.side_effect = side_effect
        
        results = wikidata_utils.search_wikidata_people('Test')
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Test Person')


class IntegrationTest(TestCase):
    """Integration tests for common workflows."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass123')
    
    def test_pool_creation_and_prediction_workflow(self):
        """Test complete workflow: create pool, join, make prediction."""
        self.client.login(username='testuser', password='testpass123')
        
        # Create pool
        response = self.client.post(reverse('create_pool'), {
            'name': 'Integration Test Pool',
            'timeframe_choice': '1_year',
            'is_public': True,
            'max_predictions_per_user': 5,
            'scoring_mode': 'simple',
            'lock_after_days': 3,
        })
        
        # Should redirect to pool detail
        self.assertEqual(response.status_code, 302)
        
        # Verify pool was created
        pool = Pool.objects.get(name='Integration Test Pool')
        self.assertIsNotNone(pool)
        self.assertFalse(pool.is_locked)
        self.assertIsNotNone(pool.lock_date)
        self.assertEqual(pool.lock_after_days, 3)
        
        # Verify user is a member
        membership = PoolMembership.objects.filter(pool=pool, user=self.user)
        self.assertTrue(membership.exists())
        
        # Create a celebrity and make a prediction
        celebrity = Celebrity.objects.create(
            name='Test Celebrity',
            wikidata_id='QTEST'
        )
        
        prediction = Prediction.objects.create(
            user=self.user,
            pool=pool,
            celebrity=celebrity
        )
        
        self.assertIsNone(prediction.is_correct)
        self.assertEqual(prediction.user, self.user)
        self.assertEqual(prediction.pool, pool)


class AddCelebrityApiWeightValidationTest(TestCase):
    """Regression tests for distributed weight handling in add_celebrity API."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='weightuser', password='testpass123')
        self.client.login(username='weightuser', password='testpass123')

        self.distributed_pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Distributed Pool',
            slug='DIST1',
            limit_date=timezone.now() + timedelta(days=365),
            scoring_mode='distributed',
            max_predictions_per_user=10,
        )
        PoolMembership.objects.create(pool=self.distributed_pool, user=self.user)

        self.simple_pool = Pool.objects.create(
            creator=self.user,
            admin=self.user,
            name='Simple Pool',
            slug='SIMP1',
            limit_date=timezone.now() + timedelta(days=365),
            scoring_mode='simple',
            max_predictions_per_user=10,
        )
        PoolMembership.objects.create(pool=self.simple_pool, user=self.user)

        self.celebrity = Celebrity.objects.create(
            name='Weight Test Celebrity',
            wikidata_id='QWEIGHT1',
        )

    def test_distributed_requires_weight(self):
        """Distributed pool requests without weight should fail."""
        response = self.client.post(
            reverse('api_add_celebrity', args=[self.distributed_pool.slug]),
            data=json.dumps({'celebrity_id': self.celebrity.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('Weight is required', response.json()['detail'])
        self.assertFalse(
            Prediction.objects.filter(pool=self.distributed_pool, user=self.user, celebrity=self.celebrity).exists()
        )

    def test_distributed_rejects_invalid_weight(self):
        """Distributed pool should reject non-integer weight values."""
        response = self.client.post(
            reverse('api_add_celebrity', args=[self.distributed_pool.slug]),
            data=json.dumps({'celebrity_id': self.celebrity.id, 'weight': 'abc'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('valid integer', response.json()['detail'])
        self.assertFalse(
            Prediction.objects.filter(pool=self.distributed_pool, user=self.user, celebrity=self.celebrity).exists()
        )

    def test_distributed_accepts_valid_weight(self):
        """Distributed pool should persist explicit valid weight."""
        response = self.client.post(
            reverse('api_add_celebrity', args=[self.distributed_pool.slug]),
            data=json.dumps({'celebrity_id': self.celebrity.id, 'weight': 4}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        prediction = Prediction.objects.get(
            pool=self.distributed_pool,
            user=self.user,
            celebrity=self.celebrity,
        )
        self.assertEqual(prediction.weight, 4)

    def test_simple_pool_allows_missing_weight_with_default(self):
        """Simple pool keeps legacy behavior: missing weight defaults to 1."""
        response = self.client.post(
            reverse('api_add_celebrity', args=[self.simple_pool.slug]),
            data=json.dumps({'celebrity_id': self.celebrity.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        prediction = Prediction.objects.get(
            pool=self.simple_pool,
            user=self.user,
            celebrity=self.celebrity,
        )
        self.assertEqual(prediction.weight, 1)


class PoolLockBehaviorApiTest(TestCase):
    """Tests for open vs closed behavior around visibility and prediction edits."""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')

        self.pool = Pool.objects.create(
            creator=self.admin,
            admin=self.admin,
            name='Lock Behavior Pool',
            slug='LOCK1',
            limit_date=timezone.now() + timedelta(days=365),
            is_locked=False,
            lock_after_days=3,
            lock_date=timezone.now() + timedelta(days=3),
        )
        PoolMembership.objects.create(pool=self.pool, user=self.admin)
        PoolMembership.objects.create(pool=self.pool, user=self.member)

        self.celebrity = Celebrity.objects.create(name='Lock Test Celebrity', wikidata_id='QLOCK1')
        self.member_prediction = Prediction.objects.create(
            user=self.member,
            pool=self.pool,
            celebrity=self.celebrity,
        )

    def test_user_picks_hidden_while_pool_open(self):
        self.client.login(username='admin', password='testpass123')

        response = self.client.get(
            reverse('api_user_picks', args=[self.pool.slug]),
            {'user_id': self.member.id},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('not visible', response.json()['detail'])

    def test_user_picks_visible_after_pool_closed(self):
        self.pool.is_locked = True
        self.pool.save(update_fields=['is_locked'])
        self.client.login(username='admin', password='testpass123')

        response = self.client.get(
            reverse('api_user_picks', args=[self.pool.slug]),
            {'user_id': self.member.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['prediction_count'], 1)

    def test_add_prediction_rejected_when_closed(self):
        self.pool.is_locked = True
        self.pool.save(update_fields=['is_locked'])
        self.client.login(username='admin', password='testpass123')

        new_celeb = Celebrity.objects.create(name='Another Celebrity', wikidata_id='QLOCK2')
        response = self.client.post(
            reverse('api_add_celebrity', args=[self.pool.slug]),
            data=json.dumps({'celebrity_id': new_celeb.id}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('closed', response.json()['detail'].lower())

    def test_delete_prediction_rejected_when_closed(self):
        self.pool.is_locked = True
        self.pool.save(update_fields=['is_locked'])
        self.client.login(username='member', password='testpass123')

        response = self.client.delete(
            reverse('api_delete_prediction', args=[self.pool.slug, self.member_prediction.id]),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('closed', response.json()['detail'].lower())

    def test_admin_can_lock_pool_immediately(self):
        self.client.login(username='admin', password='testpass123')

        response = self.client.post(reverse('api_lock_pool', args=[self.pool.slug]))

        self.assertEqual(response.status_code, 200)
        self.pool.refresh_from_db()
        self.assertTrue(self.pool.is_locked)

    def test_non_admin_cannot_lock_pool(self):
        self.client.login(username='member', password='testpass123')

        response = self.client.post(reverse('api_lock_pool', args=[self.pool.slug]))

        self.assertEqual(response.status_code, 403)


class UserDeletionCascadeTest(TestCase):
    """Test that deleting a user cascades correctly through pools, memberships, and predictions."""

    def _make_pool(self, creator, admin=None, name='Test Pool'):
        """Helper to create a pool with a membership for the admin."""
        pool = Pool.objects.create(
            creator=creator,
            admin=admin or creator,
            name=name,
            slug=Pool.generate_slug(),
            timeframe_choice='1_year',
            limit_date=timezone.now() + timedelta(days=365),
        )
        PoolMembership.objects.create(pool=pool, user=admin or creator)
        return pool

    def _add_member(self, pool, user):
        """Helper to add a member to a pool."""
        return PoolMembership.objects.create(pool=pool, user=user)

    def _add_prediction(self, pool, user, celebrity):
        """Helper to add a prediction."""
        return Prediction.objects.create(pool=pool, user=user, celebrity=celebrity)

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        self.user3 = User.objects.create_user(username='user3', password='pass')
        self.celeb = Celebrity.objects.create(name='Famous Person', wikidata_id='Q999')

    # ------------------------------------------------------------------
    # Test A: Delete admin (who is also creator) -> pool is destroyed
    # ------------------------------------------------------------------
    def test_delete_admin_destroys_pool(self):
        """Deleting the admin user cascades to delete the pool and everything in it."""
        pool = self._make_pool(self.user1)
        self._add_member(pool, self.user2)
        self._add_prediction(pool, self.user1, self.celeb)
        self._add_prediction(pool, self.user2, self.celeb)
        PoolCelebrity.objects.create(pool=pool, celebrity=self.celeb, added_by=self.user1)

        pool_id = pool.id

        self.user1.delete()

        self.assertFalse(Pool.objects.filter(id=pool_id).exists())
        self.assertFalse(PoolMembership.objects.filter(pool_id=pool_id).exists())
        self.assertFalse(Prediction.objects.filter(pool_id=pool_id).exists())
        self.assertFalse(PoolCelebrity.objects.filter(pool_id=pool_id).exists())

    # ------------------------------------------------------------------
    # Test B: Creator transfers admin away, then creator is deleted ->
    #         pool survives, creator field becomes NULL
    # ------------------------------------------------------------------
    def test_delete_non_admin_creator_pool_survives(self):
        """Deleting a creator who is no longer admin leaves the pool intact."""
        pool = self._make_pool(self.user1)
        self._add_member(pool, self.user2)

        # Transfer admin to user2
        pool.admin = self.user2
        pool.save(update_fields=['admin'])

        self.user1.delete()

        pool.refresh_from_db()
        self.assertIsNone(pool.creator)
        self.assertEqual(pool.admin, self.user2)

    # ------------------------------------------------------------------
    # Test C: After admin transfer, delete the new admin -> pool dies
    # ------------------------------------------------------------------
    def test_delete_transferred_admin_destroys_pool(self):
        """After admin transfer, deleting the new admin still destroys the pool."""
        pool = self._make_pool(self.user1)
        self._add_member(pool, self.user2)
        pool.admin = self.user2
        pool.save(update_fields=['admin'])

        pool_id = pool.id

        self.user2.delete()

        self.assertFalse(Pool.objects.filter(id=pool_id).exists())

    # ------------------------------------------------------------------
    # Test D: Delete a regular member -> pool survives, their data gone
    # ------------------------------------------------------------------
    def test_delete_regular_member_pool_survives(self):
        """Deleting a non-admin member removes their membership and predictions but keeps the pool."""
        pool = self._make_pool(self.user1)
        self._add_member(pool, self.user2)
        PoolCelebrity.objects.create(pool=pool, celebrity=self.celeb, added_by=self.user2)
        self._add_prediction(pool, self.user2, self.celeb)

        user2_id = self.user2.id
        self.user2.delete()

        pool.refresh_from_db()  # pool still exists
        self.assertEqual(pool.admin, self.user1)
        self.assertFalse(Prediction.objects.filter(user_id=user2_id).exists())
        self.assertFalse(PoolMembership.objects.filter(user_id=user2_id).exists())

    # ------------------------------------------------------------------
    # Test E: Admin of multiple pools deleted -> all those pools deleted
    # ------------------------------------------------------------------
    def test_delete_admin_of_multiple_pools(self):
        """Deleting a user who admins multiple pools destroys all of them."""
        pool_a = self._make_pool(self.user1, name='Pool A')
        pool_b = self._make_pool(self.user1, name='Pool B')
        self._add_member(pool_a, self.user2)
        self._add_member(pool_b, self.user3)

        ids = [pool_a.id, pool_b.id]

        self.user1.delete()

        self.assertEqual(Pool.objects.filter(id__in=ids).count(), 0)

    # ------------------------------------------------------------------
    # Test F: PoolCelebrity.added_by is SET_NULL on user deletion
    # ------------------------------------------------------------------
    def test_pool_celebrity_added_by_set_null(self):
        """When a non-admin user is deleted, PoolCelebrity.added_by becomes NULL."""
        pool = self._make_pool(self.user1)
        self._add_member(pool, self.user2)
        pc = PoolCelebrity.objects.create(pool=pool, celebrity=self.celeb, added_by=self.user2)

        self.user2.delete()

        pc.refresh_from_db()
        self.assertIsNone(pc.added_by)

    # ------------------------------------------------------------------
    # Test G: Pool with only admin member -- delete admin -> pool gone
    # ------------------------------------------------------------------
    def test_delete_sole_member_admin(self):
        """Deleting the only member (who is the admin) destroys the pool."""
        pool = self._make_pool(self.user1)
        pool_id = pool.id

        self.user1.delete()

        self.assertFalse(Pool.objects.filter(id=pool_id).exists())
