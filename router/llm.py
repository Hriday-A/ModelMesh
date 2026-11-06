"""Calls one Lumen model and returns the answer with token counts and latency.

This is the router's only connection to an LLM. Lumen (UIUC/NCSA) serves the models
through an OpenAI-compatible API, so this uses the standard library and no SDK.
Every call is a real API call; there is no mock mode. Without LUMEN_API_KEY,
calls raise ProviderError and the request is logged as an error.
"""

import json
import socket
import ssl
import time
import urllib.error
import urllib.request

from django.conf import settings

from accounts.services import ProviderError


def _ssl_context():
    """Use certifi's CA bundle (python.org builds on macOS ship without root certificates)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class QuotaExceeded(ProviderError):
    """The Lumen coin budget is spent. Retrying cannot help until it refills."""


def _error_detail(e):
    """(code, message) from an HTTP error body, tolerating non-JSON bodies."""
    try:
        err = json.loads(e.read().decode("utf-8", "replace")).get("error", {})
        return err.get("code") or "", err.get("message") or ""
    except (ValueError, AttributeError):
        return "", ""


def complete(model_id, prompt):
    """Return {"text", "input_tokens", "output_tokens", "latency_ms", "stop_reason"}."""
    if not settings.LUMEN_API_KEY:
        raise ProviderError("No Lumen API key found. Set LUMEN_API_KEY in the .env file.")

    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.ROUTER_MAX_TOKENS,
        "reasoning_effort": settings.ROUTER_REASONING_EFFORT,
    }
    request = urllib.request.Request(
        settings.LUMEN_BASE_URL.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.LUMEN_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=settings.ROUTER_TIMEOUT_SECONDS, context=_ssl_context()) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        code, message = _error_detail(e)
        if e.code in (401, 403):
            raise ProviderError("The Lumen API key is invalid, or this model needs to be acknowledged in Lumen.")
        if e.code == 404:
            raise ProviderError(f"Model {model_id} was not found.")
        if e.code == 429 and code == "insufficient_quota":
            raise QuotaExceeded("The Lumen coin budget is spent.")
        if e.code == 429:
            raise ProviderError("The provider is rate limiting requests. Try again shortly.")
        raise ProviderError(f"Provider error ({e.code}): {message or e.reason}")
    except (socket.timeout, TimeoutError):
        raise ProviderError("Could not reach the provider: the request timed out.")
    except urllib.error.URLError:
        raise ProviderError("Could not reach the provider. Check your connection and the Lumen URL (campus VPN?).")
    except ValueError:
        raise ProviderError("The provider returned an unreadable response.")
    latency_ms = int((time.perf_counter() - start) * 1000)

    try:
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
        usage = data.get("usage") or {}
        finish = choice.get("finish_reason")
    except (KeyError, IndexError, AttributeError):
        raise ProviderError("The provider returned an unexpected response.")
    if not text.strip():
        if finish == "length":
            raise ProviderError("The model used all its tokens thinking. Raise ROUTER_MAX_TOKENS or lower the effort.")
        raise ProviderError("The model returned an empty answer.")
    return {
        "text": text,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),  # includes thinking tokens
        "latency_ms": latency_ms,
        "stop_reason": finish,
    }
