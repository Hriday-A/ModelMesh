"""Saves the router's decision next to the RequestLog that run_prompt() creates.

run_prompt() prices every request with one global rate. Here the cost is
replaced with the chosen model's real price, so the Usage dashboard is correct.
"""

from decimal import Decimal

from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import RequestLog

from .models import RoutingDecision
from .scoring import typical_price
from .services import pending_decision


@receiver(post_save, sender=RequestLog)
def save_routing_decision(sender, instance, created, **kwargs):
    pending = pending_decision.get()
    if not created or pending is None or pending["prompt"] != instance.prompt:
        return
    pending_decision.set(None)

    decision = pending["decision"]
    chosen = pending["chosen"]
    cost = saved = Decimal("0")
    if chosen and instance.status == "success":
        cost = chosen.cost(instance.input_tokens, instance.output_tokens)
        priciest = max(decision.models.values(), key=typical_price)
        saved = max(Decimal("0"), priciest.cost(instance.input_tokens, instance.output_tokens) - cost)
        instance.cost_usd = cost.quantize(Decimal("0.000001"))
        RequestLog.objects.filter(pk=instance.pk).update(cost_usd=instance.cost_usd)

    RoutingDecision.objects.create(
        request_log=instance,
        chosen_model=chosen,
        rule=decision.rule,
        category=decision.category,
        classifier_used=decision.classifier_used,
        scores={r["model_id"]: r for r in decision.scores},
        attempts=pending["attempts"],
        fallback_used=len(pending["attempts"]) > 1,
        cost_usd=cost,
        saved_usd=saved,
    )
