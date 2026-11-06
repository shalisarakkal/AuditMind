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


class SnapshotComparison(BaseModel):
    reviewed_at: datetime
    baseline: SnapshotView
    current: SnapshotView
    declared_metadata_matches: bool
    absence_eligible: Literal[False] = False
    blocking_reasons: list[str]
    absence_blockers: list[str] = ["stable_finding_identity_and_reconciliation_not_enabled"]
    scope_differences: dict[str, list[str]]
    not_observed_finding_ids: None = None
