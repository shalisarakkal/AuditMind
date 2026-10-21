"""Pydantic schemas for structured Claude AI audit reasoning, scoring, and report generation."""

from typing import Any, Literal, Self
from pydantic import BaseModel, Field, model_validator

from app.models.enums import Domain, RiskTier


def _tier_for_score(score: int) -> RiskTier:
    if score >= 80:
        return RiskTier.low
    if score >= 60:
        return RiskTier.medium
    if score >= 30:
        return RiskTier.high
    return RiskTier.critical


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
    related_controls: list[str] = Field(default_factory=list)
    affected_asset_types: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)


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
