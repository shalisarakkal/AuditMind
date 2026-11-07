import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("name", "rationale")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class IdentityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("rationale")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class IdentityBind(IdentityDecision):
    tool_id: uuid.UUID
    expected_tool_version: int = Field(ge=1)
    canonical_asset_id: uuid.UUID
    confirm_mapping: bool


class IdentityReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_observation_id: uuid.UUID


class IdentityCarryForward(IdentityReference, IdentityDecision):
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirm_mapping: bool
