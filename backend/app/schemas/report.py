import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReportStatus


class ReportCreate(BaseModel):
    title: str
    period_start: date | None = None
    period_end: date | None = None
    format: str = "html"


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    period_start: date | None
    period_end: date | None
    status: ReportStatus
    generated_at: datetime | None
    format: str | None
    location: str | None
