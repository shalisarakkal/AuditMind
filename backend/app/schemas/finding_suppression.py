"""Read contracts for the suppression ledger foundation."""
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SuppressionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    identity_version: str
    candidate_key: str
    finding_id: uuid.UUID
    version: int
    state: Literal["suppressed", "cleared"]
    label: str = ""
    reappearance_count: int = 0
    created_at: datetime
    updated_at: datetime


class SuppressionPage(BaseModel):
    items: list[SuppressionRead]
    has_more: bool
    limit: int
    offset: int
    mutations_available: Literal[True] = True
    availability_reason: str = "Only current reviewed native Nessus identities are eligible. New uploads require identity review."


class SuppressionDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: int
    state: Literal["suppressed", "cleared"]
    rationale: str
    actor_label: str
    created_at: datetime


class SuppressionHistoryPage(BaseModel):
    items: list[SuppressionDecisionRead]
    has_more: bool
    limit: int
    before_version: int | None


class SuppressionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["suppress", "clear"]
    finding_id: uuid.UUID | None = None
    suppression_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def valid_target(self):
        if self.action == "suppress" and (not self.finding_id or self.suppression_id):
            raise ValueError("Choose one finding to suppress")
        if self.action == "clear" and (not self.suppression_id or self.finding_id):
            raise ValueError("Choose one suppression to clear")
        return self


class SuppressionWrite(SuppressionTarget):
    request_id: uuid.UUID
    review_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_version: int = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=2000)
    confirm: bool

    @field_validator("rationale")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A rationale is required")
        return value.strip()
