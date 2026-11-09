# ModelMesh

**An intelligent AI gateway.** ModelMesh sits between an application and several AI models and chooses
which model answers each prompt, so simple prompts don't cost as much as hard ones and one model's
failure doesn't take an application down. It is built for students, student organizations and small
developer teams on small budgets. INFO 490 Project 2, Team ModelMesh (Team 7).

## Features

| App | What it does | Status |
|---|---|---|
| `accounts` | Sign-up and log-in, profiles, API keys, Playground, request history with search and filters, `POST /api/chat` JSON API | Working |
| `router` | The AI feature: a trained classifier predicts which model will answer each prompt well, then the router calls the best one for the user's priority and falls back to the next if it fails. Routing rules, weights, explanations and star feedback | Working |
| `providers` | Provider and model registry with per-model prices, load-balancing weights and health checks | Working |
| `analytics` | Usage dashboard, CSV export, quota and cache settings | Working. Limits and caching are saved but not enforced yet |

## Setup

You need Python 3.10 or newer. Check with `python3 --version`: on a Mac, the built-in `python3` is 3.9,
and `pip install` then fails with "No matching distribution found for anthropic". Install a newer Python
from python.org and create the environment with it, for example `python3.13 -m venv .venv`.

```bash
git clone https://github.com/Hriday-A/ModelMesh.git
cd ModelMesh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

On Windows, activate with `.venv\Scripts\activate`, use `python` instead of `python3`, and `copy` instead of `cp`.

- `pip install` takes a few minutes: the router's embedding model needs PyTorch.
- `migrate` creates a local SQLite database (`db.sqlite3`) with the tables for every app, and adds the
  three Lumen models and the providers they belong to.
- Open http://localhost:8000 and sign up. Staff accounts can also edit routing rules and providers;
  create one with `python manage.py createsuperuser`.

Run the tests with:

```bash
python manage.py test
```

## Environment variables

Put these in `.env` (copied from `.env.example` and never committed) or set them in your shell, which
takes priority. Only `LUMEN_API_KEY` is needed to get real answers.

| Variable | Default | Purpose |
|---|---|---|
| `LUMEN_API_KEY` | none | Key for UIUC Lumen, which serves the models the router chooses between. Create one in Lumen under Profile → API Keys |
| `LUMEN_BASE_URL` | `https://lumen.ncsa.illinois.edu/v1` | Lumen API address |
| `ROUTER_REASONING_EFFORT` | `high` | Thinking effort for the chosen model (`low`, `high` or `max`) |
| `ROUTER_MAX_TOKENS` | `12000` | Token limit per answer, including thinking |
| `ROUTER_TIMEOUT_SECONDS` | `120` | How long to wait for a model before trying the next one |
| `ROUTER_ARTIFACT_PATH` | `router/artifacts/router.joblib` | The trained router |
| `MODELMESH_ROUTER` | `router.services.route` | Function that picks the model. `accounts.services.default_router` uses the single-model route below instead |
| `MODELMESH_PROVIDER` | `mock` | For `default_router` only: `mock` runs offline, `anthropic` calls one Anthropic model |
| `ANTHROPIC_API_KEY`, `MODELMESH_DEFAULT_MODEL` | none | For `default_router` with `MODELMESH_PROVIDER=anthropic` |
| `DJANGO_SECRET_KEY` | development key | Set this to your own value for any deployment |
| `DJANGO_DEBUG` | `true` | Set to `false` for any deployment |

## Try the AI

1. Add your Lumen key to `.env` and restart the server. Lumen may need the campus network or VPN.
2. Log in, open **Playground**, type a prompt, choose a priority (Balanced, Cheapest, Fastest or Best
   quality) and click **Send**.
3. The answer shows the model the router chose, latency, tokens, cost and a one-line reason, for example
   the predicted chance of a good answer from each model. Click **Explain & rate this answer** to see
   every model's score and give the answer 1 to 5 stars; ratings adjust future choices.
4. Open **Routing** to test a prompt without calling any model and see which model would be picked.
   This works without a Lumen key.

The first request after a server start takes a few extra seconds while the embedding model loads. It is
downloaded once, about 90 MB, to the Hugging Face cache.

Without a key, Playground prompts are saved with status `error` and the message "No Lumen API key
found". To try the app fully offline, start it with `MODELMESH_ROUTER=accounts.services.default_router`
for labeled mock answers.

## How the router works

- **Classifier:** a small Hugging Face embedding model (`all-MiniLM-L6-v2`) turns each prompt into 384
  numbers. For each of the three models, a logistic regression predicts the chance of a good answer,
  and another predicts the task category.
- **Training data:** 200 public-benchmark prompts answered by all three models and judged by GPT-6 Astra.
  The trained file is committed at `router/artifacts/router.joblib`. If it is missing, the router falls
  back to keyword rules.
- **Choosing:** each model's chance of a good answer is combined with its measured cost and speed,
  weighted by the user's priority. Routing rules set by staff can override the choice for prompts with
  given keywords. If the chosen model fails, the next one is tried.
- **Preview API:** `POST /routing/api/preview` with `{"prompt": "...", "priority": "balanced"}` returns
  the model the router would pick, without calling it. It accepts a logged-in session or an `mm_` key.
- Costs are in Lumen coins, though the Playground and Usage pages show them with a "$" sign.

Full details: [docs/ai_plan.md](docs/ai_plan.md). Evaluation results: [docs/eval/router_eval.md](docs/eval/router_eval.md).
To rebuild the benchmark or retrain, follow [router/benchmark/README.md](router/benchmark/README.md).

## Project documents

- [Updated product scope](docs/product_scope.md)
- [AI implementation plan](docs/ai_plan.md)
- [Roadmap](docs/roadmap.md)
- [Router evaluation](docs/eval/router_eval.md)
- [Team build status](docs/status/README.md)

## API

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer mm_your_key" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain recursion", "priority": "cheapest"}'
```

Create a key on the **API Keys** page. `priority` is one of `balanced`, `cheapest`, `fastest`, `quality`
(optional; defaults to the user's profile setting). Returns 401 for a bad key, 400 for a bad body, 502 if
every model failed.

## For developers: how the apps plug in

**Request flow:** Playground page or `POST /api/chat` → `accounts.services.run_prompt()` →
`router.services.route()` → the chosen Lumen model → saved as an `accounts.RequestLog` row, with the
router's `RoutingDecision` saved next to it.

- **Router contract:** `route(prompt, priority)` returns
  `{"response", "provider", "model", "input_tokens", "output_tokens", "reason", "cached"}`
  (`reason` and `cached` are optional) and raises `accounts.services.ProviderError` on failure.
  `settings.MODELMESH_ROUTER` names the function to use.
- **Providers:** `providers.services.model_cost()` prices each request with its model's own prices.
  Model IDs must match between `providers.AIModel` and `router.RouterModel`.
- **Analytics:** reads `accounts.RequestLog` (user, model_used, status, tokens, cost_usd, latency_ms,
  created_at).
- **Pages:** extend `base.html` (`{% extends "base.html" %}`, fill `{% block content %}`), add URLs in
  `modelmesh/urls.py`, and add the nav link to `MODELMESH_NAV` in settings. Render forms with
  `{% include "form_fields.html" with form=form %}`.
