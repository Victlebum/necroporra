"""
Django forms for necroporra
"""
from datetime import timedelta

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Pool


class LoginForm(AuthenticationForm):
    """Login form with Bootstrap/Bulma styling."""
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'input',
            'placeholder': 'Enter your username',
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'input',
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        })
    )


class RegisterForm(forms.ModelForm):
    """User registration form."""
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'input',
            'placeholder': 'At least 8 characters',
            'autocomplete': 'new-password',
        }),
        help_text='Password must be at least 8 characters long.'
    )
    password_confirm = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'input',
            'placeholder': 'Confirm your password',
            'autocomplete': 'new-password',
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'Choose a username',
                'autocomplete': 'username',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'input',
                'placeholder': 'Enter your email',
                'autocomplete': 'email',
            }),
        }

    def clean_password_confirm(self):
        """Validate that passwords match."""
        password = self.cleaned_data.get('password')
        password_confirm = self.cleaned_data.get('password_confirm')
        
        if password and password_confirm and password != password_confirm:
            raise ValidationError('Passwords do not match')
        
        return password_confirm

    def clean_email(self):
        """Validate that email is unique."""
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('A user with this email already exists')
        return email

    def save(self, commit=True):
        """Save user with hashed password."""
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class StepperNumberInput(forms.NumberInput):
    """Reusable number input rendered as a +/- stepper control."""

    template_name = 'necroporra/widgets/number_stepper.html'

    def __init__(self, attrs=None):
        attrs = attrs.copy() if attrs else {}
        existing_class = attrs.get('class', '')
        merged_classes = f"{existing_class} number-stepper__input js-number-stepper-input".strip()
        attrs['class'] = ' '.join(dict.fromkeys(merged_classes.split()))
        attrs.setdefault('inputmode', 'numeric')
        super().__init__(attrs=attrs)


class CreatePoolForm(forms.ModelForm):
    """Form for creating a new pool."""
    timeframe_choice = forms.ChoiceField(
        label='Pool Duration',
        choices=Pool.TIMEFRAME_CHOICES,
        initial='1_year',
        widget=forms.Select(attrs={'class': 'select'})
    )
    
    is_public = forms.BooleanField(
        label='Public Pool',
        initial=True,
        required=False,
        help_text='Public pools can be discovered by anyone with the pool code',
        widget=forms.CheckboxInput(attrs={'class': 'checkbox'})
    )
    
    max_predictions_per_user = forms.IntegerField(
        label='Max Predictions Per User',
        initial=10,
        min_value=1,
        max_value=10,
        widget=StepperNumberInput(attrs={
            'class': 'input',
            'min': '1',
            'max': '10',
        })
    )
    
    lock_after_days = forms.IntegerField(
        label='Lock pool after (days)',
        initial=7,
        required=True,
        widget=StepperNumberInput(attrs={
            'class': 'input',
            'min': '1',
            'max': '7',
            'id': 'id_lock_after_days',
        })
    )
    
    scoring_mode = forms.ChoiceField(
        label='Scoring Mode',
        choices=Pool.SCORING_MODES,
        initial='simple',
        widget=forms.RadioSelect(attrs={'class': 'radio'})
    )

    class Meta:
        model = Pool
        fields = ['name', 'timeframe_choice', 'is_public', 
                  'max_predictions_per_user', 'scoring_mode']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'e.g., Celebrity Deaths 2026',
            }),
        }
        help_texts = {
            'name': 'Give your pool a descriptive name',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def clean(self):
        """Validate form fields."""
        cleaned_data = super().clean()
        timeframe_choice = cleaned_data.get('timeframe_choice')
        lock_after_days = cleaned_data.get('lock_after_days')

        if lock_after_days is None:
            self.add_error('lock_after_days', 'Please specify when the pool should lock (1-7 days)')
        elif lock_after_days < 1 or lock_after_days > 7:
            self.add_error('lock_after_days', 'Days must be between 1 and 7')

        if timeframe_choice and lock_after_days is not None and not self.errors:
            now = timezone.now()
            projected_limit_date = Pool.calculate_limit_date(timeframe_choice, now)
            projected_lock_date = now + timedelta(days=lock_after_days)

            if projected_limit_date - projected_lock_date < timedelta(days=1):
                self.add_error(
                    None,
                    'Pool lock timing must leave at least one full active day before the pool ends. '
                    'Choose a longer duration or fewer lock days.'
                )
        
        return cleaned_data


class ChangePasswordForm(PasswordChangeForm):
    """Password change form with Bulma styling."""

    PASSWORD_FIELDS = ('old_password', 'new_password1', 'new_password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.PASSWORD_FIELDS:
            attrs = self.fields[field_name].widget.attrs
            attrs['class'] = 'input'
            attrs.pop('autofocus', None)
