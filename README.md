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

Prompts go through the **smart router** (`router` app), which picks a small, medium or
large open-weight model (Ornith 1.0 35B, DeepSeek V4 Flash, GLM 5.3) served by UIUC's
Lumen, and calls only that model. The server needs one Lumen key; end users never do (they
log in, or use a ModelMesh `mm_` key for the API). Put the key in `.env` (copy
`.env.example`; `.env` is git-ignored):

```bash
cp .env.example .env     # then set LUMEN_API_KEY=... in .env
python manage.py runserver
```

Thinking effort is `high` (`ROUTER_REASONING_EFFORT` in `.env`). Lumen may need the
campus network or VPN. Costs are in Lumen coins. Without a key, prompts are saved as errors
("No Lumen API key found"). To use the
old single-model mock instead: `export MODELMESH_ROUTER=accounts.services.default_router`.

### Smart router

- Screens: **Routing** in the nav (`/routing/`) for rules, weights and a dry-run test
  prompt; **My routed requests** → **Explain & rate** for why a model was chosen and star
  feedback. Only staff users can edit rules and weights
  (`python manage.py createsuperuser`).
- Preview API: `POST /routing/api/preview` with `{"prompt": "...", "priority": "balanced"}`
  returns the model the router would pick, without calling it.
- Until it is trained, the router uses keyword rules. To train it on real benchmark data,
  follow [router/benchmark/README.md](router/benchmark/README.md). How it works:
  [docs/ai_plan.md](docs/ai_plan.md).
- The first request after a server start takes a few extra seconds while the embedding
  model loads (downloaded once, about 90MB, to the Hugging Face cache).

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
