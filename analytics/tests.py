import csv
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RequestLog

from .models import UsageLimit


class AnalyticsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", "alice@illinois.edu", "s3cure-pass-123")
        self.other = User.objects.create_user("bob", "bob@illinois.edu", "s3cure-pass-123")
        self.add_log(self.user, "success", "model-a", "0.002000", 400)
        self.add_log(self.user, "cached", "model-a", "0", 10)
        self.add_log(self.user, "success", "model-b", "0.010000", 900)
        self.add_log(self.other, "success", "model-a", "5.000000", 100)
        self.client.force_login(self.user)

    def add_log(self, user, status, model, cost, latency, days_ago=0):
        log = RequestLog.objects.create(
            user=user, source="api", prompt="hi", status=status,
            model_used=model, cost_usd=Decimal(cost), latency_ms=latency,
        )
        if days_ago:  # created_at is set on insert, so move it afterwards
            RequestLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
        return log


class DashboardTests(AnalyticsTestCase):
    def test_requires_login(self):
        self.client.logout()
        url = reverse("analytics:dashboard")
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_totals_use_only_own_requests(self):
        summary = self.client.get(reverse("analytics:dashboard")).context["summary"]
        self.assertEqual(summary["requests"], 3)
        self.assertEqual(summary["cost"], Decimal("0.012"))
        self.assertEqual(summary["avg_latency_ms"], 437)
        self.assertEqual(summary["cache_hit_rate"], 33)
        self.assertEqual([row["model_used"] for row in summary["per_model"]], ["model-b", "model-a"])
        self.assertEqual(summary["per_day"][-1]["requests"], 3)

    def test_range_filter(self):
        self.add_log(self.user, "success", "model-a", "0.001000", 300, days_ago=10)
        week = self.client.get(reverse("analytics:dashboard")).context
        month = self.client.get(reverse("analytics:dashboard"), {"days": 30}).context
        self.assertEqual((week["days"], week["summary"]["requests"]), (7, 3))
        self.assertEqual((month["days"], month["summary"]["requests"]), (30, 4))
        self.assertEqual(len(month["summary"]["per_day"]), 30)

    def test_bad_range_falls_back_to_7_days(self):
        response = self.client.get(reverse("analytics:dashboard"), {"days": "abc"})
        self.assertEqual(response.context["days"], 7)

    def test_csv_has_only_own_rows(self):
        response = self.client.get(reverse("analytics:export_csv"), {"days": 7})
        self.assertEqual(response["Content-Type"], "text/csv")
        rows = list(csv.reader(response.content.decode().splitlines()))
        self.assertEqual(rows[0][:2], ["created_at", "source"])
        self.assertEqual(len(rows), 4)
        self.assertNotIn("5.000000", response.content.decode())


class LimitsTests(AnalyticsTestCase):
    def post(self, **overrides):
        data = {"requests_per_minute": 30, "monthly_budget_usd": "5.00", "cache_enabled": "on", "cache_ttl_minutes": 15}
        data.update(overrides)
        return self.client.post(reverse("analytics:limits"), data, follow=True)

    def test_first_visit_creates_defaults(self):
        response = self.client.get(reverse("analytics:limits"))
        limit = UsageLimit.objects.get(user=self.user)
        self.assertEqual((limit.requests_per_minute, limit.monthly_budget_usd), (60, Decimal("10.00")))
        self.assertContains(response, "$0.01 of $10.00")

    def test_valid_settings_are_saved(self):
        response = self.post()
        self.assertContains(response, "Settings saved.")
        limit = UsageLimit.objects.get(user=self.user)
        self.assertEqual((limit.requests_per_minute, limit.monthly_budget_usd, limit.cache_ttl_minutes), (30, Decimal("5.00"), 15))

    def test_bad_values_are_rejected(self):
        response = self.post(requests_per_minute=0, monthly_budget_usd="-1")
        self.assertContains(response, "Enter at least 1 request per minute.")
        self.assertContains(response, "Enter a monthly budget of at least $0.01.")
        self.assertContains(response, "of $10.00")  # the saved budget, not the rejected one
        self.assertEqual(UsageLimit.objects.get(user=self.user).monthly_budget_usd, Decimal("10.00"))

    def test_month_summary_counts_cache_hits(self):
        month = self.client.get(reverse("analytics:limits")).context["month"]
        self.assertEqual((month["hits"], month["misses"]), (1, 2))
        self.assertEqual(month["saved"], Decimal("0.006"))  # one hit x average paid cost (0.012 / 2)
