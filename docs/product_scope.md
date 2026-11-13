# ModelMesh: updated product scope

INFO 490 · P2-A3 first draft · Team ModelMesh (Team 7)

## Finalized startup idea

**ModelMesh: An Intelligent AI Gateway.** ModelMesh is a web application that sits between an application and several AI models and chooses which model answers each prompt. Users send prompts from a web Playground or through one API. A trained router picks a model for the priority they choose (Balanced, Cheapest, Fastest or Best quality), ModelMesh moves to the next model when one fails, and it records the model, cost, latency and reason for every request.

## Problem

Most applications that use AI are wired to a single model, often the most expensive one. A short factual question costs as much as a hard coding problem, and when that one provider is slow or down, the whole application stops working. Each application also has to handle its own keys, spending and error handling.

## Target users

Students, student organizations and small developer teams who build with AI on budgets of a few dollars a month and don't have time to build routing, fallback and monitoring themselves.

## Three planned core features

1. **Smart routing.** A trained classifier predicts each model's chance of giving a good answer to the prompt. ModelMesh combines that chance with each model's measured cost and speed for the user's priority and sends the request to the best fit. Every answer shows why that model was chosen, and users' star ratings adjust future choices.
2. **Failover and a model registry.** A registry of providers and models with their prices and health status. When the chosen model fails, the request moves to the next model without breaking the user's application.
3. **Usage tracking with limits and caching.** A usage dashboard (requests, cost, latency, cache hit rate and CSV export), per-user rate limits and monthly budgets, and reuse of stored answers when the same prompt is sent again.

Accounts, API keys, the Playground and request history support all three features.

## Changes since P2-A2

The idea, problem, target users and screens are the same as in our P2-A2 submission. Two parts of how we build it changed:

1. **Routing is learned instead of rule-based.** P2-A2 planned keyword-based task categories with a weighted score, because a trained classifier seemed harder to build and explain. We changed this so routing is a measurable AI feature. The router now turns each prompt into an embedding with a small Hugging Face model (`all-MiniLM-L6-v2`), and one scikit-learn logistic regression per model predicts the chance of a near-perfect answer (judge score 9 or 10). It is trained on 196 public-benchmark prompts that all three models answered and an LLM judge scored. Keyword rules remain as the fallback and as overrides that staff can set. On 40 held-out prompts, the Balanced priority kept 78% near-perfect answers at 46% of the cost of always using the largest model; keyword rules alone reached 70%. Details: [AI plan](ai_plan.md).
2. **The models run on UIUC Lumen.** Instead of several commercial providers, ModelMesh routes between three open-weight models of different sizes served by Lumen: Ornith 1.0 35B, DeepSeek V4 Flash and GLM 5.3. Costs are counted in Lumen coins. Because all three models run on one provider for now, failover moves between models, not between providers.

The app also adds a few links beyond the wireframes: the Usage dashboard links to the Quotas & cache page, the Playground and request detail pages link to the router's explanation page (Screen 12), and a list of routed requests is at `/routing/requests/`.
