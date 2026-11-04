# providers: Omkar Chougule

- **Status:** not started
- **Branch:** `feature/providers`
- **Wireframe screens:** 9 (Providers & Health), 10 (Add / Edit Provider)
- **Last updated:** 2026-11-03

## P2-A3 tasks (due 2026-11-09)

- [ ] `python manage.py startapp providers`
- [ ] Models:
  - `Provider`: name, API base URL, enabled, health status.
  - `AIModel`: linked to a `Provider`, with model ID, cost per 1M input tokens, cost per 1M output tokens, load-balancing weight and enabled.
  - Merge these first, by 2026-11-04. The router app links to `AIModel`.
- [ ] Migrations, and admin pages for both models.
- [ ] Providers list page (Screen 9).
- [ ] Add / Edit provider form (Screen 10). Validate that required fields are filled, costs aren't negative, and the weight is from 0 to 100.
- [ ] Move `anthropic_completion()` from `accounts/services.py` into this app, and price each request with its own model's costs.
- [ ] Add the app to `INSTALLED_APPS`, add a "Providers" link to `MODELMESH_NAV`, and add its URLs to `modelmesh/urls.py`.

## Submission piece: roadmap table (Requirement 4, 15 pts)

- [ ] `docs/roadmap.md`: a table with Task, Current Status, Responsible Member and Expected Completion. The rows are Django Core Features, Database and APIs, AI Integration, Evaluation and Testing, Deployment, and Documentation.
- [ ] On 2026-11-08, fill in each row's current status from what is actually merged.

## Depends on / used by

- **Depends on:** nothing new.
- **Used by:**
  - the `router` app: `RoutingRule` links to `AIModel`
  - cost estimates in `accounts.services`
- **Open decision:** agree on the `AIModel` field names with Srinath.
