# analytics: Manojkumar Mohankumar

- **Status:** first version merged into `main` through PR #1 on 2026-11-03. Its 9 tests pass, along with the 18 accounts tests.
- **Branch:** `feature/analytics`
- **Wireframe screens:** 13 (Usage Dashboard), 14 (Quotas & Cache Settings)
- **Last updated:** 2026-11-03

## Built so far

- **Model** (`analytics/models.py`): `UsageLimit`, one per user (`user` one-to-one, `related_name="usage_limit"`). Fields:
  - `requests_per_minute`: 1–1000, default 60
  - `monthly_budget_usd`: at least $0.01, default 10.00
  - `cache_enabled`: default on
  - `cache_ttl_minutes`: 15, 60 or 1440; default 60
  - `updated_at`
  - Migration: `0001_initial`
- **Services** (`analytics/services.py`), all computed from the user's `accounts.RequestLog` rows:
  - `usage_summary(user, days)`: requests, total cost, average latency, cache hit rate, requests per day (every day in the range, including days with zero) and cost per model.
  - `month_summary(user, budget)`: this month's spending, percent of the budget used, cache hits and misses, and estimated savings.
  - Helpers: `logs_in_range(user, days)`, `range_start(days)`, and `RANGE_CHOICES` (7, 30 or 90 days).
- **Forms** (`analytics/forms.py`):
  - `RangeForm`: the range select. Invalid values fall back to 7 days.
  - `UsageLimitForm`: its error messages come from the model's validators.
- **Pages** (all require log-in):
  - `/usage/` (`analytics:dashboard`): range select, four tiles, requests-per-day bars, cost-by-model bars, a "Download CSV" link and a "Quotas & cache settings →" button.
  - `/usage/export.csv?days=7` (`analytics:export_csv`): the user's requests in the range. Prompts and answers are left out.
  - `/usage/limits/` (`analytics:limits`): the settings form, this month's spending with a progress bar, and cache hits, misses and estimated savings. Saving shows "Settings saved."
- **Wiring:**
  - `"analytics"` in `INSTALLED_APPS`
  - `("Usage", "analytics:dashboard")` in `MODELMESH_NAV`
  - `path("usage/", include("analytics.urls"))` in `modelmesh/urls.py`
  - Styles added at the end of `static/css/main.css`
- **Admin:** `UsageLimit` is registered.
- **Tests** (`analytics/tests.py`, 9 tests):
  - log-in is required
  - totals use only the user's own requests
  - the range filter works
  - a bad range falls back to 7 days
  - the CSV has only the user's own rows
  - the first visit creates default settings
  - valid settings are saved
  - bad values are rejected
  - the month summary counts cache hits

## Not built yet (P2-A4)

- Enforcing the rate limit and monthly budget on `/api/chat` and the Playground (HTTP 429).
- The response cache itself (Redis), and "Clear cache".
- Clicking a model's bar to open History filtered by that model. History has no model filter yet.
- Load tests.

## P2-A3 checklist

- [x] App, model, migration, services, forms, views, URLs, templates, admin, tests
- [x] Wired into settings, URLs and the nav bar
- [x] `docs/product_scope.md` drafted
- [ ] Confirm the "Changes since P2-A2" section after the team's router decision
- [x] Committed, pushed and merged into `main` (PR #1)

## Submission piece: updated product scope (Requirement 1, 15 pts)

Draft: [`docs/product_scope.md`](../product_scope.md). Its "Changes since P2-A2" section says "No significant changes" until the team decides how the router uses AI.

## Depends on / used by

- **Depends on:** `accounts.RequestLog`, read only.
- **Used by:** the nav bar ("Usage" link). Later, the router or `run_prompt()` can read `user.usage_limit` to enforce limits and caching.
