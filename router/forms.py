from django import forms

from accounts.models import UserProfile

from .models import Feedback, RouterModel, RoutingRule, RoutingSettings


class RoutingRuleForm(forms.ModelForm):
    class Meta:
        model = RoutingRule
        fields = ["category", "keywords", "preferred_model", "fallback_model", "enabled"]
        labels = {"category": "Task category", "keywords": "Detected by keywords"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        enabled = RouterModel.objects.filter(enabled=True)
        self.fields["preferred_model"].queryset = enabled
        self.fields["fallback_model"].queryset = enabled
        self.fields["fallback_model"].required = False


def slider(min_value, max_value, step):
    return forms.NumberInput(attrs={"type": "range", "min": min_value, "max": max_value, "step": step})


class RoutingSettingsForm(forms.ModelForm):
    class Meta:
        model = RoutingSettings
        fields = ["quality_weight", "cost_weight", "speed_weight", "confidence_threshold"]
        labels = {
            "quality_weight": "Quality",
            "cost_weight": "Cost",
            "speed_weight": "Speed",
            "confidence_threshold": "Confidence bar",
        }
        help_texts = {
            "quality_weight": "How much a better chance of a good answer counts (×0–2).",
            "cost_weight": "How much price counts against a model (×0–2).",
            "speed_weight": "How much slowness counts against a model (×0–2).",
        }
        widgets = {
            "quality_weight": slider(0, 2, 0.1),
            "cost_weight": slider(0, 2, 0.1),
            "speed_weight": slider(0, 2, 0.1),
            "confidence_threshold": slider(0.3, 0.95, 0.05),
        }


class TestPromptForm(forms.Form):
    test_prompt = forms.CharField(
        label="Prompt", max_length=4000, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Try a prompt…"})
    )
    priority = forms.ChoiceField(choices=UserProfile.PRIORITY_CHOICES, initial="balanced")

    def clean_test_prompt(self):
        prompt = self.cleaned_data["test_prompt"].strip()
        if not prompt:
            raise forms.ValidationError("Enter a prompt to test.")
        return prompt


class FeedbackForm(forms.ModelForm):
    stars = forms.TypedChoiceField(
        choices=[(i, f"{i} ★") for i in range(5, 0, -1)], coerce=int, widget=forms.RadioSelect, label="Your rating"
    )

    class Meta:
        model = Feedback
        fields = ["stars", "comment"]
        labels = {"comment": "Comment (optional)"}
        widgets = {"comment": forms.Textarea(attrs={"rows": 3, "maxlength": 1000})}
