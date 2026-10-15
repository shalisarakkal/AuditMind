"""Claude AI service for resilience auditing, scoring, and report generation."""

import json
import logging
import re
from typing import Any, Type, TypeVar

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, Anthropic
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger("app.claude")

T = TypeVar("T", bound=BaseModel)

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        _client = Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.CLAUDE_TIMEOUT_SECONDS,
            max_retries=2,
        )
    return _client


SYSTEM_PROMPT = (
    "You are a senior cyber resilience auditor and technical assessor. "
    "You evaluate organizations against NIST CSF 2.0, CIS Controls v8, and ISO/IEC 27001:2022. "
    "Your assessments must be clear, actionable, evidence-based, and objective. "
    "Output must strictly match the requested JSON schema without markdown wrappers or preamble."
)


def ask_claude(prompt: str, system: str | None = None, max_tokens: int = 2048) -> str:
    """Invokes Claude and returns raw text response."""
    client = get_client()
    system_prompt = system or SYSTEM_PROMPT
    message = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


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
) -> T:
    """Invokes Claude and validates the structured JSON response against `response_model`."""
    schema = json.dumps(response_model.model_json_schema())
    raw_response = ask_claude(
        f"{prompt}\n\nRequired JSON schema:\n{schema}", system=system, max_tokens=max_tokens,
    )
    json_text = _extract_json_substring(raw_response)

    try:
        data = json.loads(json_text)
        return response_model.model_validate(data)
    except Exception as exc:
        logger.error(f"Failed to parse Claude structured response: {exc}\nResponse: {raw_response[:500]}")
        raise ValueError(f"Invalid structured response from AI model: {exc}") from exc

