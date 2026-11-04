from django import forms

from .models import UsageLimit
from .services import RANGE_CHOICES


class RangeForm(forms.Form):
    days = forms.TypedChoiceField(choices=RANGE_CHOICES, coerce=int, initial=7, label="Range")


class UsageLimitForm(forms.ModelForm):
    class Meta:
        model = UsageLimit
        fields = ["requests_per_minute", "monthly_budget_usd", "cache_enabled", "cache_ttl_minutes"]
        labels = {
            "requests_per_minute": "Requests per minute (per user)",
            "monthly_budget_usd": "Monthly budget (USD)",
            "cache_enabled": "Cache identical prompts",
            "cache_ttl_minutes": "Keep cached answers for",
        }
