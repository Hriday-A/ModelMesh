# accounts: Hriday Agarwal

- **Status:** all four apps merged into `main` and tested together. README updated for the finished first draft.
- **Branch:** `main` (merges everyone's pull requests)
- **Wireframe screens:** 1–8 (Home, Sign up, Log in, Playground, History, Request detail, API Keys, Profile)
- **Last updated:** 2026-11-09

## Built so far

- **Models** (`accounts/models.py`):
  - `UserProfile`: one per user, created on sign-up by `accounts/signals.py`. Holds the organization and default priority.
  - `APIKey`: keys start with `mm_`. Only a SHA-256 hash is stored. The full key is shown once, keys can be revoked, and each user can have at most 5 active.
  - `RequestLog`: one row per prompt. Fields: user, key, source, priority, prompt, response, provider, model used, routing reason, status (`success`, `cached` or `error`), error message, input and output tokens, cost, latency, created time.
- **Services** (`accounts/services.py`): `run_prompt()`, `ProviderError`, `estimate_cost()` (one global price from environment variables), `mock_completion()`, `anthropic_completion()`, and the placeholder `default_router()`.
- **Pages:** `/` home, `/signup/`, `/login/`, `/logout/`, `/profile/`, `/keys/` and `/keys/<id>/revoke/`, `/playground/`, `/history/` (search, status, source and date filters, 20 rows per page), `/history/<id>/`.
- **JSON API:** `POST /api/chat` with `Authorization: Bearer mm_...`. Returns 401 for a bad key, 400 for a bad body, 502 when the provider fails.
- **Shared UI:** `templates/base.html` (its nav is built from `MODELMESH_NAV`), `templates/form_fields.html`, `static/css/main.css`.
- **Tests:** 23 in `accounts/tests.py`. These include the real-provider path with the SDK mocked, so they use no API key. Provider failures, including a missing key, show an error instead of crashing.

## P2-A3 tasks (due 2026-11-09)

- [x] `analytics`: in `INSTALLED_APPS`, `MODELMESH_NAV` and `modelmesh/urls.py`; merged (PR #1).
- [x] `providers` (PR #3) and `router` (PR #2): merged; conflicts in settings, URLs and CSS resolved by keeping both apps.
- [x] After each merge, run `python manage.py test` and try the Playground. On 2026-11-09 all 80 tests pass; one providers test was pinned to the mock route, since the router is now the default.
- [x] Full flow tested on 2026-11-09 without a Lumen key: the prompt goes through the trained classifier, is saved with its routing decision and a clear "No Lumen API key" error, and the Playground links to the explanation page. A live Lumen answer was checked on the router branch.

## Submission piece: GitHub and README (Requirement 5, 10 pts)

- [x] Update `README.md`: setup, environment variables, `migrate` for all apps, how to run the prototype and how to try the AI feature.
- [x] README updated for all four apps: Lumen key setup, environment variables, how the router works, and links to every document. `requirements.txt` includes the router's packages.
- [x] Link `docs/product_scope.md` from the README.
- [x] Link `docs/ai_plan.md` and `docs/roadmap.md` from the README.
- [x] Check that no `.env` file or key is committed (scanned all history on 2026-11-05). `*.bin`, `*.safetensors` and `*.pt` are in `.gitignore`. Scan again before submitting.
- [ ] 2026-11-08: clone the repo fresh and follow the README from scratch.
- [ ] 2026-11-09: submit the repository URL on Canvas. The repo is public.

## Used by

Every app reads `RequestLog` and extends `base.html`.
