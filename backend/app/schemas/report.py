"""Pydantic schemas for reports API (creation, reading, details, paged responses)."""

import uuid
from datetime import date, datetime
from typing import Any, Self

from pydantic import AliasPath, BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ReportStatus


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    period_start: date | None = None
    period_end: date | None = None
    frameworks: list[str] = Field(default_factory=lambda: ["CIS", "NIST", "ISO"])
    format: str = "json"

    @model_validator(mode="after")
    def valid_period(self) -> Self:
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    assessment_type: str | None = Field(
        default=None,
        validation_alias=AliasPath("data", "provenance", "assessment_type"),
    )
    period_start: date | None = None
    period_end: date | None = None
    frameworks: str | None = None
    status: ReportStatus
    generated_at: datetime | None = None
    format: str | None = None
    location: str | None = None
    error_message: str | None = None
    started_by: uuid.UUID | None = None
    created_at: datetime
    overall_score: int | None = Field(default=None, validation_alias=AliasPath("data", "overall_score"))


class ReportDetail(ReportRead):
    data: dict[str, Any] | None = None


class ReportListResponse(BaseModel):
    items: list[ReportRead]
    total: int
