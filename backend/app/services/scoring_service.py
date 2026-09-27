"""Rule-based v1 risk scoring, per RISL_SCORING.md. Deterministic baseline;
Claude-driven qualitative scoring (RAG + narrative justification) layers on top of
this in a later milestone.
"""

from app.models.enums import Domain, RiskTier, Severity
from app.models.finding import Finding

CRITICAL_DEDUCTION = 15
HIGH_DEDUCTION = 7
MEDIUM_DEDUCTION = 3
LOW_DEDUCTION = 1

DOMAIN_WEIGHTS: dict[Domain, float] = {
    Domain.identity_access: 0.20,
    Domain.network_config: 0.15,
    Domain.vulnerability_management: 0.15,
    Domain.backup_recovery: 0.15,
    Domain.monitoring_detection: 0.15,
    Domain.incident_response: 0.10,
    Domain.compliance_alignment: 0.10,
}

_DEDUCTIONS = {
    Severity.critical: CRITICAL_DEDUCTION,
    Severity.high: HIGH_DEDUCTION,
    Severity.medium: MEDIUM_DEDUCTION,
    Severity.low: LOW_DEDUCTION,
}


def tier_for_score(score: float) -> RiskTier:
    if score >= 80:
        return RiskTier.low
    if score >= 60:
        return RiskTier.medium
    if score >= 40:
        return RiskTier.high
    return RiskTier.critical


def score_domain(domain: Domain, findings: list[Finding]) -> tuple[float, RiskTier, str]:
    score = 100.0
    counts: dict[Severity, int] = {}
    for finding in findings:
        if finding.domain != domain:
            continue
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
        score -= _DEDUCTIONS[finding.severity]

    score = max(0.0, score)
    tier = tier_for_score(score)
    justification = (
        "; ".join(f"{count} {severity.value} finding(s)" for severity, count in counts.items())
        or "No findings recorded for this domain."
    )
    return score, tier, justification


def score_all_domains(findings: list[Finding]) -> dict[Domain, tuple[float, RiskTier, str]]:
    return {domain: score_domain(domain, findings) for domain in Domain}


def overall_score(domain_scores: dict[Domain, tuple[float, RiskTier, str]]) -> tuple[float, RiskTier]:
    weighted_sum = sum(
        domain_scores[domain][0] * weight for domain, weight in DOMAIN_WEIGHTS.items()
    )
    return weighted_sum, tier_for_score(weighted_sum)
