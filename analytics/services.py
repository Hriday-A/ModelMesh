"""Usage numbers for the analytics pages, computed from accounts.RequestLog."""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

RANGE_CHOICES = [(7, "Last 7 days"), (30, "Last 30 days"), (90, "Last 90 days")]


def range_start(days):
    """First day of a range that ends today: 7 days is today and the 6 days before it."""
    return timezone.localdate() - timedelta(days=days - 1)


def logs_in_range(user, days):
    return user.request_logs.filter(created_at__date__gte=range_start(days))


def percent(part, whole):
    return round(100 * part / whole) if whole else 0


def usage_summary(user, days):
    """Tiles and chart data for the usage dashboard (Screen 13)."""
    logs = logs_in_range(user, days)
    totals = logs.aggregate(
        requests=Count("id"),
        cached=Count("id", filter=Q(status="cached")),
        cost=Sum("cost_usd"),
        avg_latency=Avg("latency_ms"),
    )

    counts = {
        row["day"]: row["requests"]
        for row in logs.annotate(day=TruncDate("created_at")).values("day").annotate(requests=Count("id"))
    }
    peak = max(counts.values(), default=0)
    first_day = range_start(days)
    per_day = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        requests = counts.get(day, 0)
        per_day.append({"day": day, "requests": requests, "height": percent(requests, peak)})

    per_model = list(
        logs.exclude(model_used="")
        .values("model_used")
        .annotate(requests=Count("id"), cost=Sum("cost_usd"))
        .order_by("-cost", "-requests")
    )
    top_cost = max((row["cost"] for row in per_model), default=0)
    for row in per_model:
        row["width"] = percent(row["cost"], top_cost)

    return {
        "requests": totals["requests"],
        "cost": totals["cost"] or Decimal("0"),
        "avg_latency_ms": round(totals["avg_latency"] or 0),
        "cache_hit_rate": percent(totals["cached"], totals["requests"]),
        "per_day": per_day,
        "first_day": first_day,
        "last_day": timezone.localdate(),
        "per_model": per_model,
    }


def month_summary(user, budget):
    """This month's spending against the budget, and cache hits (Screen 14)."""
    logs = user.request_logs.filter(created_at__date__gte=timezone.localdate().replace(day=1))
    totals = logs.aggregate(
        requests=Count("id"),
        hits=Count("id", filter=Q(status="cached")),
        paid=Count("id", filter=Q(status="success")),
        spend=Sum("cost_usd"),
    )
    spend = totals["spend"] or Decimal("0")
    average_paid = spend / totals["paid"] if totals["paid"] else Decimal("0")
    return {
        "spend": spend,
        "budget": budget,
        "used_pct": min(100, percent(spend, budget)),
        "hits": totals["hits"],
        "misses": totals["requests"] - totals["hits"],
        # ponytail: estimate that assumes each cache hit would have cost an average paid request;
        # store each answer's real cost with its cache entry once caching exists.
        "saved": average_paid * totals["hits"],
    }
