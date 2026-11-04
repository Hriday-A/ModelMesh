from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class UsageLimit(models.Model):
    """A user's rate limit, monthly budget and cache settings (Screen 14).

    Created the first time the user opens the Quotas & cache page.
    """

    CACHE_TTL_CHOICES = [
        (15, "15 minutes"),
        (60, "1 hour"),
        (1440, "1 day"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_limit")
    requests_per_minute = models.PositiveIntegerField(
        default=60,
        validators=[
            MinValueValidator(1, "Enter at least 1 request per minute."),
            MaxValueValidator(1000, "Enter 1000 or fewer requests per minute."),
        ],
    )
    monthly_budget_usd = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0.01"), "Enter a monthly budget of at least $0.01.")],
    )
    cache_enabled = models.BooleanField(default=True, help_text="Reuse the stored answer when the same prompt is sent again.")
    cache_ttl_minutes = models.PositiveIntegerField(choices=CACHE_TTL_CHOICES, default=60)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Limits for {self.user.username}"
