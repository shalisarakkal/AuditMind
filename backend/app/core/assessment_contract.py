"""Versioned contract shared by report prompts and consent disclosures."""
REPORT_PROMPT_VERSION = "audit-evidence-v3"
SCORING_RUBRIC_VERSION = "shared-tiers-v1"


def active_prompt_version() -> str:
    from app.core.config import settings
    return 'audit-evidence-v4' if settings.REPORT_EVIDENCE_V3_ENABLED else REPORT_PROMPT_VERSION
