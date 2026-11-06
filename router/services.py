"""The router: route(prompt, priority) is what settings.MODELMESH_ROUTER points to.

Flow: decide() picks an ordered list of models without calling any LLM, then
route() calls them in that order until one answers. The decision is handed to
router.signals through a ContextVar, so it can be saved next to the RequestLog
that accounts.services.run_prompt() creates, without changing that code.
"""

import contextvars
import statistics
from dataclasses import dataclass, field

from django.db.models import Avg, Count

from accounts.models import RequestLog
from accounts.services import ProviderError

from . import classifier, features, llm
from .models import CATEGORY_CHOICES, Feedback, RouterModel, RoutingRule, RoutingSettings
from .scoring import apply_confidence_gate, blend_feedback, score_candidates, weights_for

CATEGORY_LABELS = dict(CATEGORY_CHOICES)
PRIORITY_LABELS = {"balanced": "Balanced", "cheapest": "Cheapest", "fastest": "Fastest", "quality": "Best quality"}

# Set by route(), read once by the RequestLog post_save handler in signals.py.
pending_decision = contextvars.ContextVar("pending_decision", default=None)


@dataclass
class Decision:
    priority: str
    category: str
    classifier_used: str
    scores: list  # ranked rows from scoring.score_candidates
    order: list  # RouterModel objects to try, best first
    rule: RoutingRule = None
    matched_keyword: str = None
    gated: bool = False
    models: dict = field(default_factory=dict)  # model_id -> RouterModel

    def reason(self, chosen):
        parts = [CATEGORY_LABELS.get(self.category, self.category)]
        if self.classifier_used == "trained":
            probs = " / ".join(
                f"{self.models[r['model_id']].short_name} {round(r['p_good'] * 100)}%" for r in self.scores_by_tier()
            )
            parts.append(f"chance of a good answer: {probs}")
        else:
            parts.append("keyword rules (no trained classifier yet)")
        if self.rule:
            parts.append(f"rule matched “{self.matched_keyword}”")
        if self.gated:
            parts.append("top pick was below the confidence bar")
        parts.append(f"{PRIORITY_LABELS.get(self.priority, self.priority)} → {chosen.name}")
        return " · ".join(parts)[:255]

    def scores_by_tier(self):
        return sorted(self.scores, key=lambda r: self.models[r["model_id"]].tier)


def measured_latency(model):
    """Median latency of the model's last 50 real answers, else the benchmark value."""
    recent = list(
        RequestLog.objects.filter(model_used=model.model_id, status="success")
        .values_list("latency_ms", flat=True)[:50]
    )
    if len(recent) >= 5:
        return int(statistics.median(recent))
    return model.avg_latency_ms


def measured_cost(model):
    """Median cost of the model's last 50 real answers, else the benchmark value."""
    recent = list(
        RequestLog.objects.filter(model_used=model.model_id, status="success")
        .values_list("cost_usd", flat=True)[:50]
    )
    if len(recent) >= 5:
        return statistics.median(recent)
    return model.avg_cost


def feedback_by_model(category):
    """{model_id: (avg_stars, count)} for answers in this category."""
    rows = (
        Feedback.objects.filter(request_log__routing_decision__category=category)
        .values("request_log__routing_decision__chosen_model__model_id")
        .annotate(avg=Avg("stars"), n=Count("id"))
    )
    return {r["request_log__routing_decision__chosen_model__model_id"]: (r["avg"], r["n"]) for r in rows}


def decide(prompt, priority="balanced"):
    """Choose the order in which to try models. Makes no LLM call."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise ProviderError("The prompt is empty.")
    models = list(RouterModel.objects.filter(enabled=True))
    if not models:
        raise ProviderError("No models are enabled for routing.")
    by_id = {m.model_id: m for m in models}
    knobs = RoutingSettings.load()
    weights = weights_for(priority, {"quality": knobs.quality_weight, "cost": knobs.cost_weight, "speed": knobs.speed_weight})
    latency = {m.model_id: measured_latency(m) for m in models}
    cost = {m.model_id: measured_cost(m) for m in models}

    prediction = classifier.predict(prompt)
    # Only trust the classifier if it knows every enabled model.
    if prediction and all(m.model_id in prediction["p_good"] for m in models):
        category = prediction["category"]
        feedback = feedback_by_model(category)
        p_good = {
            mid: blend_feedback(p, *feedback.get(mid, (None, 0)))
            for mid, p in prediction["p_good"].items()
            if mid in by_id
        }
        ranked = score_candidates(models, p_good, weights, latency, cost)
        ranked, gated = apply_confidence_gate(ranked, knobs.confidence_threshold)
        classifier_used = "trained"
    else:
        category = features.detect_category(prompt)
        tier = features.target_tier(prompt, priority)
        ranked = score_candidates(models, None, weights, latency, cost)
        # Closest tier first; on a tie, the larger model (safer).
        ranked.sort(key=lambda r: (abs(by_id[r["model_id"]].tier - tier), -by_id[r["model_id"]].tier))
        gated = False
        classifier_used = "keyword_fallback"

    order = [by_id[r["model_id"]] for r in ranked]
    rule, keyword = None, None
    for candidate in RoutingRule.objects.filter(enabled=True).select_related("preferred_model", "fallback_model"):
        keyword = candidate.matches(prompt)
        if keyword and candidate.preferred_model.enabled:
            rule = candidate
            category = candidate.category
            first = [candidate.preferred_model]
            if candidate.fallback_model and candidate.fallback_model.enabled:
                first.append(candidate.fallback_model)
            order = first + [m for m in order if m not in first]
            break

    return Decision(
        priority=priority, category=category, classifier_used=classifier_used, scores=ranked,
        order=order, rule=rule, matched_keyword=keyword if rule else None, gated=gated, models=by_id,
    )


def route(prompt, priority="balanced"):
    """Router contract used by accounts.services.run_prompt()."""
    pending_decision.set(None)
    decision = decide(prompt, priority)
    attempts = []
    for model in decision.order:
        try:
            answer = llm.complete(model.model_id, prompt)
        except ProviderError as e:
            attempts.append({"model_id": model.model_id, "error": str(e)})
            continue
        attempts.append({"model_id": model.model_id, "error": None})
        pending_decision.set({
            "prompt": prompt, "decision": decision, "chosen": model, "attempts": attempts,
        })
        return {
            "response": answer["text"],
            "provider": model.provider,
            "model": model.model_id,
            "input_tokens": answer["input_tokens"],
            "output_tokens": answer["output_tokens"],
            "reason": decision.reason(model),
        }

    pending_decision.set({"prompt": prompt, "decision": decision, "chosen": None, "attempts": attempts})
    last_error = attempts[-1]["error"] if attempts else "no models to try"
    raise ProviderError(f"All models failed. Last error: {last_error}")
