from django.contrib import admin

from .models import Feedback, RouterModel, RoutingDecision, RoutingRule, RoutingSettings


@admin.register(RouterModel)
class RouterModelAdmin(admin.ModelAdmin):
    list_display = ["name", "model_id", "tier", "input_price_per_m", "output_price_per_m", "avg_latency_ms", "enabled"]
    list_editable = ["enabled"]


@admin.register(RoutingRule)
class RoutingRuleAdmin(admin.ModelAdmin):
    list_display = ["category", "keywords", "preferred_model", "fallback_model", "enabled"]
    list_filter = ["category", "enabled"]


@admin.register(RoutingSettings)
class RoutingSettingsAdmin(admin.ModelAdmin):
    list_display = ["quality_weight", "cost_weight", "speed_weight", "confidence_threshold", "updated_at"]


@admin.register(RoutingDecision)
class RoutingDecisionAdmin(admin.ModelAdmin):
    list_display = ["request_log", "chosen_model", "category", "classifier_used", "fallback_used", "cost_usd", "saved_usd"]
    list_filter = ["category", "classifier_used", "fallback_used"]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["request_log", "user", "stars", "created_at"]
    list_filter = ["stars"]
