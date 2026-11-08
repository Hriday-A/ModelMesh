"""Runs a prompt through ModelMesh and records it in RequestLog.

Views call run_prompt(). run_prompt() asks the router (settings.MODELMESH_ROUTER)
for a completion. Until the Router app (Part 3) exists, default_router() is used:
it sends every prompt to one model, or returns a mock reply when
MODELMESH_PROVIDER is "mock" so the app works without an API key.
"""

import time
from decimal import Decimal

from django.conf import settings
from django.utils.module_loading import import_string

from .models import RequestLog

class ProviderError(Exception):
    """Raised by a router or provider when a completion could not be produced."""


def estimate_cost(model, input_tokens, output_tokens):
    """Cost of one request, using the model's own prices from the Providers app.

    Models that aren't registered there fall back to the global
    MODELMESH_INPUT_PRICE / MODELMESH_OUTPUT_PRICE settings (per 1M tokens).
    """
    from providers.services import model_cost  # Imported here: providers imports this module.

    if model == "mock-echo":
        return Decimal("0")
    cost = model_cost(model, input_tokens, output_tokens)
    if cost is not None:
        return cost
    input_price = Decimal(settings.MODELMESH_INPUT_PRICE)
    output_price = Decimal(settings.MODELMESH_OUTPUT_PRICE)
    return (input_price * input_tokens + output_price * output_tokens) / Decimal(1_000_000)


def estimate_tokens(text):
    # Rough rule of thumb (about 4 characters per token) for the mock provider.
    return max(1, len(text) // 4)


def mock_completion(prompt):
    reply = (
        "[Mock response] ModelMesh received your prompt "
        f"({len(prompt.split())} words). Set MODELMESH_PROVIDER=anthropic to get real answers."
    )
    return {
        "response": reply,
        "provider": "mock",
        "model": "mock-echo",
        "input_tokens": estimate_tokens(prompt),
        "output_tokens": estimate_tokens(reply),
    }


def default_router(prompt, priority):
    """Placeholder router: same model for every prompt.

    Must return a dict with keys: response, provider, model, input_tokens,
    output_tokens, and optionally reason and cached. Raise ProviderError on failure.
    """
    if settings.MODELMESH_PROVIDER == "anthropic":
        from providers.services import anthropic_completion  # Imported here: providers imports this module.

        result = anthropic_completion(prompt, settings.MODELMESH_DEFAULT_MODEL)
    else:
        result = mock_completion(prompt)
    result["reason"] = "Default route: smart router not connected yet."
    return result


def run_prompt(user, prompt, source, priority="balanced", api_key=None):
    """Send a prompt through the router and save a RequestLog. Never raises ProviderError."""
    router = import_string(settings.MODELMESH_ROUTER)
    log = RequestLog(user=user, api_key=api_key, source=source, priority=priority, prompt=prompt)

    start = time.perf_counter()
    try:
        result = router(prompt, priority)
    except ProviderError as e:
        log.status = "error"
        log.error_message = str(e)
    else:
        log.status = "cached" if result.get("cached") else "success"
        log.response = result["response"]
        log.provider = result["provider"]
        log.model_used = result["model"]
        log.routing_reason = result.get("reason", "")[:255]
        log.input_tokens = result["input_tokens"]
        log.output_tokens = result["output_tokens"]
        log.cost_usd = estimate_cost(log.model_used, log.input_tokens, log.output_tokens)
    log.latency_ms = int((time.perf_counter() - start) * 1000)
    log.save()
    return log
