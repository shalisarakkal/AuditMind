import uuid

from pydantic import BaseModel

from app.models.enums import ScanStatus


class RowError(BaseModel):
    """A row that couldn't be imported. `row` is the line number for CSV
    (header = line 1), the 1-based record position for JSON, the 1-based
    ReportItem position for .nessus, and 0 for a problem with the whole file."""

    row: int
    message: str


class ImportReport(BaseModel):
    created: int = 0
    updated: int = 0
    # Assets left untouched (strategy "skip"), and Nessus Info items when
    # Info is set to be skipped.
    skipped: int = 0
    # Findings identical to one already recorded (same asset, source, category).
    duplicates: int = 0
    failed: int = 0
    errors: list[RowError] = []


class ImportResponse(BaseModel):
    """Files processed during the request come back completed/failed with the
    report. Larger files come back pending with no report: poll
    GET /orgs/{org_id}/scans/{scan_id} until status is completed or failed;
    the report is then in the scan's summary."""

    scan_id: uuid.UUID
    status: ScanStatus
    report: ImportReport | None = None
