# ModelMesh

**An intelligent AI gateway.** ModelMesh sits between an application and several AI providers and chooses
which model answers each prompt, so simple prompts don't cost as much as hard ones and one provider's
outage doesn't take an application down. It is built for students, student organizations and small
developer teams on small budgets. INFO 490 Project 2, Team ModelMesh (Team 7).

## Features

| App | What it does | Status |
|---|---|---|
| `accounts` | Sign-up and log-in, profiles, API keys, Playground, request history with search and filters, `POST /api/chat` JSON API | Working |
| `analytics` | Usage dashboard, CSV export, quota and cache settings | Working. Limits and caching are saved but not enforced yet |
| `providers` | Provider and model registry, prices, failover | Planned |
| `router` | Prompt classification, model scoring, feedback | Planned |

Until `router` and `providers` are merged, every prompt takes one default route, and answers come from a
built-in mock unless you configure a real model (see [Try the AI](#try-the-ai)).

## Setup

You need Python 3.10 or newer.

```bash
git clone https://github.com/Hriday-A/ModelMesh.git
cd ModelMesh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

On Windows, activate with `.venv\Scripts\activate` and use `python` instead of `python3`.

`migrate` creates a local SQLite database (`db.sqlite3`) with the tables for every app. Open
http://localhost:8000 and sign up; no API key is needed. To use the Django admin, also run
`python manage.py createsuperuser`.

Run the tests with:

```bash
python manage.py test
```

## Environment variables

All of these are optional. Set them in your shell before `runserver`. The app doesn't load `.env` files.

| Variable | Default | Purpose |
|---|---|---|
| `MODELMESH_PROVIDER` | `mock` | `mock` runs offline; `anthropic` calls a real model |
| `ANTHROPIC_API_KEY` | none | Provider API key, needed when the provider is `anthropic` |
| `MODELMESH_DEFAULT_MODEL` | none | Model ID to call, needed when the provider is `anthropic` |
| `MODELMESH_INPUT_PRICE` | `0` | USD per 1M input tokens, used to estimate cost |
| `MODELMESH_OUTPUT_PRICE` | `0` | USD per 1M output tokens, used to estimate cost |
| `MODELMESH_ROUTER` | `accounts.services.default_router` | Function that picks the model for each prompt |
| `DJANGO_SECRET_KEY` | development key | Set this to your own value for any deployment |
| `DJANGO_DEBUG` | `true` | Set to `false` for any deployment |

Never commit API keys or `.env` files.

## Try the AI

1. Log in and open **Playground**.
2. Type a prompt, choose a priority (Balanced, Cheapest, Fastest or Best quality) and click **Send**.
3. The answer appears with the model used, latency, tokens, cost and "Why this model?". It is also saved
   to **History** and counted on the **Usage** page.

With the default settings the answer is a labeled mock response. For real answers, restart the server with:

```bash
export MODELMESH_PROVIDER=anthropic
export ANTHROPIC_API_KEY=your-api-key
export MODELMESH_DEFAULT_MODEL=your-model-id
python manage.py runserver
```

If the key or model is missing or the provider fails, the Playground shows the error and saves the request
with status `error`; `POST /api/chat` returns 502.

## Project documents

- [Updated product scope](docs/product_scope.md)
- [Team build status](docs/status/README.md)

## For developers: how the apps plug in

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
