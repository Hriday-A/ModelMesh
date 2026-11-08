"""Adds the two providers the app uses today.

- Mock: the offline provider (MODELMESH_PROVIDER=mock). Free.
- UIUC Lumen: serves the three models the router chooses between. Prices are Lumen
  coins per 1M tokens and match router/migrations/0005 on feature/router.
"""

from decimal import Decimal

from django.db import migrations

PROVIDERS = [
    ("Mock (offline)", "mock", "", [("Mock echo", "mock-echo", "0", "0")]),
    ("UIUC Lumen", "lumen", "https://lumen.ncsa.illinois.edu/v1", [
        ("Ornith 1.0 35B", "ornith-1.0-35b", "0.05", "0.10"),
        ("DeepSeek V4 Flash", "deepseek-v4-flash", "0.16", "0.37"),
        ("GLM 5.3", "glm-5.3", "1.32", "4.25"),
    ]),
]


def seed(apps, schema_editor):
    Provider = apps.get_model("providers", "Provider")
    AIModel = apps.get_model("providers", "AIModel")
    for name, slug, url, models in PROVIDERS:
        provider, _ = Provider.objects.update_or_create(slug=slug, defaults={"name": name, "api_base_url": url})
        for model_name, model_id, price_in, price_out in models:
            AIModel.objects.update_or_create(
                model_id=model_id,
                defaults={"provider": provider, "name": model_name,
                          "input_price_per_m": Decimal(price_in), "output_price_per_m": Decimal(price_out)},
            )


def unseed(apps, schema_editor):
    apps.get_model("providers", "Provider").objects.filter(slug__in=[p[1] for p in PROVIDERS]).delete()


class Migration(migrations.Migration):
    dependencies = [("providers", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
