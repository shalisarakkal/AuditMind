from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, StrictBool
from app.models.enums import Domain


class SourceReference(BaseModel):
    source_type: Literal["finding", "document_version"]
    source_id: UUID
    source_sha256: str = Field(pattern="^[0-9a-f]{64}$")


class CachedDomain(BaseModel):
    domain: Domain
    evidence_status: Literal["insufficient", "limited", "conflicting", "sufficient"]
    reason_code: str
    eligible: StrictBool
    qualification_id: UUID | None
    version: int | None
    scope: str | None
    reviewed_at: datetime | None
    expires_at: datetime | None
    observed_at: list[datetime]
    source_references: list[SourceReference]


class CachedInventory(BaseModel):
    scope_kind: Literal["organization_all"]
    binding_version: str
    inventory_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    asset_count: int = Field(ge=0)
    finding_count: int = Field(ge=0)


class EvaluationResult(BaseModel):
    policy_version: str
    evaluated_at: datetime
    inventory: CachedInventory
    domains: list[CachedDomain] = Field(min_length=7, max_length=7)
    qualified_domain_count: int = Field(ge=0, le=7)
    assessment_status: Literal["complete", "partial", "not_assessed"]
    overall_reason: str | None = None


class EvidenceEvaluationRead(BaseModel):
    id: UUID
    org_id: UUID
    status: Literal["pending", "running", "completed", "failed", "cancelled", "superseded"]
    created_at: datetime
    run_started_at: datetime | None
    completed_at: datetime | None
    cancel_requested_at: datetime | None
    progress: dict | None
    error_message: str | None
    is_current: bool
    can_cancel: bool
    result: EvaluationResult | None
