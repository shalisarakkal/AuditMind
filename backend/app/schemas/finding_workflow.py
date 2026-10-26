"""Explicit patches: omitted values are unchanged, null clears optional fields."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services.workflow_deadlines import validate_deadline_zone

WorkflowStatus = Literal["open", "accepted_risk", "mitigated", "resolved", "false_positive"]


class WorkflowPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: WorkflowStatus | None = None
    assignee_id: UUID | None = None
    due_date: date | None = None
    risk_review_date: date | None = None
    deadline_timezone: str | None = None

    @field_validator("deadline_timezone")
    @classmethod
    def valid_zone(cls, value):
        return validate_deadline_zone(value) if value is not None else value
    rationale: str = Field(min_length=1, max_length=2000)
    verification: str | None = Field(default=None, max_length=2000)

    @field_validator("rationale", "verification")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def status_not_null(self):
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("Status cannot be null")
        if any(name in self.model_fields_set and getattr(self, name) is not None for name in ("due_date", "risk_review_date")) and self.deadline_timezone is None:
            raise ValueError("Setting a deadline requires the entering client's IANA timezone")
        if "deadline_timezone" in self.model_fields_set and (self.deadline_timezone is None or not any(
            name in self.model_fields_set and getattr(self, name) is not None for name in ("due_date", "risk_review_date"))):
            raise ValueError("Timezone requires an explicitly set deadline date")
        return self


class WorkflowUpdate(WorkflowPatch):
    expected_version: int = Field(ge=0, strict=True)


class WorkflowTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: UUID
    expected_version: int = Field(ge=0, strict=True)


class WorkflowBulk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targets: list[WorkflowTarget] = Field(min_length=1, max_length=100)
    patch: WorkflowPatch

    @model_validator(mode="after")
    def unique_targets(self):
        if len({t.finding_id for t in self.targets}) != len(self.targets):
            raise ValueError("Finding IDs must be unique")
        return self


class SavedWorkflowNote(BaseModel):
    text: str
    actor_label: str
    created_at: datetime


class WorkflowRead(BaseModel):
    finding_id: UUID
    status: WorkflowStatus
    version: int
    assignee_id: UUID | None
    assignee_available: bool
    assignee_label: str | None = None
    due_date: date | None
    risk_review_date: date | None
    updated_at: datetime | None
    latest_rationale: SavedWorkflowNote | None = None
    latest_verification: SavedWorkflowNote | None = None
    due_timezone: str | None = None
    due_expires_at: datetime | None = None
    risk_review_timezone: str | None = None
    risk_review_expires_at: datetime | None = None


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_id: UUID | None
    actor_label: str
    version: int
    before: dict
    after: dict
    rationale: str
    verification: str | None
    created_at: datetime
    before_assignee_label: str | None = None
    after_assignee_label: str | None = None
