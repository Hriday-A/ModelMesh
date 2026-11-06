# router: Srinath Venkatesh

- **Status:** built, waiting on benchmark data to train
- **Branch:** `feature/router`
- **Wireframe screens:** 11 (Routing Rules), 12 (Routing Explanation & Feedback)
- **Last updated:** 2026-11-05

## Done

- [x] `router` app: `RouterModel` (3 Lumen models (small/medium/large by parameters) with coin prices), `RoutingRule`, `RoutingSettings`,
  `RoutingDecision` (OneToOne `RequestLog`), `Feedback` (OneToOne `RequestLog`)
- [x] `router.services.route(prompt, priority)` set as `MODELMESH_ROUTER`: embedding + one logistic
  regression per model → P(good answer) → cost/speed/quality score → confidence bar → admin rules →
  calls one model, fails over to the next
- [x] Keyword fallback when no trained classifier exists
- [x] Real per-model cost written to `RequestLog.cost_usd` (Usage dashboard is now per-model correct)
- [x] Screen 11 `/routing/`: rules list, new/edit/delete (staff), weight sliders, dry-run test prompt
- [x] Screen 12 `/routing/explain/<id>/`: score table, money saved, star feedback; `/routing/requests/`
- [x] `POST /routing/api/preview`
- [x] Benchmark pipeline: `run_benchmark`, `export_for_judging`, `import_judgments`, `train_router`,
  `evaluate_router` (see `router/benchmark/README.md`)
- [x] `docs/ai_plan.md`; 24 router tests

## To do before 2026-11-09

- [ ] Create a Lumen API key, acknowledge the 3 models, put the key in `.env`
- [ ] Run a 3-call test to confirm Lumen accepts `reasoning_effort=medium` for each model
- [ ] Write ~200 prompts in `router/benchmark/prompts.csv`
- [ ] Run the benchmark, judge in ChatGPT, import, train, evaluate
- [ ] Fill section 6 of `docs/ai_plan.md` from `docs/eval/router_eval.md`
- [ ] Open the PR

## Depends on / used by

- **Depends on:** `accounts.RequestLog` and `accounts.services.run_prompt` / `ProviderError` (on main).
  No dependency on the providers app; a link to `providers.AIModel` can be added after it merges.
- **Used by:** `run_prompt()` through `MODELMESH_ROUTER`.
- **Changes to shared files:** `settings.py` (app, router setting, nav, `ROUTER_*`), `modelmesh/urls.py`,
  `requirements.txt`, `.gitignore`, `static/css/main.css` (new section at the end), README.
