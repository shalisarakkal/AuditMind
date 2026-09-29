"""Rule-based v1 risk scoring, per RISL_SCORING.md. Deterministic baseline;
Claude-driven qualitative scoring (RAG + narrative justification) layers on top of
this in a later milestone.
"""

import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

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


# Findings per domain and severity: all the scoring needs, so callers with
# many findings can have the database count them (see dashboard.py).
SeverityCounts = dict[Domain, dict[Severity, int]]


def count_findings(findings: list[Finding]) -> SeverityCounts:
    counts: SeverityCounts = {}
    for finding in findings:
        by_severity = counts.setdefault(finding.domain, {})
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    return counts


def count_org_findings(db: Session, org_id: uuid.UUID) -> SeverityCounts:
    """The org's findings per domain and severity, counted by the database."""
    counts: SeverityCounts = {}
    rows = (
        db.query(Finding.domain, Finding.severity, func.count())
        .filter(Finding.org_id == org_id)
        .group_by(Finding.domain, Finding.severity)
    )
    for domain, severity, count in rows:
        counts.setdefault(domain, {})[severity] = count
    return counts


def score_from_counts(counts: dict[Severity, int]) -> tuple[float, RiskTier, str]:
    """One domain's score from its findings per severity (most severe first
    in the justification)."""
    score = max(0.0, 100.0 - sum(_DEDUCTIONS[severity] * count for severity, count in counts.items()))
    justification = (
        "; ".join(f"{counts[severity]} {severity.value} finding(s)" for severity in Severity if counts.get(severity))
        or "No findings recorded for this domain."
    )
    return score, tier_for_score(score), justification


def score_domain(domain: Domain, findings: list[Finding]) -> tuple[float, RiskTier, str]:
    return score_from_counts(count_findings(findings).get(domain, {}))


def score_all_domains(findings: list[Finding]) -> dict[Domain, tuple[float, RiskTier, str]]:
    return score_all_from_counts(count_findings(findings))


def score_all_from_counts(counts: SeverityCounts) -> dict[Domain, tuple[float, RiskTier, str]]:
    return {domain: score_from_counts(counts.get(domain, {})) for domain in Domain}


def overall_score(domain_scores: dict[Domain, tuple[float, RiskTier, str]]) -> tuple[float, RiskTier]:
    weighted_sum = sum(
        domain_scores[domain][0] * weight for domain, weight in DOMAIN_WEIGHTS.items()
    )
    return weighted_sum, tier_for_score(weighted_sum)
