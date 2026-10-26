from datetime import datetime
from pydantic import BaseModel

from app.models.enums import Domain, RiskTier, Severity
from app.schemas.finding import FindingRead
from app.schemas.scan import ScanRead


class DomainScore(BaseModel):
    domain: Domain
    score: float
    tier: RiskTier
    justification: str


class SecuritySummary(BaseModel):
    window_start: datetime
    window_end: datetime
    counts: dict[str, int]


class DashboardSummary(BaseModel):
    """Computed live from the org's current findings (nothing is persisted;
    POST /orgs/{org_id}/risk/score records snapshots)."""

    overall_score: float
    overall_tier: RiskTier
    domains: list[DomainScore]
    top_findings: list[FindingRead]
    recent_scans: list[ScanRead]
    asset_count: int
    findings_by_severity: dict[Severity, int]
