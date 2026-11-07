import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class FindingObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    finding_id: uuid.UUID
    import_id: uuid.UUID
    scan_id: uuid.UUID | None
    occurrence: int
    source_row: int
    source: str
    scan_type: str
    profile: str | None
    filename: str | None
    observed_at: datetime | None
    recorded_at: datetime
    asset_identity: dict
    source_identity: dict
    reconciliation_eligible: bool
    ineligibility_reasons: list[str]
    # Derived on the bounded observation page, never a verified binding.
    identity_assessment: dict
    identity_binding: dict | None = None
    payload: dict
