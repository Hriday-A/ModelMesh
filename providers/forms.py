from django import forms

from .models import AIModel, Provider


class ProviderForm(forms.ModelForm):
    class Meta:
        model = Provider
        fields = ["name", "slug", "api_base_url", "enabled"]


class AIModelForm(forms.ModelForm):
    class Meta:
        model = AIModel
        fields = ["name", "model_id", "input_price_per_m", "output_price_per_m", "weight", "enabled"]
        labels = {"name": "Model name"}
        error_messages = {
            "input_price_per_m": {"min_value": "The input price can't be negative. Enter 0 or more."},
            "output_price_per_m": {"min_value": "The output price can't be negative. Enter 0 or more."},
            "weight": {
                "min_value": "The weight must be from 0 to 100.",
                "max_value": "The weight must be from 0 to 100.",
            },
        }


AIModelFormSet = forms.inlineformset_factory(
    Provider, AIModel, form=AIModelForm, extra=1, can_delete=True
)
