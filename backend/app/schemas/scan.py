import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ScanStatus


class ScanCreate(BaseModel):
    scan_type: str
    scope: str | None = None
    source: str | None = None


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    scan_type: str
    scope: str | None
    status: ScanStatus
    started_at: datetime | None
    completed_at: datetime | None
    source: str | None
