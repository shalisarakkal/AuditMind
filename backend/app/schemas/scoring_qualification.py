"""Draft input cannot assign approval, policy identity or reviewer identity."""
from datetime import datetime, timezone
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.models.enums import Domain
from app.services.evidence_policy import PROFILES


class DraftObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str
    source_type: Literal["finding", "document_version"] = "finding"
    source_id: UUID
    source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    observed_at: datetime


class QualificationDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0, strict=True)
    scope: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=4000)
    observations: list[DraftObservation] = Field(default_factory=list, max_length=100)
    inventory_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observations_are_unambiguous(self) -> Self:
        keys = [(o.objective, o.source_type, o.source_id) for o in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate objective/source observation")
        if any(o.observed_at.tzinfo is None for o in self.observations):
            raise ValueError("Observation dates require time zones")
        return self

    def validate_domain(self, domain: Domain) -> None:
        if any(o.objective not in PROFILES[domain.value] for o in self.observations):
            raise ValueError("Observation objective does not belong to this domain")


class QualificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    domain: Domain
    policy_version: str
    status: Literal["draft", "approved", "revoked", "conflicting"]
    scope: str
    rationale: str
    observations: list[DraftObservation]
    version: int
    updated_by: UUID | None
    updated_at: datetime
    inventory_sha256: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    expires_at: datetime | None = None
    review_note: str | None = None
    review_attestation: dict = Field(default_factory=dict)

    @field_validator("updated_at", "reviewed_at", "expires_at")
    @classmethod
    def canonical_instant(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class QualificationReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1, strict=True)
    inventory_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    decision: Literal["approve", "conflicting"] = "approve"
    expires_at: datetime
    note: str = Field(min_length=1, max_length=4000)
    operational_review: StrictBool
    covers_entire_inventory: StrictBool
    conflicts_reviewed: StrictBool

    @field_validator("expires_at")
    @classmethod
    def expiry_requires_zone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Expiry requires a time zone")
        return value


class QualificationRevocation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1, strict=True)
    note: str = Field(min_length=1, max_length=4000)


class ScoringSettingsRead(BaseModel):
    evidence_qualified_enabled: bool
    version: int
    available: bool = False


class ScoringSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_qualified_enabled: StrictBool
    expected_version: int = Field(ge=0, strict=True)
