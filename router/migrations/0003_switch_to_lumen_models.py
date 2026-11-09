"""Replaces the Claude models with the three open-weight models served by Lumen.

Tiers follow total parameters (checked on each model's Hugging Face page):
  qwen3.6-35b-a3b  35B total, 3B active, FP8 weights   -> small
  deepseek-v4-flash 0731, 304B total                    -> medium
  glm-5.3          753B total                           -> large
Prices are Lumen "coins" per 1M tokens, from the Lumen models page. Latency stays
empty until run_benchmark measures it.
"""

from decimal import Decimal

from django.db import migrations

OLD_IDS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
MODELS = [
    ("Qwen3.6 35B-A3B", "qwen3.6-35b-a3b", 1, Decimal("0.19"), Decimal("1.14")),
    ("DeepSeek V4 Flash", "deepseek-v4-flash", 2, Decimal("0.16"), Decimal("0.37")),
    ("GLM 5.3", "glm-5.3", 3, Decimal("1.32"), Decimal("4.25")),
]


def switch(apps, schema_editor):
    RouterModel = apps.get_model("router", "RouterModel")
    RouterModel.objects.filter(model_id__in=OLD_IDS).delete()
    for name, model_id, tier, price_in, price_out in MODELS:
        RouterModel.objects.update_or_create(
            model_id=model_id,
            defaults={"name": name, "tier": tier, "provider": "lumen",
                      "input_price_per_m": price_in, "output_price_per_m": price_out},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("router", "0002_seed_claude_models")]

    operations = [migrations.RunPython(switch, noop)]
