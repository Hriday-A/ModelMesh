# ModelMesh

An AI gateway that picks the best model for each prompt. INFO 490 team project.

| App | What it does |
|---|---|
| `accounts` | Sign-up/login, API keys, Playground, request history, `/api/chat`, shared `base.html` |
| `providers` | Provider/model registry, load balancing, failover, health checks |
| `router` | Prompt analysis, model scoring, feedback learning |
| `analytics` | Redis cache, rate limits, usage dashboard, load tests |

## Run it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://localhost:8000 and sign up. Run tests with `python manage.py test`.

By default answers come from a **mock provider** (no API key needed). To get real answers from a model:

```bash
export ANTHROPIC_API_KEY=your-api-key
export MODELMESH_PROVIDER=anthropic
export MODELMESH_DEFAULT_MODEL=your-model-id
export MODELMESH_INPUT_PRICE=0      # optional: USD per 1M input tokens
export MODELMESH_OUTPUT_PRICE=0     # optional: USD per 1M output tokens
python manage.py runserver
```

## How the other apps plug in

**Request flow:** `Playground page or POST /api/chat` → `accounts.services.run_prompt()` → router function → provider → saved as a `RequestLog` row.

- **Router:** write a function `route(prompt, priority)` that returns
  `{"response", "provider", "model", "input_tokens", "output_tokens", "reason", "cached"}`
  (`reason` and `cached` are optional) and raises `accounts.services.ProviderError` on failure.
  Then set `MODELMESH_ROUTER = "router.services.route"` in `modelmesh/settings.py`.
- **Providers:** the router calls your load balancer/failover code to actually reach a model.
  `accounts.services.anthropic_completion()` is an example provider call you can move into your app.
- **Analytics:** read from `accounts.models.RequestLog` (user, model_used, status, tokens,
  cost_usd, latency_ms, created_at). Cache hits can return `"cached": True` from the router, and they
  are logged with status `cached`.
- **Everyone:** extend `base.html` (`{% extends "base.html" %}`, fill `{% block content %}`), add your
  URLs in `modelmesh/urls.py`, and add your nav link to `MODELMESH_NAV` in settings.
  Reuse `{% include "form_fields.html" with form=form %}` for forms.

## API

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer mm_your_key" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain recursion", "priority": "cheapest"}'
```

`priority` is one of `balanced`, `cheapest`, `fastest`, `quality` (optional; defaults to the user's
profile setting). Returns 401 for a bad key, 400 for a bad body, 502 if every provider failed.

## Local test account

A test account (`demo` / `demo-pass-2026x`) was created in the local `db.sqlite3` during development.
It is not committed. Make your own by signing up.
