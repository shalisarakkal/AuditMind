"""Claude AI service for resilience auditing, scoring, and report generation."""

import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from threading import Lock
from typing import Any, Type, TypeVar

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, Anthropic
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger("app.claude")

T = TypeVar("T", bound=BaseModel)

_client: Anthropic | None = None
_client_lock = Lock()

# In-memory call counters and cost tracking (reset at process start)
# For production, these should move to persistent metrics
_claude_call_stats: dict[str, Any] = {
    "calls_total": 0,
    "calls_successful": 0,
    "calls_failed": 0,
    "total_tokens_input": 0,
    "total_tokens_output": 0,
    "estimated_cost_usd": 0.0,
    "errors_by_type": {},
    "last_error_at": None,
}

# Per-organization token/cost tracking (in-memory; process-scoped)
# Key: org_id -> dict with tokens_used, cost_usd, calls_made
_org_claude_usage: dict[str, dict[str, Any]] = {}

# Per-organization call rate limiting state
# Key: org_id -> dict with last_call_time, calls_in_window
_org_call_state: dict[str, dict[str, Any]] = {}

# Default per-organization limits (configurable via environment)
ORG_MAX_CALLS_PER_HOUR = getattr(settings, "CLAUDE_ORG_CALLS_PER_HOUR", 100)
ORG_MAX_COST_PER_HOUR_USD = getattr(settings, "CLAUDE_ORG_MAX_COST_PER_HOUR_USD", 50.0)

# Retry configuration
MAX_RETRIES = getattr(settings, "CLAUDE_MAX_RETRIES", 3)
RETRY_BACKOFF_BASE = 2  # seconds
RETRYABLE_STATUS_CODES = {429, 529, 503, 504}


class ClaudeOperationalError(ValueError):
    """Raised when Claude operational controls prevent a call."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


def get_client() -> Anthropic:
    """Initialize lazily; application retries own the total attempt budget."""
    global _client
    if not settings.ANTHROPIC_API_KEY:
        raise ClaudeOperationalError("Claude isn't configured (no API key)")
    with _client_lock:
        if _client is None:
            _client = Anthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                timeout=settings.CLAUDE_TIMEOUT_SECONDS,
                max_retries=0,
            )
    return _client


def reset_call_stats() -> None:
    """Reset call statistics (used in tests)."""
    _claude_call_stats.update({
        "calls_total": 0,
        "calls_successful": 0,
        "calls_failed": 0,
        "total_tokens_input": 0,
        "total_tokens_output": 0,
        "estimated_cost_usd": 0.0,
        "errors_by_type": {},
        "last_error_at": None,
    })


def get_call_stats() -> dict[str, Any]:
    """Return current call statistics snapshot."""
    return dict(_claude_call_stats)


def get_org_usage(org_id: uuid.UUID) -> dict[str, Any]:
    """Return current token/cost usage for an organization."""
    key = str(org_id)
    return dict(_org_claude_usage.get(key, {
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0.0,
        "calls_made": 0,
        "first_call_at": None,
        "last_call_at": None,
    }))


def check_org_limits(org_id: uuid.UUID) -> None:
    """Raise ClaudeOperationalError if organization exceeds limits."""
    key = str(org_id)
    usage = _org_claude_usage.get(key, {
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0.0,
        "calls_made": 0,
    })

    now = time.time()

    # Reset window if needed (simple hourly window)
    if "window_start" not in usage or now - usage.get("window_start", 0) > 3600:
        usage["window_start"] = now
        usage["calls_in_window"] = 0
        usage["cost_in_window"] = 0.0

    calls_in_window = usage.get("calls_in_window", 0)
    cost_in_window = usage.get("cost_in_window", 0.0)

    if calls_in_window >= ORG_MAX_CALLS_PER_HOUR:
        raise ClaudeOperationalError(
            f"Organization {org_id} has exceeded the per-hour Claude call limit "
            f"({ORG_MAX_CALLS_PER_HOUR} calls/hour)."
        )

    if cost_in_window >= ORG_MAX_COST_PER_HOUR_USD:
        raise ClaudeOperationalError(
            f"Organization {org_id} has exceeded the per-hour Claude cost limit "
            f"(${ORG_MAX_COST_PER_HOUR_USD:.2f}/hour)."
        )


def record_org_call(org_id: uuid.UUID, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
    """Record a Claude call's usage for an organization."""
    key = str(org_id)
    now = time.time()
    usage = _org_claude_usage.get(key, {
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_usd": 0.0,
        "calls_made": 0,
        "first_call_at": now,
        "window_start": now,
        "calls_in_window": 0,
        "cost_in_window": 0.0,
    })

    usage["tokens_input"] = usage.get("tokens_input", 0) + tokens_in
    usage["tokens_output"] = usage.get("tokens_output", 0) + tokens_out
    usage["cost_usd"] = usage.get("cost_usd", 0.0) + cost_usd
    usage["calls_made"] = usage.get("calls_made", 0) + 1
    usage["last_call_at"] = now
    usage["calls_in_window"] = usage.get("calls_in_window", 0) + 1
    usage["cost_in_window"] = usage.get("cost_in_window", 0.0) + cost_usd

    _org_claude_usage[key] = usage


def record_call_stats(success: bool, error_type: str | None = None) -> None:
    """Record global call statistics."""
    _claude_call_stats["calls_total"] += 1
    if success:
        _claude_call_stats["calls_successful"] += 1
    else:
        _claude_call_stats["calls_failed"] += 1
        if error_type:
            _claude_call_stats["errors_by_type"][error_type] = \
                _claude_call_stats["errors_by_type"].get(error_type, 0) + 1
            _claude_call_stats["last_error_at"] = time.time()


def estimate_cost_usd(tokens_in: int, tokens_out: int, model: str | None = None) -> float:
    """Estimate cost in USD for token usage.

    Claude 3.5 Sonnet pricing (approximate):
    - Input: $3.00 per 1M tokens
    - Output: $15.00 per 1M tokens
    """
    model_name = model or settings.CLAUDE_MODEL
    input_rate = 3.00 / 1_000_000
    output_rate = 15.00 / 1_000_000

    # Adjust for known models
    if "haiku" in model_name.lower():
        input_rate = 0.25 / 1_000_000
        output_rate = 1.25 / 1_000_000
    elif "opus" in model_name.lower():
        input_rate = 15.00 / 1_000_000
        output_rate = 75.00 / 1_000_000

    return (tokens_in * input_rate) + (tokens_out * output_rate)


def provider_error_status(exc: Exception) -> int:
    if isinstance(exc, APITimeoutError):
        return 504
    if isinstance(exc, APIConnectionError):
        return 503
    if isinstance(exc, APIStatusError) and exc.status_code in (401, 403, 429, 503, 504, 529):
        return 503
    return 502


def provider_error_message(exc: Exception) -> str:
    """Map provider exceptions to clear user-facing messages."""
    if isinstance(exc, APITimeoutError):
        return "Claude request timed out. Please try again with a shorter prompt or fewer findings."
    if isinstance(exc, APIConnectionError):
        return "Unable to connect to Claude service. Please check network and try again."
    if isinstance(exc, APIStatusError):
        if exc.status_code == 401:
            return "Claude authentication failed. Please verify ANTHROPIC_API_KEY."
        if exc.status_code == 403:
            return "Claude access forbidden. Please check API key permissions."
        if exc.status_code == 429:
            return "Claude rate limit exceeded. Please wait and retry."
        if exc.status_code in (503, 504, 529):
            return f"Claude service temporarily unavailable (HTTP {exc.status_code}). Please retry."
        return f"Claude API error (HTTP {exc.status_code})."
    return "Claude service returned an unexpected error. Please retry."


@contextmanager
def claude_call_context(org_id: uuid.UUID | None = None, operation: str = "claude_call"):
    """Correlate each attempt; durable admission happens before this context.

    Yields a dict with `call_id`, `start_time`, and `org_id` for caller use.
    """
    start = time.time()
    call_id = str(uuid.uuid4())

    yield {"call_id": call_id, "start_time": start, "org_id": org_id}


SYSTEM_PROMPT = (
    "You are a senior cyber resilience auditor and technical assessor. "
    "You evaluate organizations against NIST CSF 2.0, CIS Controls v8, and ISO/IEC 27001:2022. "
    "Your assessments must be clear, actionable, evidence-based, and objective. "
    "Output must strictly match the requested JSON schema without markdown wrappers or preamble."
)


def ask_claude(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 2048,
    org_id: uuid.UUID | None = None,
    operation: str = "claude_call",
    usage_bind=None,
) -> str:
    """Invokes Claude with operational controls: retries, timeouts, error mapping, cost tracking.

    Parameters:
        prompt: User prompt to send.
        system: Optional system prompt override.
        max_tokens: Maximum tokens in response.
        org_id: Organization ID for per-org usage tracking and limits.
        operation: Operation name for logging context.
    """
    client = get_client()
    system_prompt = system or SYSTEM_PROMPT
    last_error: Exception | None = None
    if org_id is not None and usage_bind is None:
        from app.db.session import engine
        usage_bind = engine

    for attempt in range(1, MAX_RETRIES + 1):
        ledger_id = None
        if org_id is not None:
            from app.services import ai_accounting
            # UTF-8 bytes conservatively upper-bound normal tokenizer counts.
            estimate = estimate_cost_usd(len((prompt + system_prompt).encode("utf-8")), max_tokens)
            ledger_id = ai_accounting.reserve(usage_bind, org_id, settings.CLAUDE_MODEL, estimate)
        with claude_call_context(org_id, operation) as ctx:
            try:
                message = client.messages.create(
                    model=settings.CLAUDE_MODEL,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                )

                # Extract usage info if available
                tokens_in = getattr(message, "usage", None)
                if ledger_id is not None and tokens_in is None:
                    raise ValueError("Provider response omitted usage accounting")
                if tokens_in:
                    input_tokens = getattr(tokens_in, "input_tokens", 0) or 0
                    output_tokens = getattr(tokens_in, "output_tokens", 0) or 0
                    cost = estimate_cost_usd(input_tokens, output_tokens, settings.CLAUDE_MODEL)
                    if ledger_id is not None:
                        ai_accounting.finish(usage_bind, ledger_id, input_tokens=input_tokens,
                            output_tokens=output_tokens, cost_usd=cost, success=True)

                    if org_id:
                        record_org_call(org_id, input_tokens, output_tokens, cost)
                    _claude_call_stats["total_tokens_input"] += input_tokens
                    _claude_call_stats["total_tokens_output"] += output_tokens
                    _claude_call_stats["estimated_cost_usd"] += cost

                record_call_stats(success=True)
                logger.info(
                    f"Claude call {ctx['call_id']} succeeded in {time.time() - ctx['start_time']:.2f}s",
                    extra={"call_id": ctx["call_id"], "org_id": str(org_id) if org_id else None,
                           "operation": operation},
                )
                return "".join(block.text for block in message.content if block.type == "text")

            except Exception as exc:
                if ledger_id is not None:
                    ai_accounting.finish(usage_bind, ledger_id)
                last_error = exc
                duration = time.time() - ctx["start_time"]
                record_call_stats(success=False, error_type=type(exc).__name__)

                # Check if retryable
                is_retryable = False
                if isinstance(exc, APIStatusError) and exc.status_code in RETRYABLE_STATUS_CODES:
                    is_retryable = True
                elif isinstance(exc, (APITimeoutError, APIConnectionError)):
                    is_retryable = True

                if attempt < MAX_RETRIES and is_retryable:
                    backoff = RETRY_BACKOFF_BASE ** attempt
                    logger.warning(
                        f"Claude call {ctx['call_id']} attempt {attempt} failed, "
                        f"retrying in {backoff}s",
                        extra={"call_id": ctx["call_id"], "org_id": str(org_id) if org_id else None,
                               "operation": operation, "attempt": attempt},
                    )
                    time.sleep(backoff)
                    continue

                # Not retryable or exhausted retries
                message = provider_error_message(exc)
                logger.error(
                    f"Claude call {ctx['call_id']} failed after {duration:.2f}s: {message}",
                    extra={"call_id": ctx["call_id"], "org_id": str(org_id) if org_id else None,
                           "operation": operation, "error_type": type(exc).__name__,
                           "error_message": message, "attempts": attempt},
                )
                raise ClaudeOperationalError(message, provider_error_status(exc)) from exc

    # Should not reach here
    raise ValueError(str(last_error) if last_error else "Claude call failed")


def _extract_json_substring(text: str) -> str:
    """Extracts JSON content from potential markdown code blocks or text wrappers."""
    text = text.strip()
    # Check for ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def ask_claude_structured(
    prompt: str,
    response_model: Type[T],
    system: str | None = None,
    max_tokens: int = 4096,
    org_id: uuid.UUID | None = None,
    usage_bind=None,
) -> T:
    """Invokes Claude and validates the structured JSON response against `response_model`."""
    schema = json.dumps(response_model.model_json_schema())
    raw_response = ask_claude(
        f"{prompt}\n\nRequired JSON schema:\n{schema}", system=system, max_tokens=max_tokens,
        org_id=org_id, usage_bind=usage_bind,
    )
    json_text = _extract_json_substring(raw_response)

    try:
        data = json.loads(json_text)
        return response_model.model_validate(data)
    except Exception as exc:
        logger.error("Failed to parse Claude structured response")
        raise ValueError("Invalid structured response from AI model") from exc

