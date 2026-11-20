from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ProofSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0, strict=True)
    expected_workflow_version: int = Field(ge=0, strict=True)
    source_reference: str = Field(min_length=1, max_length=2048)
    observed_at: AwareDatetime
    note: str = Field(min_length=1, max_length=4000)


class ProofDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1, strict=True)
    expected_workflow_version: int = Field(ge=0, strict=True)
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1, max_length=4000)
    evidence_reviewed: bool = False
    self_review_acknowledged: bool = False
