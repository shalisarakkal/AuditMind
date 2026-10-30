from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.enums import Domain, RiskTier, Severity
from app.schemas.finding import FindingRead
from app.schemas.scan import ScanRead


class DomainScore(BaseModel):
    domain: Domain
    score: float | None
    tier: RiskTier | None
    assessment_status: Literal["not_assessed", "findings_based", "evidence_qualified"] = "findings_based"
    justification: str
    evidence_status: Literal["insufficient", "limited", "conflicting", "sufficient"] | None = None
    evidence_reason: str | None = None
    qualification_id: UUID | None = None
    qualification_version: int | None = None
    qualification_scope: str | None = None
    reviewed_at: datetime | None = None
    expires_at: datetime | None = None
    observed_at: list[datetime] = Field(default_factory=list)
    source_references: list[dict] = Field(default_factory=list)


class SecuritySummary(BaseModel):
    window_start: datetime
    window_end: datetime
    counts: dict[str, int]
    snapshot_generated_at: datetime | None = None


class DashboardSummary(BaseModel):
    """Scores derived from live or explicitly timestamped saved inventory;
    evidence eligibility always uses current revision-bound checks.
    POST /orgs/{org_id}/risk/score independently records baseline snapshots.
    Empty active inventory
    AND findings returns not_assessed/null scores; findings_based is a baseline,
    not an assertion that domain evidence coverage has been qualified."""

    overall_score: float | None
    overall_tier: RiskTier | None
    assessment_status: Literal["not_assessed", "findings_based", "partial", "complete"] = "findings_based"
    scoring_mode: Literal["findings_based", "evidence_qualified"] = "findings_based"
    settings_version: int = 0
    evidence_revision: int = 0
    qualified_domain_count: int = 0
    evaluation_state: Literal["not_required", "current", "not_current"] = "not_required"
    qualification_evaluated_at: datetime | None = None
    evaluation_id: UUID | None = None
    baseline_method: str = "rule-v1"
    policy_version: str | None = None
    aggregation_version: str = "weighted-seven-float-v1"
    overall_reason: str | None = None
    domains: list[DomainScore]
    top_findings: list[FindingRead]
    recent_scans: list[ScanRead]
    asset_count: int
    findings_by_severity: dict[Severity, int]
    snapshot_generated_at: datetime | None = None
    snapshot_stale: bool = False
    snapshot_refresh_status: str | None = None
    snapshot_error: str | None = None
    security_summary: SecuritySummary | None = None


class DashboardPending(BaseModel):
    snapshot_state: Literal["pending"] = "pending"
    snapshot_refresh_status: str
    snapshot_error: str | None = None


class DashboardSettings(BaseModel):
    enabled: bool = False
    refresh_interval_seconds: int = Field(3600, ge=60, le=86400)
    version: int = 0


class DashboardSettingsUpdate(BaseModel):
    enabled: bool
    refresh_interval_seconds: int = Field(3600, ge=60, le=86400)
    expected_version: int = Field(ge=0)


class OrganizationDashboardSettings(BaseModel):
    enabled: bool
    platform_refresh_interval_seconds: int
    refresh_interval_seconds: int
    refresh_interval_override_seconds: int | None
    version: int


class OrganizationDashboardSettingsUpdate(BaseModel):
    refresh_interval_override_seconds: int | None = Field(..., ge=60, le=86400)
    expected_version: int = Field(ge=0)
