from django.contrib import admin

from .models import UsageLimit


@admin.register(UsageLimit)
class UsageLimitAdmin(admin.ModelAdmin):
    list_display = ["user", "requests_per_minute", "monthly_budget_usd", "cache_enabled", "cache_ttl_minutes", "updated_at"]
