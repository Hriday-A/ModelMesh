from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import APIKey, RequestLog, UserProfile


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "email"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["organization", "default_priority"]
        labels = {"default_priority": "Default routing priority"}


class APIKeyForm(forms.ModelForm):
    MAX_ACTIVE_KEYS = 5

    class Meta:
        model = APIKey
        fields = ["name"]
        labels = {"name": "Key name"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "e.g. My class project"})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean(self):
        cleaned = super().clean()
        if self.user and self.user.api_keys.filter(revoked=False).count() >= self.MAX_ACTIVE_KEYS:
            raise forms.ValidationError(
                f"You can have at most {self.MAX_ACTIVE_KEYS} active keys. Revoke one first."
            )
        return cleaned


class PlaygroundForm(forms.Form):
    MAX_PROMPT_LENGTH = 8000

    prompt = forms.CharField(
        max_length=MAX_PROMPT_LENGTH,
        widget=forms.Textarea(attrs={"rows": 6, "placeholder": "Ask anything…"}),
    )
    priority = forms.ChoiceField(choices=UserProfile.PRIORITY_CHOICES, initial="balanced")

    def clean_prompt(self):
        prompt = self.cleaned_data["prompt"].strip()
        if not prompt:
            raise forms.ValidationError("Prompt cannot be empty.")
        return prompt


class HistoryFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search", widget=forms.TextInput(attrs={"placeholder": "Search prompts"}))
    status = forms.ChoiceField(required=False, choices=[("", "Any status")] + RequestLog.STATUS_CHOICES)
    source = forms.ChoiceField(required=False, choices=[("", "Any source")] + RequestLog.SOURCE_CHOICES)
    date_from = forms.DateField(required=False, label="From", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, label="To", widget=forms.DateInput(attrs={"type": "date"}))

    def filter(self, queryset):
        if not self.is_valid():
            return queryset
        data = self.cleaned_data
        if data["q"]:
            queryset = queryset.filter(prompt__icontains=data["q"])
        if data["status"]:
            queryset = queryset.filter(status=data["status"])
        if data["source"]:
            queryset = queryset.filter(source=data["source"])
        if data["date_from"]:
            queryset = queryset.filter(created_at__date__gte=data["date_from"])
        if data["date_to"]:
            queryset = queryset.filter(created_at__date__lte=data["date_to"])
        return queryset
