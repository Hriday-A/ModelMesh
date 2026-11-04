# router: Srinath Venkatesh

- **Status:** not started
- **Branch:** `feature/router`
- **Wireframe screens:** 11 (Routing Rules), 12 (Routing Explanation & Feedback)
- **Last updated:** 2026-11-03

## P2-A3 tasks (due 2026-11-09)

- [ ] `python manage.py startapp router`
- [ ] Models:
  - `RoutingRule`: task category, keywords, preferred model and fallback model. Both models link to `providers.AIModel`.
  - `Feedback`: linked to an `accounts.RequestLog`, with 1–5 stars and an optional comment.
- [ ] `route(prompt, priority)` in `router/services.py`. It classifies the prompt, scores the enabled models for the priority, calls the chosen model, and returns the router contract dictionary (see `README.md` in this folder).
- [ ] Set `MODELMESH_ROUTER = "router.services.route"`.
- [ ] Routing rules list and New rule form (Screen 11).
- [ ] Add the app to `INSTALLED_APPS`, add a "Routing" link to `MODELMESH_NAV`, and add its URLs to `modelmesh/urls.py`.

## Submission piece: initial AI implementation (Requirement 3, 20 pts)

- [ ] `docs/ai_plan.md`, covering:
  - The AI technique and model, and why they fit on cost, speed and accuracy.
  - Input and output: a prompt and priority go in; a task category, a chosen model and a one-line reason come out.
  - How it connects to Django: it reads `AIModel`, `RoutingRule` and `Feedback`, and writes the reason to `RequestLog`.
  - Evidence: run the classifier on about 20 sample prompts it was not trained on, and record expected vs. predicted category and the time per prompt.

## Depends on / used by

- **Depends on:**
  - `providers.AIModel`, due 2026-11-04
  - `accounts.RequestLog`
- **Used by:** `accounts.services.run_prompt()`, through `MODELMESH_ROUTER`.
- **Open decisions:**
  - How the router uses AI. The recommendation is a scikit-learn TF-IDF and logistic regression classifier, with keyword rules as the fallback.
  - The `AIModel` field names, to agree with Omkar.
