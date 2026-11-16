import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

Criticality = Literal["critical", "high", "medium", "low"]
class AssetContextPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0, le=2147483646)
    owner_id: uuid.UUID | None = None
    environment: str | None = Field(default=None, max_length=50)
    business_criticality: Criticality | None = None
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("environment", "rationale", mode="before")
    @classmethod
    def clean_text(cls, value, info):
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("Use text")
        if any(ord(char)<32 and char not in "\n\r\t" for char in value):
            raise ValueError("Control characters are not allowed")
        value=value.strip()
        if info.field_name=="environment":
            if any(ord(char)<32 for char in value):raise ValueError("Environment must fit on one line")
            return value or None
        if not value:raise ValueError("A rationale is required")
        return value

class AssetContextRead(BaseModel):
    available: bool = True
    version: int = 0
    owner_id: uuid.UUID | None = None
    owner_label: str | None = None
    owner_status: Literal["unassigned","active","inactive","former"] = "unassigned"
    environment: str | None = None
    business_criticality: Criticality | None = None
    updated_at: datetime | None = None
    asset_archived: bool = False

class AssetContextHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_label: str
    version: int
    before: dict
    after: dict
    rationale: str
    created_at: datetime
