"""Pydantic schemas for structured Claude AI audit reasoning, scoring, and report generation."""

from typing import Any, Literal, Self
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

from app.models.enums import Domain, RiskTier
from app.services.scoring_service import tier_for_score


def _tier_for_score(score: int) -> RiskTier:
    return tier_for_score(score)


class DomainScoreAI(BaseModel):
    domain: Domain
    score: int = Field(ge=0, le=100)
    tier: RiskTier
    justification: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_tier(self) -> Self:
        if self.tier != _tier_for_score(self.score):
            raise ValueError("Domain tier must match its score")
        return self


class RemediationActionAI(BaseModel):
    title: str
    description: str
    priority: Literal["Critical", "High", "Medium", "Low"]
    domain: Domain
    estimated_effort: Literal["Quick Win", "Moderate", "Major Project"]
    expected_impact: str
    # Null is reserved for explicitly non-AI test snapshots; generation rejects it.
    confidence: float | None = Field(ge=0, le=1, allow_inf_nan=False, strict=True)
    affected_finding_ids: list[UUID]
    affected_asset_ids: list[UUID]
    related_controls: list[str] = Field(default_factory=list)
    affected_asset_types: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_references(self) -> Self:
        for ids in (self.affected_finding_ids, self.affected_asset_ids):
            if len(ids) != len(set(ids)):
                raise ValueError("Remediation references must be unique")
        return self


class ComplianceCitation(BaseModel):
    control_id: str
    framework: str
    title: str
    content: str
    content_ref: str | None = None
    related_findings_count: int = 0


class AuditReportSnapshot(BaseModel):
    title: str
    executive_summary: str
    overall_score: int = Field(ge=0, le=100)
    overall_tier: RiskTier
    resilience_summary: str
    domains: list[DomainScoreAI]
    remediations: list[RemediationActionAI]
    compliance_citations: list[dict[str, Any]] = Field(default_factory=list)
    total_assets: int = 0
    total_findings: int = 0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    frameworks_evaluated: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_assessment(self) -> Self:
        if self.overall_tier != _tier_for_score(self.overall_score):
            raise ValueError("Overall tier must match its score")
        if len(self.domains) != len(Domain) or {item.domain for item in self.domains} != set(Domain):
            raise ValueError("Assessment must include each domain exactly once")
        return self
