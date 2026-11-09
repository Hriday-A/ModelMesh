"""Adds the three Claude models the router chooses between.

Prices are Anthropic's list prices in USD per 1M tokens (Haiku 5.5: prompts up
to 100K tokens). Latency stays empty until run_benchmark measures it.
"""

from decimal import Decimal

from django.db import migrations

MODELS = [
    ("Claude Haiku 5.5", "claude-haiku-5-5", 1, Decimal("0.10"), Decimal("0.50")),
    ("Claude Sonnet 5.5", "claude-sonnet-5-5", 2, Decimal("2.00"), Decimal("10.00")),
    ("Claude Opus 5.5", "claude-opus-5-5", 3, Decimal("4.00"), Decimal("20.00")),
]


def add_models(apps, schema_editor):
    RouterModel = apps.get_model("router", "RouterModel")
    for name, model_id, tier, price_in, price_out in MODELS:
        RouterModel.objects.update_or_create(
            model_id=model_id,
            defaults={"name": name, "tier": tier, "input_price_per_m": price_in, "output_price_per_m": price_out},
        )


def remove_models(apps, schema_editor):
    apps.get_model("router", "RouterModel").objects.filter(model_id__in=[m[1] for m in MODELS]).delete()


class Migration(migrations.Migration):
    dependencies = [("router", "0001_initial")]

    operations = [migrations.RunPython(add_models, remove_models)]
