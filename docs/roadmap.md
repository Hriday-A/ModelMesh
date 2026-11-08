# ModelMesh roadmap

Team ModelMesh (Team 7), INFO 490 Project 2. Status as of 2026-11-08.

"Merged" means the work is on `main`. "On branch" means it is built and tested but its pull request has not been merged yet.

| Task | Current Status | Responsible Member | Expected Completion |
|---|---|---|---|
| **Django Core Features** | Merged: `accounts` (sign-up, login, profile, API keys, Playground, history) and `analytics` (usage dashboard, CSV export, quota and cache settings). On branch: `providers` (Screens 9–10: providers list with health, add/edit form) on `feature/providers`, and `router` (Screens 11–12: routing rules, explanation and feedback) on `feature/router`. | Hriday Agarwal (`accounts`), Manojkumar Mohankumar (`analytics`), Omkar Chougule (`providers`), Srinath Venkatesh (`router`) | All four apps merged by 2026-11-09. Enforcing rate limits, budgets and caching by 2026-12-08. |
| **Database and APIs** | Merged: `UserProfile`, `APIKey`, `RequestLog`, `UsageLimit`, and `POST /api/chat` with Bearer API keys. On branch: `Provider` and `AIModel` (per-model prices, load-balancing weight, health status), and `RouterModel`, `RoutingRule`, `RoutingSettings`, `RoutingDecision`, `Feedback`, plus `POST /routing/api/preview`. Each request is now priced with its own model's costs. | Hriday Agarwal (API, `RequestLog`), Omkar Chougule (`Provider`, `AIModel`), Srinath Venkatesh (routing tables) | Merged by 2026-11-09. Merging `AIModel` and `RouterModel` into one table by 2026-11-22. |
| **AI Integration** | On branch (`feature/router`): a trained router. A sentence embedding feeds one logistic regression per model, which predicts the chance of a good answer. A quality, cost and speed score with a confidence bar then picks one of three UIUC Lumen models, and admin keyword rules override it. Keyword rules are the fallback when no trained model exists. It fails over to the next model on errors. Trained on 196 labeled benchmark prompts. | Srinath Venkatesh | Merged 2026-11-09. Confidence-bar tuning with cross-validation and multi-turn routing by 2026-12-08. |
| **Evaluation and Testing** | 27 automated tests on `main`. `feature/providers` adds 19 (forms, pricing, health checks, permissions). `feature/router` adds 26. The router is evaluated on 40 held-out prompts (`docs/eval/router_eval.md`). Not started: end-to-end tests after all apps merge, failover tests across providers, and a fresh hand-written test set. | All members. Srinath Venkatesh leads the router evaluation. | End-to-end check 2026-11-09. Full evaluation by 2026-12-08. |
| **Deployment** | Not started. The app runs locally with SQLite. Hosting choice is still open. | To be assigned | 2026-12-08 |
| **Documentation** | Done: `docs/product_scope.md`, this roadmap and the team status files. On branch: `docs/ai_plan.md` and the router evaluation reports. In progress: README updates (how to run the prototype, links to these documents). Not started: `README_AI.md` and the three-minute demo video. | Hriday Agarwal (README), Srinath Venkatesh (AI plan), Omkar Chougule (roadmap), all members (demo video) | README by 2026-11-09. `README_AI.md` and demo video by 2026-12-08. |

## Update before submitting

After the `providers` and `router` pull requests merge on 2026-11-09, change "On branch" to "Merged" in the rows above.
