import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count

CATEGORY_CHOICES = [
    ("coding", "Coding"),
    ("math", "Math & reasoning"),
    ("summarization", "Summarizing"),
    ("writing", "Writing"),
    ("extraction", "Extraction"),
    ("chat", "Simple chat"),
]


class RouterModel(models.Model):
    """A model the router can choose. Prices are Lumen coins per 1M tokens."""

    TIER_CHOICES = [(1, "Small"), (2, "Medium"), (3, "Large")]

    name = models.CharField(max_length=60)
    model_id = models.CharField(max_length=100, unique=True)
    provider = models.CharField(max_length=50, default="lumen")
    tier = models.PositiveSmallIntegerField(choices=TIER_CHOICES)
    input_price_per_m = models.DecimalField(max_digits=8, decimal_places=4)
    output_price_per_m = models.DecimalField(max_digits=8, decimal_places=4)
    # Median latency measured by run_benchmark. Empty until the benchmark has run.
    avg_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    # Median coins per answer measured by run_benchmark (thinking models differ a lot in
    # how many tokens they write, so list price alone misleads). Empty until measured.
    avg_cost = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["tier"]

    def __str__(self):
        return self.name

    @property
    def short_name(self):
        return self.name.removeprefix("Claude ")

    def cost(self, input_tokens, output_tokens):
        return (
            self.input_price_per_m * input_tokens + self.output_price_per_m * output_tokens
        ) / Decimal(1_000_000)


class RoutingRule(models.Model):
    """Admin override: prompts containing any keyword go to the preferred model first."""

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    keywords = models.CharField(
        max_length=255, help_text="Comma-separated, case-insensitive. Example: traceback, stack trace, segfault"
    )
    preferred_model = models.ForeignKey(RouterModel, on_delete=models.PROTECT, related_name="preferred_rules")
    fallback_model = models.ForeignKey(
        RouterModel, on_delete=models.PROTECT, null=True, blank=True, related_name="fallback_rules"
    )
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "id"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.keywords}"

    def keyword_list(self):
        return [k.strip().lower() for k in self.keywords.split(",") if k.strip()]

    def matches(self, prompt):
        """The first keyword found as a whole word or phrase ("hi" matches "hi there", not "this")."""
        text = prompt.lower()
        return next((k for k in self.keyword_list() if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text)), None)

    def clean(self):
        if not self.keyword_list():
            raise ValidationError({"keywords": "Add at least one keyword."})
        if self.fallback_model_id and self.fallback_model_id == self.preferred_model_id:
            raise ValidationError({"fallback_model": "The fallback must be a different model."})

    def learned_score(self):
        """Average star rating on requests this rule routed, as (average, count)."""
        stats = Feedback.objects.filter(request_log__routing_decision__rule=self).aggregate(
            avg=Avg("stars"), n=Count("id")
        )
        return stats["avg"], stats["n"]


class RoutingSettings(models.Model):
    """One row of admin-tunable knobs (Screen 11 sliders)."""

    quality_weight = models.FloatField(default=1.0, validators=[MinValueValidator(0), MaxValueValidator(2)])
    cost_weight = models.FloatField(default=1.0, validators=[MinValueValidator(0), MaxValueValidator(2)])
    speed_weight = models.FloatField(default=1.0, validators=[MinValueValidator(0), MaxValueValidator(2)])
    confidence_threshold = models.FloatField(
        default=0.6,
        validators=[MinValueValidator(0.3), MaxValueValidator(0.95)],
        help_text="A model is only trusted if its chance of a good answer is at least this high.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "routing settings"

    def __str__(self):
        return "Routing settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class RoutingDecision(models.Model):
    """Why the router picked a model for one request. Shown on Screen 12."""

    CLASSIFIER_CHOICES = [
        ("trained", "Trained classifier"),
        ("keyword_fallback", "Keyword fallback"),
    ]

    request_log = models.OneToOneField(
        "accounts.RequestLog", on_delete=models.CASCADE, related_name="routing_decision"
    )
    chosen_model = models.ForeignKey(RouterModel, on_delete=models.SET_NULL, null=True, blank=True)
    rule = models.ForeignKey(RoutingRule, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    classifier_used = models.CharField(max_length=20, choices=CLASSIFIER_CHOICES)
    # {model_id: {"p_good", "quality", "cost", "speed", "total"}} for every candidate.
    scores = models.JSONField(default=dict)
    # Models tried in order, with the error for each one that failed.
    attempts = models.JSONField(default=list)
    fallback_used = models.BooleanField(default=False)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    saved_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Decision for request #{self.request_log_id}"


class Feedback(models.Model):
    """A user's star rating of one answer. Feeds the learned adjustment in the router."""

    request_log = models.OneToOneField("accounts.RequestLog", on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="routing_feedback")
    stars = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.stars}★ on request #{self.request_log_id}"
