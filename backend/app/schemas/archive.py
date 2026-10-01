import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ArchiveAction, ArchiveItemType, ArchiveProgress, ArchiveState, ScanStatus
from app.schemas.paging import Page
from app.schemas.scan import ScanRead


class ArchiveJobRead(BaseModel):
    """Archiving, restoring or purging one item. Poll it like an import
    (GET /orgs/{org_id}/archive-jobs?tracked=true) while it runs; its
    summary then holds the rows done per table ("uploads", "assets",
    "findings"; on restore also "duplicates_purged"), or "error"."""

    id: uuid.UUID
    org_id: uuid.UUID
    batch_id: uuid.UUID
    action: ArchiveAction
    status: ScanStatus
    item_type: ArchiveItemType
    item_id: uuid.UUID
    label: str
    started_by: uuid.UUID | None
    started_at: datetime
    completed_at: datetime | None
    dismissed_at: datetime | None
    progress: dict | None
    summary: dict | None
    # Set only while the background worker runs the job (it checks in every
    # ~15 s); None for one run during its request.
    heartbeat_at: datetime | None = None


class ArchivedItemRead(BaseModel):
    """One archive action (a batch): the upload, asset or finding archived,
    how many rows went with it, and when it'll be purged automatically."""

    id: uuid.UUID
    item_type: ArchiveItemType
    item_id: uuid.UUID
    label: str
    # archived; restoring or purging while a job runs, or if one stopped
    # part-way (restore or purge it again to finish). Items still being
    # archived aren't listed.
    state: ArchiveState
    # What a job is doing to it right now, if anything.
    running: ArchiveAction | None
    archived_at: datetime
    archived_by: str | None
    purge_at: datetime
    counts: dict[str, int]


class ArchivedPage(Page[ArchivedItemRead]):
    """The Archived list, plus how many of each type match the other filters."""

    type_counts: dict[ArchiveItemType, int]


class UploadRead(ScanRead):
    """An upload on the Imports page: the scan, without its report's row
    lists, and who uploaded it."""

    uploaded_by: str | None
    # Its archive hasn't finished: running now, or stopped part-way; and that
    # archive (restore it to undo what it archived).
    archiving: ArchiveProgress | None = None
    archiving_batch_id: uuid.UUID | None = None
