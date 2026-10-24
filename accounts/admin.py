from django.contrib import admin

from .models import APIKey, RequestLog, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "organization", "default_priority", "created_at"]


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "prefix", "revoked", "created_at", "last_used_at"]
    list_filter = ["revoked"]
    readonly_fields = ["prefix", "hashed_key"]


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "source", "model_used", "status", "latency_ms", "cost_usd"]
    list_filter = ["status", "source", "provider"]
    search_fields = ["prompt"]
