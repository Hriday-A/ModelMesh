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
    # Prices are USD per 1M tokens. The Providers app (Part 2) will store a price per model.
    if model == "mock-echo":
        return Decimal("0")
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


def anthropic_completion(prompt, model):
    import anthropic

    if not model:
        raise ProviderError("No model is configured. Set MODELMESH_DEFAULT_MODEL.")
    client = anthropic.Anthropic()
    try:
        message = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            output_config={"effort": "medium"},
            # If the model declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise ProviderError("The Anthropic API key is missing or invalid.")
    except anthropic.RateLimitError:
        raise ProviderError("The provider is rate limiting requests. Try again shortly.")
    except anthropic.APIStatusError as e:
        raise ProviderError(f"Provider error ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise ProviderError("Could not reach the provider. Check your internet connection.")

    if message.stop_reason == "refusal":
        raise ProviderError("The model declined to answer this prompt.")

    text = "".join(block.text for block in message.content if block.type == "text")
    return {
        "response": text,
        "provider": "anthropic",
        "model": message.model,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
    }


def default_router(prompt, priority):
    """Placeholder router: same model for every prompt.

    Must return a dict with keys: response, provider, model, input_tokens,
    output_tokens, and optionally reason and cached. Raise ProviderError on failure.
    """
    if settings.MODELMESH_PROVIDER == "anthropic":
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
