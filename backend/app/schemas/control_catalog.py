import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from app.models.enums import Domain


class ControlMappingSummary(BaseModel):
    available: bool = True
    status: Literal["mapped", "unmapped"] = "unmapped"
    proposal_pending: bool = False
    version: int = 0
    catalog_id: uuid.UUID | None = None


class MappingKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = Field(max_length=100)
    domain: Domain
    category: str | None = Field(max_length=100)
    expected_version: StrictInt = Field(ge=0, le=2147483646)
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("rationale")
    @classmethod
    def rationale_text(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            raise ValueError("A readable change rationale is required")
        return value


class MappingProposal(MappingKey):
    catalog_id: uuid.UUID
    control_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)

    @field_validator("control_ids")
    @classmethod
    def distinct_controls(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Choose each control only once")
        return value


class MappingApproval(MappingKey):
    proposal_version: StrictInt = Field(ge=1)
