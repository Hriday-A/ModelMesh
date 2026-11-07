"""Compares routing strategies on the held-out test prompts.

Every number comes from real benchmark data: the judge's score, cost and latency
recorded for the answer each strategy would have picked.
"""

import statistics
import time

from . import classifier, features
from .scoring import PRIORITY_WEIGHTS, apply_confidence_gate, score_candidates
from .training import GOOD_SCORE, counts_as_attempt


def by_tier_closest(models, tier):
    return min(models, key=lambda m: (abs(m.tier - tier), -m.tier))


def router_choice(models, p_good, weights, latency, threshold, cost=None):
    ranked = score_candidates(models, p_good, weights, latency, cost)
    ranked, _ = apply_confidence_gate(ranked, threshold)
    return ranked[0]["model_id"]


def summarize(name, picks, test, results, top_model_id):
    """Metrics for one strategy. picks: {prompt_id: model_id}."""
    scores = [r["scores"][picks[r["id"]]] for r in test]
    costs = [results[(r["id"], picks[r["id"]])]["cost_usd"] for r in test]
    latencies = [results[(r["id"], picks[r["id"]])]["latency_ms"] for r in test]
    return {
        "name": name,
        "picks": picks,
        "avg_score": statistics.mean(scores),
        "good_rate": sum(s >= GOOD_SCORE for s in scores) / len(scores),
        "total_cost": sum(costs),
        "avg_latency_ms": statistics.mean(latencies),
        "top_model": top_model_id,
    }


def oracle_picks(test, models, results):
    """For each prompt: the cheapest model the judge rated good, else the best-scored one."""
    picks = {}
    for r in test:
        good = [m for m in models if r["scores"][m.model_id] >= GOOD_SCORE]
        if good:
            picks[r["id"]] = min(good, key=lambda m: results[(r["id"], m.model_id)]["cost_usd"]).model_id
        else:
            picks[r["id"]] = max(models, key=lambda m: r["scores"][m.model_id]).model_id
    return picks


def calibration(predicted, actual, bins=((0, .5), (.5, .7), (.7, .9), (.9, 1.01))):
    """Rows of (bin, n, average predicted, actual good rate)."""
    rows = []
    for low, high in bins:
        pairs = [(p, a) for p, a in zip(predicted, actual) if low <= p < high]
        if pairs:
            rows.append({
                "bin": f"{low:.0%}–{min(high, 1):.0%}",
                "n": len(pairs),
                "predicted": statistics.mean(p for p, _ in pairs),
                "actual": statistics.mean(a for _, a in pairs),
            })
    return rows


def evaluate(test, models, results, artifact, threshold):
    """Everything the report needs. test: dataset rows (with "scores")."""
    model_ids = [m.model_id for m in models]
    top = max(models, key=lambda m: m.tier).model_id
    # Median latency and cost per answer for each model, from the benchmark answers to the
    # training prompts only, so the test prompts don't leak into the router's inputs.
    test_ids = {r["id"] for r in test}
    latency, cost = {}, {}
    for m in models:
        ok = [r for (pid, mid), r in results.items() if mid == m.model_id and counts_as_attempt(r) and pid not in test_ids]
        latency[m.model_id] = int(statistics.median(r["latency_ms"] for r in ok)) if ok else m.avg_latency_ms
        cost[m.model_id] = statistics.median(r["cost_usd"] for r in ok) if ok else m.avg_cost

    vectors = classifier.embed([r["prompt"] for r in test])  # also warms up the embedder
    # Router overhead as the app sees it: one prompt at a time, embedding + scoring.
    timings = []
    for r in test[:10]:
        started = time.perf_counter()
        one = classifier.embed([r["prompt"]])
        probs = {m: classifier.model_probability(artifact["models"][m], one)[0] for m in model_ids}
        router_choice(models, probs, PRIORITY_WEIGHTS["balanced"], latency, threshold, cost)
        timings.append((time.perf_counter() - started) * 1000)
    embed_ms = statistics.median(timings)
    p_good = {r["id"]: {} for r in test}
    for model_id in model_ids:
        probs = classifier.model_probability(artifact["models"][model_id], vectors)
        for r, p in zip(test, probs):
            p_good[r["id"]][model_id] = float(p)
    predicted_category = dict(zip([r["id"] for r in test], artifact["category_clf"].predict(vectors)))

    strategies = [summarize(f"Always {m.short_name}", {r["id"]: m.model_id for r in test}, test, results, top) for m in models]
    strategies.append(summarize(
        "Keyword rules (no ML)",
        {r["id"]: by_tier_closest(models, features.target_tier(r["prompt"], "balanced")).model_id for r in test},
        test, results, top,
    ))
    for priority, weights in PRIORITY_WEIGHTS.items():
        picks = {r["id"]: router_choice(models, p_good[r["id"]], weights, latency, threshold, cost) for r in test}
        strategies.append(summarize(f"Router · {priority}", picks, test, results, top))
    oracle = summarize("Oracle (best possible)", oracle_picks(test, models, results), test, results, top)
    strategies.append(oracle)

    # Random choice: the average over models, which is its expected value.
    always = [s for s in strategies if s["name"].startswith("Always")]
    strategies.insert(len(always), {
        "name": "Random (expected)", "picks": None,
        "avg_score": statistics.mean(s["avg_score"] for s in always),
        "good_rate": statistics.mean(s["good_rate"] for s in always),
        "total_cost": statistics.mean(s["total_cost"] for s in always),
        "avg_latency_ms": statistics.mean(s["avg_latency_ms"] for s in always),
        "top_model": top,
    })

    baseline = next(s for s in strategies if s["name"] == f"Always {next(m for m in models if m.model_id == top).short_name}")
    for s in strategies:
        s["quality_kept"] = s["avg_score"] / baseline["avg_score"] if baseline["avg_score"] else 0
        s["cost_share"] = s["total_cost"] / baseline["total_cost"] if baseline["total_cost"] else 0
        s["oracle_match"] = (
            sum(s["picks"][pid] == oracle["picks"][pid] for pid in s["picks"]) / len(test) if s["picks"] else None
        )

    classifier_rows = []
    for model_id in model_ids:
        predicted = [p_good[r["id"]][model_id] for r in test]
        actual = [int(r["scores"][model_id] >= GOOD_SCORE) for r in test]
        classifier_rows.append({
            "model_id": model_id,
            "accuracy": sum((p >= .5) == bool(a) for p, a in zip(predicted, actual)) / len(test),
            "base_rate": statistics.mean(actual),
            "brier": statistics.mean((p - a) ** 2 for p, a in zip(predicted, actual)),
            "calibration": calibration(predicted, actual),
        })

    curve = []
    for cost_weight in (0, .1, .2, .3, .5, .8, 1.2, 2.0):
        weights = {"quality": 1.0, "cost": cost_weight, "speed": 0.0}
        picks = {r["id"]: router_choice(models, p_good[r["id"]], weights, latency, threshold, cost) for r in test}
        s = summarize("", picks, test, results, top)
        curve.append({"cost_weight": cost_weight, "avg_score": s["avg_score"], "total_cost": s["total_cost"],
                      "share": {m.short_name: sum(v == m.model_id for v in picks.values()) for m in models}})

    balanced = next(s for s in strategies if s["name"] == "Router · balanced")
    samples = []
    for r in test:
        pick = balanced["picks"][r["id"]]
        samples.append({
            "id": r["id"], "prompt": r["prompt"], "category": r["category"],
            "predicted_category": predicted_category[r["id"]],
            "expected": oracle["picks"][r["id"]], "actual": pick, "score": r["scores"][pick],
            "latency_ms": results[(r["id"], pick)]["latency_ms"],
        })

    return {
        "strategies": strategies,
        "classifiers": classifier_rows,
        "category_accuracy": statistics.mean(predicted_category[r["id"]] == r["category"] for r in test),
        "curve": curve,
        "samples": samples,
        "embed_ms": embed_ms,
        "n_test": len(test),
    }
