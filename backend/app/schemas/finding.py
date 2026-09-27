import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import Domain, Severity


class FindingCreate(BaseModel):
    asset_id: uuid.UUID | None = None
    scan_id: uuid.UUID | None = None
    category: str | None = None
    domain: Domain
    severity: Severity
    description: str | None = None
    raw_data: dict | None = None
    source: str | None = None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    asset_id: uuid.UUID | None
    scan_id: uuid.UUID | None
    category: str | None
    domain: Domain
    severity: Severity
    description: str | None
    source: str | None
    created_at: datetime
