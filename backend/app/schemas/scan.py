import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ScanStatus


class ScanCreate(BaseModel):
    scan_type: str
    scope: str | None = None
    source: str | None = None


class ScanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    scan_type: str
    scope: str | None
    status: ScanStatus
    started_at: datetime | None
    completed_at: datetime | None
    source: str | None
    filename: str | None
    summary: dict | None
    profile: str | None
    started_by: uuid.UUID | None
    dismissed_at: datetime | None
    progress: dict | None
    # Set only while the background worker runs the import (it checks in
    # every ~15 s); None for one run during its request.
    heartbeat_at: datetime | None


def brief_scan(scan) -> ScanRead:
    """A scan without its report's row lists (up to 1,000 errors and
    warnings each), for lists that show only names, status and counts."""
    brief = ScanRead.model_validate(scan)
    if brief.summary:
        brief.summary = {k: v for k, v in brief.summary.items() if k not in ("errors", "warnings")}
    return brief
