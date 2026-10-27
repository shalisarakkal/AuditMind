from datetime import datetime
from typing import Literal
from pydantic import BaseModel

from app.models.enums import Domain, RiskTier, Severity
from app.schemas.finding import FindingRead
from app.schemas.scan import ScanRead


class DomainScore(BaseModel):
    domain: Domain
    score: float | None
    tier: RiskTier | None
    assessment_status: Literal["not_assessed", "findings_based"] = "findings_based"
    justification: str


class SecuritySummary(BaseModel):
    window_start: datetime
    window_end: datetime
    counts: dict[str, int]


class DashboardSummary(BaseModel):
    """Computed live from the org's current findings (nothing is persisted;
    POST /orgs/{org_id}/risk/score records snapshots). Empty active inventory
    AND findings returns not_assessed/null scores; findings_based is a baseline,
    not an assertion that domain evidence coverage has been qualified."""

    overall_score: float | None
    overall_tier: RiskTier | None
    assessment_status: Literal["not_assessed", "findings_based"] = "findings_based"
    domains: list[DomainScore]
    top_findings: list[FindingRead]
    recent_scans: list[ScanRead]
    asset_count: int
    findings_by_severity: dict[Severity, int]
