import urllib.error
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import RequestLog
from accounts.services import estimate_cost, run_prompt

from .forms import AIModelForm
from .models import AIModel, Provider
from .services import check_health

User = get_user_model()


def model_data(**overrides):
    data = {"name": "Test model", "model_id": "test-model", "input_price_per_m": "1.00",
            "output_price_per_m": "2.00", "weight": "50", "enabled": "on"}
    data.update(overrides)
    return data


class SeedTests(TestCase):
    def test_mock_and_lumen_are_seeded(self):
        self.assertEqual(set(Provider.objects.values_list("slug", flat=True)), {"mock", "lumen"})
        self.assertEqual(AIModel.objects.filter(provider__slug="lumen").count(), 3)


class AIModelFormTests(TestCase):
    def test_valid(self):
        self.assertTrue(AIModelForm(model_data()).is_valid())

    def test_negative_price_rejected(self):
        form = AIModelForm(model_data(input_price_per_m="-1"))
        self.assertFalse(form.is_valid())
        self.assertIn("can't be negative", form.errors["input_price_per_m"][0])

    def test_weight_must_be_0_to_100(self):
        for bad in ["101", "-1"]:
            form = AIModelForm(model_data(weight=bad))
            self.assertFalse(form.is_valid(), bad)
            self.assertIn("weight", form.errors)

    def test_required_fields(self):
        form = AIModelForm(model_data(name="", model_id=""))
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn("model_id", form.errors)


class PricingTests(TestCase):
    def test_registered_model_uses_its_own_prices(self):
        # glm-5.3 is seeded at 1.32 in / 4.25 out per 1M tokens.
        self.assertEqual(estimate_cost("glm-5.3", 1_000_000, 1_000_000), Decimal("5.57"))

    def test_unknown_model_falls_back_to_settings(self):
        with self.settings(MODELMESH_INPUT_PRICE="3", MODELMESH_OUTPUT_PRICE="15"):
            self.assertEqual(estimate_cost("not-registered", 1_000_000, 0), Decimal("3"))

    def test_mock_prompt_still_works(self):
        user = User.objects.create_user("u", password="pw-12345-long")
        log = run_prompt(user, "Hello there", source="playground")
        self.assertEqual(log.status, "success")
        self.assertEqual(log.cost_usd, 0)


class HealthCheckTests(TestCase):
    def setUp(self):
        self.lumen = Provider.objects.get(slug="lumen")

    def test_mock_is_healthy_without_network(self):
        mock_provider = Provider.objects.get(slug="mock")
        with mock.patch("urllib.request.urlopen") as urlopen:
            self.assertEqual(check_health(mock_provider), "healthy")
            urlopen.assert_not_called()

    def test_401_counts_as_reachable(self):
        error = urllib.error.HTTPError(self.lumen.api_base_url, 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            self.assertEqual(check_health(self.lumen), "healthy")

    def test_server_error_is_degraded(self):
        error = urllib.error.HTTPError(self.lumen.api_base_url, 503, "Unavailable", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            self.assertEqual(check_health(self.lumen), "degraded")

    def test_no_connection_is_down(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
            self.assertEqual(check_health(self.lumen), "down")
        self.lumen.refresh_from_db()
        self.assertEqual(self.lumen.health_status, "down")
        self.assertIsNotNone(self.lumen.last_checked_at)


class ProviderViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member", password="pw-12345-long")
        self.staff = User.objects.create_user("admin", password="pw-12345-long", is_staff=True)

    def formset_post(self, **model_overrides):
        data = {"name": "Anthropic", "slug": "anthropic", "api_base_url": "https://api.anthropic.com",
                "enabled": "on", "models-TOTAL_FORMS": "1", "models-INITIAL_FORMS": "0"}
        data.update({f"models-0-{k}": v for k, v in model_data(**model_overrides).items()})
        return data

    def test_list_requires_login(self):
        response = self.client.get(reverse("providers:list"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_providers_and_stats(self):
        RequestLog.objects.create(user=self.user, source="playground", prompt="hi", provider="lumen",
                                  model_used="glm-5.3", status="success", latency_ms=200)
        self.client.force_login(self.user)
        response = self.client.get(reverse("providers:list"))
        self.assertContains(response, "UIUC Lumen")
        self.assertContains(response, "deepseek-v4-flash")
        self.assertContains(response, "200 ms")
        self.assertNotContains(response, "Add provider")  # members can't edit

    def test_members_cannot_add(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("providers:create")).status_code, 403)

    def test_staff_can_add_provider_with_model(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("providers:create"), self.formset_post())
        self.assertRedirects(response, reverse("providers:list"))
        provider = Provider.objects.get(slug="anthropic")
        self.assertEqual(provider.models.get().weight, 50)

    def test_invalid_model_shows_errors_and_saves_nothing(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("providers:create"), self.formset_post(output_price_per_m="-5"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "can&#x27;t be negative")
        self.assertFalse(Provider.objects.filter(slug="anthropic").exists())

    def test_staff_can_edit(self):
        lumen = Provider.objects.get(slug="lumen")
        self.client.force_login(self.staff)
        response = self.client.get(reverse("providers:edit", args=[lumen.pk]))
        self.assertContains(response, "glm-5.3")

    def test_check_now(self):
        mock_provider = Provider.objects.get(slug="mock")
        self.client.force_login(self.staff)
        response = self.client.post(reverse("providers:check", args=[mock_provider.pk]))
        self.assertEqual(response.status_code, 302)
        mock_provider.refresh_from_db()
        self.assertEqual(mock_provider.health_status, "healthy")
