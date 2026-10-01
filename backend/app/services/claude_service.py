from anthropic import Anthropic

from app.core.config import settings

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.CLAUDE_TIMEOUT_SECONDS, max_retries=2)
    return _client


def ask_claude(prompt: str, system: str | None = None, max_tokens: int = 1024) -> str:
    client = get_client()
    message = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


SYSTEM_PROMPT = (
    "You are a senior cyber resilience auditor. You evaluate organizations using "
    "NIST CSF, CIS Benchmarks, and ISO 27001. Assess identity, network, vulnerability, "
    "backup, monitoring, incident response, and compliance. Assign scores (0-100) per "
    "domain and overall. Explain risks in clear language. Provide prioritized "
    "remediation steps."
)
