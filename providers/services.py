"""Provider calls, per-model pricing and health checks."""

import urllib.error
import urllib.request
from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone

from accounts.models import RequestLog
from accounts.services import ProviderError

from .models import AIModel


def model_cost(model_id, input_tokens, output_tokens):
    """Cost of one request at the model's own prices, or None if the model isn't registered."""
    model = AIModel.objects.filter(model_id=model_id).first()
    if model is None:
        return None
    return model.cost(input_tokens, output_tokens)


def anthropic_completion(prompt, model):
    import anthropic

    if not model:
        raise ProviderError("No model is configured. Set MODELMESH_DEFAULT_MODEL.")
    try:
        client = anthropic.Anthropic()
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
    except (anthropic.CredentialsError, TypeError):
        # With no credentials at all, the SDK raises TypeError when the request is built.
        raise ProviderError("No Anthropic API key found. Set ANTHROPIC_API_KEY.")
    except anthropic.AnthropicError:
        raise ProviderError("The provider returned an unexpected response.")

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


def check_health(provider, timeout=5):
    """Probe the provider's base URL and save the result on the provider.

    Any HTTP answer below 500 (including 401 when no key is sent) means the service is up.
    A 5xx answer means degraded. No answer means down. No URL (the mock) means healthy.
    """
    if not provider.api_base_url:
        status, detail = "healthy", "Offline provider. No network check needed."
    else:
        request = urllib.request.Request(
            provider.api_base_url, method="GET", headers={"User-Agent": "ModelMesh-health-check"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, detail = "healthy", f"Answered with HTTP {response.status}."
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                status, detail = "degraded", f"Answered with server error HTTP {e.code}."
            else:
                status, detail = "healthy", f"Reachable (HTTP {e.code})."
        except OSError as e:  # URLError, timeouts and DNS failures are all OSError subclasses.
            reason = getattr(e, "reason", e)
            status, detail = "down", f"Could not connect: {reason}"[:255]

    provider.health_status = status
    provider.health_detail = detail
    provider.last_checked_at = timezone.now()
    provider.save(update_fields=["health_status", "health_detail", "last_checked_at"])
    return status


def recent_stats(hours=24):
    """{provider slug: {"requests", "avg_latency_ms"}} for answered requests in the last N hours.

    Failed requests are saved without a provider, so only answered requests count here.
    """
    since = timezone.now() - timedelta(hours=hours)
    rows = (
        RequestLog.objects.filter(created_at__gte=since)
        .exclude(provider="")
        .values("provider")
        .annotate(requests=Count("id"), avg_latency_ms=Avg("latency_ms"))
    )
    return {row["provider"]: row for row in rows}
