from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.conf import settings

from .models import Item, ClaimRequest, UserProfile


# ── Helpers ──────────────────────────────────────────────────────────────────

def _allowed_domains():
    return getattr(settings, 'ALLOWED_EMAIL_DOMAINS', ['college.edu'])


# ── Auth Forms ───────────────────────────────────────────────────────────────

class CampusSignupForm(UserCreationForm):
    """
    Extended signup form that enforces college email domains
    and collects student ID / personal details.
    """
    first_name = forms.CharField(max_length=50, required=True)
    last_name  = forms.CharField(max_length=50, required=True)
    email      = forms.EmailField(
        required=True,
        help_text=f'Must end with one of: {", ".join(_allowed_domains())}'
    )
    student_id = forms.CharField(max_length=20, label='Student / Roll Number')
    department = forms.CharField(max_length=100, required=False)
    phone      = forms.CharField(max_length=15, required=False)

    class Meta:
        model  = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def clean_email(self):
        email   = self.cleaned_data['email'].lower()
        domains = _allowed_domains()
        if not any(email.endswith(f'@{d}') for d in domains):
            raise forms.ValidationError(
                f'Registration is restricted to college email addresses '
                f'({", ".join("@" + d for d in domains)}).'
            )
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_student_id(self):
        student_id = self.cleaned_data['student_id'].strip()
        if UserProfile.objects.filter(student_id__iexact=student_id).exists():
            raise forms.ValidationError('An account with this student / roll number already exists.')
        return student_id

    def save(self, commit=True):
        user            = super().save(commit=False)
        user.first_name = self.cleaned_data['first_name']
        user.last_name  = self.cleaned_data['last_name']
        user.email      = self.cleaned_data['email']
        if commit:
            user.save()
            UserProfile.objects.create(
                user       = user,
                student_id = self.cleaned_data['student_id'],
                department = self.cleaned_data.get('department', ''),
                phone      = self.cleaned_data.get('phone', ''),
            )
        return user


# ── Item Forms ────────────────────────────────────────────────────────────────

class ItemForm(forms.ModelForm):
    class Meta:
        model  = Item
        fields = ['title', 'description', 'category', 'status', 'image', 'campus_location']
        widgets = {
            'description':     forms.Textarea(attrs={'rows': 4}),
            'campus_location': forms.TextInput(attrs={'placeholder': 'e.g. Library Block B, Floor 2'}),
        }

    def __init__(self, *args, **kwargs):
        # Reporter can only mark an item as Lost or Found initially
        is_new = kwargs.pop('is_new', False)
        super().__init__(*args, **kwargs)
        if is_new:
            self.fields['status'].choices = [
                ('Lost',  'Lost'),
                ('Found', 'Found'),
            ]
        elif self.instance and self.instance.pk:
            # Claim approval is staff-only; reporters cannot bypass it by editing.
            transitions = {
                Item.Status.LOST: [Item.Status.LOST, Item.Status.FOUND, Item.Status.RETURNED],
                Item.Status.FOUND: [Item.Status.FOUND, Item.Status.RETURNED],
                Item.Status.CLAIMED: [Item.Status.CLAIMED, Item.Status.RETURNED],
                Item.Status.RETURNED: [Item.Status.RETURNED],
            }
            allowed = transitions.get(self.instance.status, [self.instance.status])
            self.fields['status'].choices = [
                choice for choice in Item.Status.choices if choice[0] in allowed
            ]
        # Bootstrap styling
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')
        self.fields['category'].widget.attrs['class'] = 'form-select'
        self.fields['status'].widget.attrs['class']   = 'form-select'

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Please upload an image smaller than 5 MB.')
        return image


class ItemStatusUpdateForm(forms.ModelForm):
    """Lightweight form just for changing an item's status (owner / admin)."""
    class Meta:
        model  = Item
        fields = ['status']
        widgets = {'status': forms.Select(attrs={'class': 'form-select'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_status = self.instance.status
        transitions = {
            Item.Status.LOST: [Item.Status.LOST, Item.Status.FOUND, Item.Status.RETURNED],
            Item.Status.FOUND: [Item.Status.FOUND, Item.Status.RETURNED],
            Item.Status.CLAIMED: [Item.Status.CLAIMED, Item.Status.RETURNED],
            Item.Status.RETURNED: [Item.Status.RETURNED],
        }
        allowed = transitions.get(current_status, [current_status])
        self.fields['status'].choices = [
            choice for choice in Item.Status.choices if choice[0] in allowed
        ]


class ProfileForm(forms.ModelForm):
    """Editable campus profile fields, including the user's display details."""

    first_name = forms.CharField(max_length=50, required=True)
    last_name = forms.CharField(max_length=50, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = ['student_id', 'department', 'phone', 'avatar']

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
            self.fields['email'].initial = user.email
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        domains = _allowed_domains()
        if not any(email.endswith(f'@{domain}') for domain in domains):
            raise forms.ValidationError('Use a permitted college email address.')
        if User.objects.exclude(pk=self.user.pk).filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean_student_id(self):
        student_id = self.cleaned_data['student_id'].strip()
        if UserProfile.objects.exclude(pk=self.instance.pk).filter(student_id__iexact=student_id).exists():
            raise forms.ValidationError('An account with this student / roll number already exists.')
        return student_id

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and avatar.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Please upload an image smaller than 5 MB.')
        return avatar

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data['first_name']
        self.user.last_name = self.cleaned_data['last_name']
        self.user.email = self.cleaned_data['email']
        if commit:
            self.user.save()
            profile.save()
        return profile


# ── Claim Forms ───────────────────────────────────────────────────────────────

class ClaimRequestForm(forms.ModelForm):
    class Meta:
        model  = ClaimRequest
        fields = ['proof_description']
        widgets = {
            'proof_description': forms.Textarea(attrs={
                'rows': 5,
                'class': 'form-control',
                'placeholder': (
                    'Describe any identifying features, serial numbers, '
                    'or circumstances to prove ownership…'
                ),
            })
        }


# ── Dashboard / Search Filter ─────────────────────────────────────────────────

class ItemFilterForm(forms.Form):
    q        = forms.CharField(required=False, label='Search',
                               widget=forms.TextInput(attrs={
                                   'class': 'form-control',
                                   'placeholder': 'Search by keyword…',
                               }))
    category = forms.ChoiceField(required=False, label='Category',
                                 widget=forms.Select(attrs={'class': 'form-select'}))
    status   = forms.ChoiceField(required=False, label='Status',
                                 widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        blank = [('', 'All')]
        self.fields['category'].choices = blank + list(Item.Category.choices)
        self.fields['status'].choices   = blank + list(Item.Status.choices)
