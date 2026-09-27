import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import Domain, RiskTier


class RiskScoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    asset_id: uuid.UUID | None
    dimension: Domain
    score: float
    tier: RiskTier
    justification: str | None
    created_at: datetime


class RiskAssessmentResult(BaseModel):
    domains: list[RiskScoreRead]
    overall_score: float
    overall_tier: RiskTier
    remediation: list[str]
