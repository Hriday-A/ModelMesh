# router: Srinath Venkatesh

- **Status:** done for the first draft; trained on real benchmark data, ready for PR
- **Branch:** `feature/router`
- **Wireframe screens:** 11 (Routing Rules), 12 (Routing Explanation & Feedback)
- **Last updated:** 2026-11-07

## Done

- [x] `router` app: `RouterModel` (3 Lumen models, small/medium/large by parameters, with coin
  prices and measured median latency and cost per answer), `RoutingRule`, `RoutingSettings`,
  `RoutingDecision` (OneToOne `RequestLog`), `Feedback` (OneToOne `RequestLog`)
- [x] Models on UIUC Lumen (OpenAI-compatible API, key in `.env`): Ornith 1.0 35B, DeepSeek V4
  Flash, GLM 5.3, `reasoning_effort=high`
- [x] `router.services.route(prompt, priority)` set as `MODELMESH_ROUTER`: embedding + one logistic
  regression per model → P(good answer) → quality/cost/speed score → confidence bar → admin rules →
  calls one model, fails over to the next
- [x] Keyword fallback when no trained classifier exists
- [x] Real per-model cost written to `RequestLog.cost_usd` (in Lumen coins)
- [x] Screen 11 `/routing/`: rules list, new/edit/delete (staff), weight sliders, dry-run test prompt
- [x] Screen 12 `/routing/explain/<id>/`: score table, savings, star feedback; `/routing/requests/`
- [x] `POST /routing/api/preview`
- [x] Benchmark: 200 public-benchmark prompts (`router/benchmark/SOURCES.md`), 600 answers,
  judged by GPT-6 Astra (High) in ChatGPT, 196 prompts labeled
- [x] Router trained (bar: judge score 9+) and evaluated on 40 held-out prompts:
  `docs/eval/router_eval.md` (bar 7 comparison: `router_eval_bar7.md`)
- [x] `docs/ai_plan.md` with results (section 6); 26 router tests, 53 in total
- [x] Checked end to end with a real request: Playground path → router → Lumen → explanation page

## To do

- [ ] Open the PR into `main` (Nov 9)
- [ ] Dec 8: tune the confidence bar with cross-validation, more and harder prompts, a fresh
  hand-written test slice (contamination check), multi-turn routing

## Depends on / used by

- **Depends on:** `accounts.RequestLog` and `accounts.services.run_prompt` / `ProviderError` (on main).
  No dependency on the providers app; a link to `providers.AIModel` can be added after it merges.
- **Used by:** `run_prompt()` through `MODELMESH_ROUTER`.
- **Changes to shared files:** `settings.py` (app, router setting, nav, `ROUTER_*`), `modelmesh/urls.py`,
  `requirements.txt`, `.gitignore`, `static/css/main.css` (new section at the end), README.
