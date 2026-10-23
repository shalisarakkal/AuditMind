"""Explicit reporting boundary. No automatic model/provider fallback."""
import hashlib
import json
import math
import re
from types import SimpleNamespace

import httpx

from app.core.config import settings
from app.services.report_context import POLICY_VERSION

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
ROUTING = {"only": ["Anthropic"], "allow_fallbacks": False,
           "require_parameters": True, "data_collection": "deny", "zdr": True}


class OpenRouterError(Exception):
    def __init__(self, status_code=502):
        super().__init__("OpenRouter request failed")
        self.status_code = status_code


def identity():
    if settings.REPORT_AI_PROVIDER == "anthropic":
        return {"provider": "anthropic", "model": settings.CLAUDE_MODEL}
    if settings.REPORT_AI_PROVIDER != "openrouter":
        raise ValueError("Unsupported report provider")
    return {"provider": "openrouter", "model": settings.OPENROUTER_MODEL,
            "routing": ROUTING, "price_caps": {
                "prompt": settings.OPENROUTER_INPUT_USD_PER_MILLION,
                "completion": settings.OPENROUTER_OUTPUT_USD_PER_MILLION}}


def target(prompt_version):
    route = identity()
    budget = {'policy': POLICY_VERSION, 'input_bytes': settings.REPORT_AI_MAX_INPUT_BYTES,
              'finding_text_bytes': settings.REPORT_AI_FINDING_TEXT_BYTES}
    if route["provider"] == "anthropic":
        budget_hash = hashlib.sha256(json.dumps(budget, sort_keys=True).encode()).hexdigest()[:16]
        return f"anthropic:{route['model']}:budget-{budget_hash}:{prompt_version}"
    digest = hashlib.sha256(json.dumps({**route, 'input_budget': budget}, sort_keys=True).encode()).hexdigest()[:24]
    return f"openrouter:{route['model']}:{prompt_version}:anthropic-only:zdr:{digest}"


def require_configured():
    if settings.REPORT_AI_PROVIDER == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set; AI audit generation is unavailable")
        return
    if settings.REPORT_AI_PROVIDER != "openrouter":
        raise ValueError("Unsupported report provider")
    if not settings.OPENROUTER_INFERENCE_ENABLED:
        raise ValueError("OpenRouter inference is disabled; no request was sent")
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OpenRouter credentials are not configured")
    if not re.fullmatch(r"anthropic/claude-[a-z0-9.-]+", settings.OPENROUTER_MODEL):
        raise ValueError("An explicit OpenRouter Claude model ID is required")
    for rate in (settings.OPENROUTER_INPUT_USD_PER_MILLION, settings.OPENROUTER_OUTPUT_USD_PER_MILLION):
        if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
            raise ValueError("Explicit OpenRouter price ceilings are required")


def complete(*, model, max_tokens, system, messages, expected_route=None):
    """One bounded HTTP attempt; caller owns retries/accounting/authorization.

    Normalizes only the transport envelope, never report JSON or evidence IDs.
    """
    if settings.REPORT_AI_PROVIDER != "openrouter":
        raise ValueError("OpenRouter is not the selected report provider")
    require_configured()
    route = identity()
    if expected_route is not None and route != expected_route:
        raise ValueError("Report provider configuration changed")
    if model != settings.OPENROUTER_MODEL:
        raise ValueError("Report model configuration changed")
    payload = dict(model=model, max_tokens=max_tokens, stream=False,
                   messages=[{"role": "system", "content": system}, *messages],
                   provider={**ROUTING, "max_price": route["price_caps"]})
    try:
        with httpx.Client(timeout=settings.CLAUDE_TIMEOUT_SECONDS, follow_redirects=False,
                          trust_env=False) as client:
            require_configured()
            if identity() != route:
                raise ValueError("Report provider configuration changed")
            response = client.post(ENDPOINT, headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"},
                                   json=payload)
        if response.status_code != 200:
            raise OpenRouterError(response.status_code)
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid provider envelope")
        if data.get("error") or data.get("model") != model or data.get("provider") != "Anthropic":
            raise ValueError("Unexpected provider response")
        choices = data["choices"]
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict) or choices[0].get("finish_reason") != "stop":
            raise ValueError("Incomplete provider response")
        if not isinstance(choices[0].get("message"), dict) or choices[0]["message"].get("role") != "assistant":
            raise ValueError("Invalid provider message")
        content = choices[0]["message"]["content"]
        usage = data["usage"]
        if not isinstance(usage, dict):
            raise ValueError("Invalid provider usage")
        for field in ("prompt_tokens", "completion_tokens"):
            if type(usage[field]) is not int or usage[field] < 0:
                raise ValueError("Invalid provider usage")
        cost = usage["cost"]
        if type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0:
            raise ValueError("Invalid provider cost")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty provider response")
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=content)],
            usage=SimpleNamespace(input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
                                  actual_cost_usd=cost))
    except httpx.TimeoutException:
        raise OpenRouterError(504) from None
    except httpx.RequestError:
        raise OpenRouterError(503) from None
    except OpenRouterError:
        raise
    except (ValueError, TypeError, KeyError, IndexError):
        raise OpenRouterError(502) from None
