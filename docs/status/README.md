# ModelMesh build status

Read this first. It records what each team member is building and how far each build has got. There is one status file per app. When you finish a task, tick it in your file and update its "Last updated" date.

Last updated: 2026-11-03

## The project

ModelMesh is a Django 5.1 web app: an AI gateway that picks a model for each prompt, switches providers when one fails, and tracks usage, limits and caching. INFO 490 Project 2, Team ModelMesh (Team 7): Hriday Agarwal, Manojkumar Mohankumar, Omkar Chougule, Srinath Venkatesh.

## Builds

| App | Owner | Wireframe screens | Status | Details |
|---|---|---|---|---|
| `accounts` | Hriday Agarwal | 1–8 | Built in Part 1. P2-A3 integration and README work not started. | [hriday-accounts.md](hriday-accounts.md) |
| `providers` | Omkar Chougule | 9–10 | Not started | [omkar-providers.md](omkar-providers.md) |
| `router` | Srinath Venkatesh | 11–12 | Not started | [srinath-router.md](srinath-router.md) |
| `analytics` | Manojkumar Mohankumar | 13–14 | First version built on `feature/analytics`. Not merged yet. | [manoj-analytics.md](manoj-analytics.md) |

## How the apps connect

- Every prompt follows one path: the Playground page or `POST /api/chat` → `accounts.services.run_prompt()` → the router function named in `settings.MODELMESH_ROUTER` → a provider → one saved `accounts.models.RequestLog` row.
- The router contract: `route(prompt, priority)` returns `{"response", "provider", "model", "input_tokens", "output_tokens", "reason", "cached"}` (`reason` and `cached` are optional) and raises `accounts.services.ProviderError` on failure.
- `priority` is one of `balanced`, `cheapest`, `fastest`, `quality`.
- Each app adds its nav link to `MODELMESH_NAV` in `modelmesh/settings.py` and its URLs to `modelmesh/urls.py`. Pages extend `templates/base.html`. Forms render with `{% include "form_fields.html" with form=form %}`.
- The default provider is a mock (`MODELMESH_PROVIDER=mock`), so the app runs without an API key.

## Milestones

- **P2-A3 first draft, due 2026-11-09 23:59.** Needs a one-page updated product scope, a functional Django foundation, an initial AI implementation plan, a roadmap table, and the GitHub repo with a README that explains how to run the prototype.
- **P2-A4 final, due 2026-12-08 23:59.** The complete app, deployment, evaluation, `README_AI.md` and a three-minute demo video.

## P2-A3 dates

| Date | Goal |
|---|---|
| 2026-11-03 | Agree on the split and the open decisions. Each member starts a branch. |
| 2026-11-04 | Omkar merges the providers models. |
| 2026-11-06 | Every app has a pull request open, with models, migrations, views, templates and forms working. |
| 2026-11-07 | Hriday merges and tests the full Playground flow. Document drafts go to the team. |
| 2026-11-08 | `docs/product_scope.md`, `docs/ai_plan.md` and `docs/roadmap.md` final. README updated. Fresh-clone test. |
| 2026-11-09 | Hriday submits the repository URL on Canvas by 21:00. |

## Open decisions

1. **How the router uses AI.** Recommended: a small trained text classifier (scikit-learn, TF-IDF with logistic regression) on about 100 labeled sample prompts, with the keyword rules as the fallback.
2. **`AIModel` field names.** Omkar and Srinath agree on them so the providers and router apps can be built at the same time.

## Working rules

- One branch per app (`feature/providers`, `feature/router`, `feature/analytics`). Open a pull request to `main`. Hriday merges.
- Don't change `RequestLog` fields without telling Hriday. Every app reads them.
- Never commit `.env` files, API keys or passwords.
