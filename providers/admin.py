from django.contrib import admin

from .models import AIModel, Provider


class AIModelInline(admin.TabularInline):
    model = AIModel
    extra = 0


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "api_base_url", "enabled", "health_status", "last_checked_at"]
    list_filter = ["enabled", "health_status"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [AIModelInline]


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ["name", "model_id", "provider", "input_price_per_m", "output_price_per_m", "weight", "enabled"]
    list_filter = ["provider", "enabled"]
    search_fields = ["name", "model_id"]
