from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class RiskPolicyRead(BaseModel):
    enabled: bool = True
    platform_enabled: bool = True
    enabled_override: bool | None = None
    version: int = 0
    platform_version: int = 0
    policy_version: str = "verified-status-v1"


class RiskPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    enabled_override: bool | None


class PlatformRiskPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    enabled: bool


class ProofSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)
    expected_workflow_version: int = Field(ge=0)
    source_reference: str = Field(min_length=1, max_length=2048)
    observed_at: AwareDatetime
    note: str = Field(min_length=1, max_length=4000)


class ProofReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    expected_workflow_version: int = Field(ge=0)
    decision: Literal["approved", "rejected", "revoked"]
    expires_at: AwareDatetime | None = None
    note: str = Field(min_length=1, max_length=4000)
    evidence_reviewed: bool = False
    self_review_acknowledged: bool = False
