import uuid

from pydantic import BaseModel

from app.models.enums import ScanStatus


class RowError(BaseModel):
    """A row that couldn't be imported. `row` is the line number for CSV
    (header = line 1), the 1-based record position for JSON, the 1-based
    ReportItem position for .nessus, and 0 for a problem with the whole file."""

    row: int
    message: str


class RowWarning(BaseModel):
    """A row that was imported, but with something worth checking (an unusual
    IP, a value that couldn't be read and was defaulted). Same `row` numbering
    as RowError. Warnings never count as failures."""

    row: int
    message: str


class RowNote(BaseModel):
    """A row left out on purpose (skipped, or a duplicate): what it was, and
    why, e.g. item "web-01: Nessus 19506 (443/tcp)", message "Same as a
    finding from scan_0915.nessus"."""

    row: int
    item: str
    message: str


class ImportReport(BaseModel):
    """For files that create assets and findings together (profile imports),
    created/updated/skipped/repeated count assets, and
    findings_created/duplicates count findings. Otherwise
    created/updated/skipped count the file's own records.

    Each asset the upload names is counted once, by its first row: created
    (new), updated (already in the inventory) or skipped (already there,
    left unchanged, strategy "skip"); its later rows are `repeated`. So the
    assets an upload names are created + updated + skipped."""

    created: int = 0
    updated: int = 0
    # Assets left untouched (strategy "skip"), and Nessus Info items when
    # Info is set to be skipped.
    skipped: int = 0
    # Rows naming an asset an earlier row of the same file already named:
    # they update it (later rows win), or leave it (strategy "skip").
    # Uploads before this change (2026-10-01) counted these as updated (or skipped).
    repeated: int = 0
    # Findings identical to one already recorded (same asset, source, category).
    duplicates: int = 0
    failed: int = 0
    findings_created: int = 0
    errors: list[RowError] = []
    warnings: list[RowWarning] = []
    # All warnings, when there are more than the report lists.
    warnings_total: int = 0
    # The first of the rows counted in `skipped` and `duplicates`, with why
    # (the counts are the totals). Uploads before 2026-09-30 have none.
    skipped_rows: list[RowNote] = []
    duplicate_rows: list[RowNote] = []


class ImportResponse(BaseModel):
    """Files processed during the request come back completed/failed with the
    report. Larger files come back pending with no report: poll
    GET /orgs/{org_id}/scans/{scan_id} until status is completed or failed;
    the report is then in the scan's summary."""

    scan_id: uuid.UUID
    status: ScanStatus
    report: ImportReport | None = None
