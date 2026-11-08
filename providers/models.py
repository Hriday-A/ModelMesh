from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

PRICE_HELP = "Per 1M tokens, in the provider's billing unit (USD for Anthropic, coins for Lumen)."


class Provider(models.Model):
    """A service that hosts AI models, such as UIUC Lumen or Anthropic."""

    HEALTH_CHOICES = [
        ("unknown", "Not checked"),
        ("healthy", "Healthy"),
        ("degraded", "Degraded"),
        ("down", "Down"),
    ]

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(
        "Short ID",
        max_length=50,
        unique=True,
        help_text='Must match the "provider" saved on each request, for example lumen.',
    )
    api_base_url = models.URLField(
        "API base URL", blank=True, help_text="Leave empty for the offline mock provider."
    )
    enabled = models.BooleanField(default=True)
    health_status = models.CharField(max_length=10, choices=HEALTH_CHOICES, default="unknown")
    health_detail = models.CharField(max_length=255, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AIModel(models.Model):
    """One model a provider serves, with its price.

    The field names match router.RouterModel (model_id, input_price_per_m,
    output_price_per_m, enabled) so the two tables can be merged later.
    """

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="models")
    name = models.CharField(max_length=60)
    model_id = models.CharField("Model ID", max_length=100, unique=True)
    input_price_per_m = models.DecimalField(
        "Input price per 1M tokens", max_digits=10, decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))], help_text=PRICE_HELP,
    )
    output_price_per_m = models.DecimalField(
        "Output price per 1M tokens", max_digits=10, decimal_places=4,
        validators=[MinValueValidator(Decimal("0"))], help_text=PRICE_HELP,
    )
    weight = models.PositiveSmallIntegerField(
        "Load-balancing weight", default=100,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0 to 100. A higher weight sends more traffic to this model when models tie.",
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider__name", "name"]
        verbose_name = "AI model"

    def __str__(self):
        return f"{self.name} ({self.provider})"

    def cost(self, input_tokens, output_tokens):
        return (
            self.input_price_per_m * input_tokens + self.output_price_per_m * output_tokens
        ) / Decimal(1_000_000)
