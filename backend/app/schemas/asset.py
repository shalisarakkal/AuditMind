import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetCreate(BaseModel):
    type: str
    hostname: str | None = None
    ip: str | None = None
    cloud_id: str | None = None
    environment: str | None = None
    criticality: str | None = None
    tags: list[str] | None = None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    type: str
    hostname: str | None
    ip: str | None
    cloud_id: str | None
    environment: str | None
    criticality: str | None
    tags: list[str] | None
    created_at: datetime
