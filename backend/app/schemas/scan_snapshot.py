import uuid
from datetime import datetime, timezone
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class DeclarationFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    snapshot_kind: Literal["complete", "partial", "incremental", "failed", "cancelled"]
    tool_name: str = Field(min_length=1, max_length=200)
    tool_instance_id: str = Field(min_length=1, max_length=200)
    tool_configuration_id: str = Field(min_length=1, max_length=200)
    targets: list[str] = Field(min_length=1, max_length=500)
    exclusions: list[str] = Field(default_factory=list, max_length=500)
    unreachable_targets: list[str] = Field(default_factory=list, max_length=500)
    coverage_confirmed: bool = False
    source_snapshot_at: AwareDatetime | None = None

    @field_validator("source_snapshot_at")
    @classmethod
    def source_time(cls, value):
        if value is not None:
            try:
                return value.astimezone(timezone.utc)
            except (ValueError, OverflowError) as exc:
                raise ValueError("Source snapshot time must convert to a valid UTC timestamp") from exc
        return None

    @field_validator("targets", "exclusions", "unreachable_targets")
    @classmethod
    def scope_entries(cls, values):
        if any(not entry.strip() or len(entry.strip()) > 255 for entry in values):
            raise ValueError("Scope entries must contain 1 to 255 characters")
        return sorted({entry.strip() for entry in values})

    @model_validator(mode="after")
    def complete_coverage(self):
        if self.snapshot_kind == "complete" and (not self.coverage_confirmed or self.unreachable_targets or self.source_snapshot_at is None):
            raise ValueError("Complete snapshots require a source timestamp, confirmed coverage and no unreachable targets")
        return self


class SnapshotWrite(DeclarationFields):
    expected_version: int = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=12000)


class SnapshotRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    rationale: str = Field(min_length=1, max_length=12000)


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    scan_id: uuid.UUID
    version: int
    state: Literal["declared", "revoked"]
    declaration: DeclarationFields
    scan_context: dict
    rationale: str
    actor_label: str
    created_at: datetime


class SnapshotView(BaseModel):
    scan: dict
    declaration: SnapshotRead | None
    declaration_blockers: list[str]
    complete_blockers: list[str]


class SnapshotComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_scan_id: uuid.UUID
    current_scan_id: uuid.UUID
    baseline_version: int = Field(ge=1)
    current_version: int = Field(ge=1)
    candidate_offset: int = Field(default=0, ge=0)
    candidate_limit: int = Field(default=50, ge=1, le=100)


class SnapshotQueueRequest(SnapshotComparisonRequest):
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class NotObservedCandidate(BaseModel):
    finding_id: uuid.UUID
    baseline_observation_id: uuid.UUID
    reviewable_baseline_observation_count: int
    asset_id: uuid.UUID | None
    description: str | None
    category: str | None
    domain: str
    severity: str
    workflow_status: str
    workflow_version: int
    baseline_recorded_at: datetime


class SnapshotComparison(BaseModel):
    reviewed_at: datetime
    baseline: SnapshotView
    current: SnapshotView
    declared_metadata_matches: bool
    absence_eligible: bool
    blocking_reasons: list[str]
    absence_blockers: list[str]
    scope_differences: dict[str, list[str]]
    review_candidates: list[NotObservedCandidate]
    candidate_count: int
    candidate_offset: int
    candidate_limit: int
    baseline_reviewable_observations: int
    current_reviewable_observations: int
    baseline_unreviewable_observations: int
    current_unreviewable_observations: int
    ambiguous_baseline_identity_count: int
    review_token: str | None = None
    review_queue_batch_id: uuid.UUID | None = None
    review_queue_item_count: int = 0


class AbsenceReviewDecisionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    action: Literal["keep_active", "reopen"]
    rationale: str = Field(min_length=1, max_length=12000)


class AbsenceReviewQueueItem(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    candidate: NotObservedCandidate
    comparison: dict
    state: Literal["pending", "kept_active"]
    decision_version: int
    rationale: str | None = None
    actor_label: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class AbsenceReviewQueuePage(BaseModel):
    items: list[AbsenceReviewQueueItem]
    total: int
    limit: int
    offset: int
