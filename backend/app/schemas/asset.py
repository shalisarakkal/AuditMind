import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    """`type` is a category or a known name for one ("laptop" -> workstation);
    see app/services/asset_types.py. A name also becomes the subtype unless
    one is given."""

    type: str
    subtype: str | None = Field(default=None, max_length=100)
    hostname: str | None = None
    ip: str | None = None
    cloud_id: str | None = None
    environment: str | None = None
    criticality: str | None = None
    tags: list[str] | None = None
    details: dict = {}


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    type: str
    subtype: str | None
    type_known: bool
    hostname: str | None
    ip: str | None
    cloud_id: str | None
    environment: str | None
    criticality: str | None
    tags: list[str] | None
    details: dict
    created_at: datetime


class AssetFacets(BaseModel):
    """The values each pick-list filter of the assets list can offer; ""
    stands for "no value"."""

    type: list[str]
    subtype: list[str]
    environment: list[str]
    criticality: list[str]
