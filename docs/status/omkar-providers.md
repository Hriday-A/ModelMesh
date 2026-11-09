# providers: Omkar Chougule

- **Status:** merged into `main` (PR #3)
- **Branch:** `feature/providers`
- **Wireframe screens:** 9 (Providers & Health), 10 (Add / Edit Provider)
- **Last updated:** 2026-11-08

## P2-A3 tasks (due 2026-11-09)

- [x] `providers` app
- [x] Models:
  - `Provider`: name, short ID (`slug`, matches `RequestLog.provider`), API base URL, enabled, health status, health detail, last checked time.
  - `AIModel`: linked to a `Provider`, with `model_id`, `input_price_per_m`, `output_price_per_m`, `weight` (0–100) and `enabled`. The field names match `router.RouterModel` so the two tables can be merged later.
- [x] Migrations, and admin pages for both models. Migration `0002` adds the Mock provider and UIUC Lumen with the router's three models and prices.
- [x] Providers list page (Screen 9) at `/providers/`. It shows each provider's health, models and prices, and its answered requests and average latency over the last 24 hours. Staff users get "Check now" and "Edit".
- [x] Add / Edit provider form (Screen 10) at `/providers/new/` and `/providers/<id>/edit/`. One page edits the provider and its models. Only staff users can use it. It checks that required fields are filled, costs aren't negative, and the weight is from 0 to 100.
- [x] Moved `anthropic_completion()` into `providers/services.py`. `accounts.services.estimate_cost()` now uses the model's own prices from `AIModel`. Models that aren't registered fall back to the `MODELMESH_*_PRICE` settings.
- [x] Added the app to `INSTALLED_APPS`, a "Providers" link to `MODELMESH_NAV`, and its URLs to `modelmesh/urls.py`.
- [x] 19 tests in `providers/tests.py`.
- [x] Open the pull request to `main`. Merged as PR #3.

## How health works

"Check now" sends a GET to the provider's base URL. Any answer below HTTP 500 (including 401 when no key is sent) counts as healthy. A 5xx answer counts as degraded. No answer counts as down. The mock provider has no URL and is always healthy. Failed requests are saved without a provider, so the error rate can't be computed from `RequestLog` yet.

## Submission piece: roadmap table (Requirement 4, 15 pts)

- [x] `docs/roadmap.md` with Task, Current Status, Responsible Member and Expected Completion for all six rows.
- [x] After the `providers` and `router` PRs merged, change "On branch" to "Merged" (done 2026-11-09).

## Notes for teammates

- **Srinath:** `router.RouterModel` and `providers.AIModel` overlap. For the draft they stay separate. After 2026-11-09, `RouterModel` could become `AIModel` or link to it. The router's signal still overwrites `RequestLog.cost_usd` with its own price, so the two don't conflict.
- **Merge conflicts:** `feature/router` also edits `INSTALLED_APPS`, `MODELMESH_NAV`, `modelmesh/urls.py` and the end of `static/css/main.css`. Whichever PR merges second needs to keep both sets of lines.

## Depends on / used by

- **Depends on:** `accounts.RequestLog` and `accounts.services.ProviderError`.
- **Used by:** `accounts.services.estimate_cost()` and `default_router()`. Later, the `router` app.
