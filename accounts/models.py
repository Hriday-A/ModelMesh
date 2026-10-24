import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """Extra settings for each user. Created automatically on sign-up (see signals.py)."""

    PRIORITY_CHOICES = [
        ("balanced", "Balanced"),
        ("cheapest", "Cheapest"),
        ("fastest", "Fastest"),
        ("quality", "Best quality"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    organization = models.CharField(max_length=100, blank=True, help_text="Team, RSO or company (optional).")
    default_priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="balanced")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


class APIKey(models.Model):
    """A key that lets a program call /api/chat.

    Only a SHA-256 hash of the key is stored, so a leaked database does not leak
    usable keys. The full key is shown to the user exactly once, when created.
    """

    KEY_PREFIX = "mm_"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=60)
    prefix = models.CharField(max_length=12, help_text="First characters of the key, shown so users can tell keys apart.")
    hashed_key = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @staticmethod
    def hash_key(raw_key):
        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def generate(cls, user, name):
        """Create a key and return (api_key, raw_key). raw_key is never stored."""
        raw_key = cls.KEY_PREFIX + secrets.token_urlsafe(32)
        api_key = cls.objects.create(
            user=user,
            name=name,
            prefix=raw_key[:10],
            hashed_key=cls.hash_key(raw_key),
        )
        return api_key, raw_key

    @classmethod
    def authenticate(cls, raw_key):
        """Return the active APIKey matching raw_key, or None."""
        if not raw_key or not raw_key.startswith(cls.KEY_PREFIX):
            return None
        api_key = cls.objects.select_related("user").filter(
            hashed_key=cls.hash_key(raw_key), revoked=False
        ).first()
        if api_key:
            api_key.last_used_at = timezone.now()
            api_key.save(update_fields=["last_used_at"])
        return api_key


class RequestLog(models.Model):
    """One prompt sent through ModelMesh and what happened to it.

    The Router (Part 3) and Analytics (Part 4) apps read from this table.
    """

    STATUS_CHOICES = [
        ("success", "Success"),
        ("cached", "Cached"),
        ("error", "Error"),
    ]
    SOURCE_CHOICES = [
        ("playground", "Playground"),
        ("api", "API"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="request_logs")
    api_key = models.ForeignKey(APIKey, on_delete=models.SET_NULL, null=True, blank=True, related_name="request_logs")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    priority = models.CharField(max_length=20, choices=UserProfile.PRIORITY_CHOICES, default="balanced")
    prompt = models.TextField()
    response = models.TextField(blank=True)
    provider = models.CharField(max_length=50, blank=True)
    model_used = models.CharField(max_length=100, blank=True)
    routing_reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.user.username} → {self.model_used or 'n/a'} ({self.status})"

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens
