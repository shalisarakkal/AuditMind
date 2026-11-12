"""Read-only foundation contracts; no consolidation write request is exposed."""
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class ConsolidationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_decision_id: uuid.UUID


class ConsolidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    pair_key: str
    finding_a_id: uuid.UUID
    finding_b_id: uuid.UUID
    canonical_finding_id: uuid.UUID
    canonical_decision_id: uuid.UUID
    version: int
    state: Literal["active", "undone"]
    created_at: datetime
    updated_at: datetime


class ConsolidationDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: int
    state: Literal["active", "undone"]
    rationale: str
    actor_label: str
    created_at: datetime


class ConsolidationPage(BaseModel):
    items: list[ConsolidationRead]
    has_more: bool
    limit: int
    offset: int
    apply_available: Literal[False] = False
    availability_reason: str = "Retained ledger only; consolidation publication is not enabled."


class ConsolidationHistoryPage(BaseModel):
    items: list[ConsolidationDecisionRead]
    has_more: bool
    limit: int
    before_version: int | None
    apply_available: Literal[False] = False
    availability_reason: str = "Retained ledger only; consolidation publication is not enabled."
