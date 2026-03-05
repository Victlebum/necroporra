"""
Django forms for necroporra
"""
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError
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
        help_text='Public pools can be discovered by anyone with the code',
        widget=forms.CheckboxInput(attrs={'class': 'checkbox'})
    )
    
    max_predictions_per_user = forms.IntegerField(
        label='Max Predictions Per User',
        initial=10,
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(attrs={
            'class': 'input',
            'min': '1',
            'max': '10',
        })
    )
    
    picks_visible_from_start = forms.BooleanField(
        label='Picks visible immediately',
        initial=False,
        required=False,
        help_text='If checked, everyone can see all picks from the start',
        widget=forms.CheckboxInput(attrs={'class': 'checkbox', 'id': 'id_picks_visible_from_start'})
    )
    
    picks_visible_after_days = forms.IntegerField(
        label='Or make picks visible after (days)',
        initial=7,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'input',
            'min': '0',
            'max': '7',
            'id': 'id_picks_visible_after_days',
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
        fields = ['name', 'description', 'timeframe_choice', 'is_public', 
                  'max_predictions_per_user', 'scoring_mode']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'input',
                'placeholder': 'e.g., Celebrity Deaths 2026',
            }),
            'description': forms.Textarea(attrs={
                'class': 'textarea',
                'placeholder': 'Add details about your pool (optional)',
                'rows': 4,
            }),
        }
        help_texts = {
            'name': 'Give your pool a descriptive name',
            'description': 'Optional: Add any rules or special conditions',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
    
    def clean(self):
        """Validate form fields."""
        cleaned_data = super().clean()
        picks_visible_from_start = cleaned_data.get('picks_visible_from_start')
        picks_visible_after_days = cleaned_data.get('picks_visible_after_days')
        
        # If not visible from start, picks_visible_after_days is required
        if not picks_visible_from_start and picks_visible_after_days is None:
            self.add_error('picks_visible_after_days', 
                          'Please specify when picks should become visible (0-7 days)')
        
        # Validate picks_visible_after_days range
        if picks_visible_after_days is not None and (picks_visible_after_days < 0 or picks_visible_after_days > 7):
            self.add_error('picks_visible_after_days', 
                          'Days must be between 0 and 7')
        
        return cleaned_data


class ChangePasswordForm(PasswordChangeForm):
    """Password change form with Bulma styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ('old_password', 'new_password1', 'new_password2'):
            self.fields[field_name].widget.attrs.update({
                'class': 'input',
            })
