# ModelMesh: updated product scope

INFO 490 · P2-A3 first draft · Team ModelMesh (Team 7)

## Finalized startup idea

**ModelMesh: An Intelligent AI Gateway.** ModelMesh is a web application that sits between an application and several AI providers and chooses which model answers each prompt. Users send prompts from a web Playground or through one API. ModelMesh picks a model for the priority they choose (Balanced, Cheapest, Fastest or Best quality), switches to a backup model when a provider fails, and records the model, cost, latency and reason for every request.

## Problem

Most applications that use AI are wired to a single model, often the most expensive one. A short factual question costs as much as a hard coding problem, and when that one provider is slow or down, the whole application stops working. Each application also has to handle its own keys, spending and error handling.

## Target users

Students, student organizations and small developer teams who build with AI on budgets of a few dollars a month and don't have time to build routing, fallback and monitoring themselves.

## Three planned core features

1. **Smart routing.** ModelMesh labels each prompt by task type, scores the available models on cost, speed and quality for the user's priority, and sends the request to the best fit. Every answer shows why that model was chosen, and users' star ratings adjust each model's score over time.
2. **Failover across providers.** A registry of providers and models with their prices and health status. When a provider is slow or down, the request moves to a backup model without breaking the user's application.
3. **Usage tracking with limits and caching.** A usage dashboard (requests, cost, latency, cache hit rate and CSV export), per-user rate limits and monthly budgets, and reuse of stored answers when the same prompt is sent again.

Accounts, API keys, the Playground and request history support all three features.

## Changes since P2-A2

No significant changes. The startup idea, features and wireframes are the ones in our P2-A2 submission (Project Idea Description and Wireframes PDF).
<!-- Update this section if the team adopts a trained text classifier for routing (see docs/status/README.md, Open decisions). -->
