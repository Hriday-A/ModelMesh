"""The decision formula, kept free of Django queries so evaluation can reuse it.

    score = P(good) × w_quality − price × w_cost − slowness × w_speed

price and slowness are relative to the most expensive and slowest candidate (0–1).
price is each model's median measured cost per answer when every candidate has one;
otherwise list price on a typical request size.
"""

from decimal import Decimal

# Base weights per priority. Admin sliders (RoutingSettings) multiply these.
PRIORITY_WEIGHTS = {
    "balanced": {"quality": 1.0, "cost": 0.3, "speed": 0.2},
    "cheapest": {"quality": 1.0, "cost": 0.8, "speed": 0.1},
    "fastest": {"quality": 1.0, "cost": 0.1, "speed": 0.8},
    "quality": {"quality": 1.0, "cost": 0.0, "speed": 0.0},
}

# Fallback when measured costs are missing: list prices on a typical request size.
# This only affects the ranking, never the billed cost (real token counts).
TYPICAL_INPUT_TOKENS = 500
TYPICAL_OUTPUT_TOKENS = 1000


def weights_for(priority, multipliers=None):
    base = PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS["balanced"])
    multipliers = multipliers or {}
    return {k: v * multipliers.get(k, 1.0) for k, v in base.items()}


def typical_price(model):
    return model.cost(TYPICAL_INPUT_TOKENS, TYPICAL_OUTPUT_TOKENS)


def answer_costs(models, measured=None):
    """{model_id: cost used for ranking}. Measured cost per answer if known for all, else list price."""
    measured = measured or {}
    if models and all(measured.get(m.model_id) for m in models):
        return {m.model_id: Decimal(str(measured[m.model_id])) for m in models}
    return {m.model_id: typical_price(m) for m in models}


def score_candidates(models, p_good, weights, latency_ms, measured_cost=None):
    """Rank models best first.

    models: RouterModel-like objects (need .model_id and .cost()).
    p_good: {model_id: probability} or None (keyword fallback: no quality term).
    latency_ms: {model_id: median latency or None}. If any is unknown, speed is ignored.
    measured_cost: {model_id: median cost per answer or None}. If any is unknown, list prices are used.
    """
    prices = answer_costs(models, measured_cost)
    max_price = max(prices.values()) or Decimal(1)
    known = [v for v in latency_ms.values() if v]
    use_speed = len(known) == len(models) and max(known) > 0

    rows = []
    for m in models:
        p = p_good.get(m.model_id) if p_good else None
        cost_norm = float(prices[m.model_id] / max_price)
        speed_norm = latency_ms[m.model_id] / max(known) if use_speed else 0.0
        quality = (p or 0.0) * weights["quality"]
        total = quality - cost_norm * weights["cost"] - speed_norm * weights["speed"]
        rows.append({
            "model_id": m.model_id,
            "p_good": None if p is None else round(p, 4),
            "price": round(cost_norm, 4),
            "slowness": round(speed_norm, 4),
            "total": round(total, 4),
        })
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


def apply_confidence_gate(ranked, threshold):
    """If the top pick is unlikely to answer well, prefer models that clear the threshold.

    Returns (new_order, gated). Without probabilities the order is unchanged.
    """
    if not ranked or ranked[0]["p_good"] is None or ranked[0]["p_good"] >= threshold:
        return ranked, False
    passing = [r for r in ranked if r["p_good"] >= threshold]
    if passing:
        rest = [r for r in ranked if r["p_good"] < threshold]
        return passing + rest, True
    return sorted(ranked, key=lambda r: r["p_good"], reverse=True), True


def blend_feedback(p, avg_stars, n, prior_strength=5):
    """Nudge a predicted probability toward users' ratings (5 stars = 1.0)."""
    if not n or avg_stars is None:
        return p
    return (prior_strength * p + n * (avg_stars / 5)) / (prior_strength + n)
