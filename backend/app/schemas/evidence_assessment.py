"""New provider contract, independent of retained schema1/2 snapshots."""
from typing import Literal, Self
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.enums import Domain, RiskTier
from app.schemas.report_ai import RemediationActionAI
from app.services.scoring_service import tier_for_score

EvidenceStatus = Literal['sufficient', 'limited', 'insufficient', 'conflicting']


class EvidenceDomain(BaseModel):
    model_config = ConfigDict(extra='forbid')
    domain: Domain
    evidence_status: EvidenceStatus
    evidence_reason: str = Field(min_length=1, max_length=4000)
    evidence_finding_ids: list[UUID] = Field(max_length=20)
    citation_ids: list[str] = Field(max_length=8)
    score: int | None = Field(ge=0, le=100, strict=True)
    tier: RiskTier | None
    justification: str = Field(min_length=1, max_length=4000)
    strengths: list[str] = Field(max_length=20)
    weaknesses: list[str] = Field(max_length=20)

    @model_validator(mode='after')
    def invariants(self) -> Self:
        for values in (self.evidence_finding_ids, self.citation_ids):
            if len(values) != len(set(values)):
                raise ValueError('Evidence references must be unique')
        if not self.evidence_reason.strip() or not self.justification.strip():
            raise ValueError('Evidence explanations cannot be blank')
        if self.evidence_status == 'sufficient':
            if self.score is None or self.tier != tier_for_score(self.score):
                raise ValueError('Sufficient domain requires score and matching tier')
        elif self.score is not None or self.tier is not None:
            raise ValueError('Unqualified domains must have null score and tier')
        count = len(self.evidence_finding_ids) + len(self.citation_ids)
        if self.evidence_status in ('sufficient', 'limited') and not count:
            raise ValueError('Assessed evidence requires source references')
        if self.evidence_status == 'conflicting' and count < 2:
            raise ValueError('Conflict requires at least two observations')
        return self


class EvidenceRemediation(RemediationActionAI):
    model_config = ConfigDict(extra='forbid')
    confidence: float = Field(ge=0, le=1, strict=True, allow_inf_nan=False)


class EvidenceAssessment(BaseModel):
    """Provider cannot submit overall scores, provenance or qualification metadata."""
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=255)
    executive_summary: str = Field(min_length=1, max_length=8000)
    resilience_summary: str = Field(min_length=1, max_length=8000)
    domains: list[EvidenceDomain] = Field(min_length=7, max_length=7)
    remediations: list[EvidenceRemediation] = Field(max_length=10)

    @model_validator(mode='after')
    def domains_once(self) -> Self:
        if {d.domain for d in self.domains} != set(Domain):
            raise ValueError('Each of the seven domains must appear exactly once')
        if len({a.model_dump_json() for a in self.remediations}) != len(self.remediations):
            raise ValueError('Exact duplicate remediation actions are not allowed')
        return self


class EvidenceSnapshot(EvidenceAssessment):
    overall_score: int | None = Field(ge=0, le=100, strict=True)
    overall_tier: RiskTier | None
    assessment_status: Literal['complete', 'partial']
    compliance_citations: list[dict] = Field(default_factory=list)
    total_assets: int = 0
    total_findings: int = 0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    frameworks_evaluated: list[str] = Field(default_factory=list)
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def derived_fields(self) -> Self:
        from app.services.evidence_policy import WEIGHTS
        complete = all(d.evidence_status == 'sufficient' for d in self.domains)
        if complete:
            expected = (sum(d.score * WEIGHTS[d.domain.value] for d in self.domains) + 50) // 100
            if (self.assessment_status != 'complete' or self.overall_score != expected
                    or self.overall_tier != tier_for_score(expected)):
                raise ValueError('Overall fields must match server aggregation')
        elif self.assessment_status != 'partial' or self.overall_score is not None or self.overall_tier is not None:
            raise ValueError('Partial assessment requires null overall score and tier')
        return self
