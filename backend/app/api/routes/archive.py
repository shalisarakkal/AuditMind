"""Archive, restore and purge (Phase 2d part 2), the Imports page's list of
uploads, the Archived page and the purge log. The work itself is in
app/services/archive_service.py."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import PageParams, SortOrder, contains, ordered, page_params
from app.core.config import settings
from app.db.session import get_db
from app.models.archive import ArchiveBatch, ArchiveJob, PurgeLogEntry
from app.models.enums import ArchiveAction, ArchiveItemType, ArchiveState, ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.schemas.archive import ArchivedItemRead, ArchiveJobRead, PurgeLogRead, UploadRead
from app.schemas.paging import Page
from app.schemas.scan import brief_scan
from app.services import archive_service, ingestion_background
from app.services.archive_service import ArchiveError

router = APIRouter(prefix="/orgs/{org_id}", tags=["archive"])

_WRITERS = require_org_role(UserRole.admin, UserRole.auditor)
_ADMINS = require_org_role(UserRole.admin)
_ACTIVE = (ScanStatus.pending, ScanStatus.running)

JOB_RESPONSES = {202: {"model": ArchiveJobRead, "description": "Large job accepted; it runs in the background"}}


def _who(user: User | None) -> str | None:
    return (user.name or user.email) if user else None


def _job_read(job: ArchiveJob, batch: ArchiveBatch) -> ArchiveJobRead:
    return ArchiveJobRead(
        id=job.id,
        org_id=job.org_id,
        batch_id=job.batch_id,
        action=job.action,
        status=job.status,
        item_type=batch.item_type,
        item_id=batch.item_id,
        label=batch.label,
        started_by=job.started_by,
        started_at=job.started_at,
        completed_at=job.completed_at,
        dismissed_at=job.dismissed_at,
        progress=job.progress,
        summary=job.summary,
    )


def _start(db: Session, background_tasks: BackgroundTasks, response: Response, start) -> ArchiveJobRead:
    """Start a job (`start` creates it) and run it now (200, finished) or,
    above ARCHIVE_SYNC_MAX_ROWS rows, in the background (202)."""
    try:
        job = start()
    except ArchiveError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    if archive_service.estimated_rows(db, job) <= settings.ARCHIVE_SYNC_MAX_ROWS:
        job = archive_service.run_job(db, job.id)
        response.status_code = status.HTTP_200_OK
    else:
        background_tasks.add_task(ingestion_background.run_archive_job, job.id)
        response.status_code = status.HTTP_202_ACCEPTED
    return _job_read(job, db.get(ArchiveBatch, job.batch_id))


def _archive_route(item_type: ArchiveItemType, path: str, summary: str):
    @router.post(path, response_model=ArchiveJobRead, responses=JOB_RESPONSES, summary=summary)
    def archive_item(
        org_id: uuid.UUID,
        item_id: uuid.UUID,
        background_tasks: BackgroundTasks,
        response: Response,
        db: Session = Depends(get_db),
        membership: OrgMembership = Depends(_WRITERS),
    ) -> ArchiveJobRead:
        return _start(
            db,
            background_tasks,
            response,
            lambda: archive_service.start_archive(db, org_id, item_type, item_id, membership.user_id),
        )

    archive_item.__name__ = f"archive_{item_type.value}"
    return archive_item


_archive_route(
    ArchiveItemType.upload,
    "/scans/{item_id}/archive",
    "Archive an upload: its findings, and the assets it created that no other upload uses",
)
_archive_route(ArchiveItemType.asset, "/assets/{item_id}/archive", "Archive an asset and all its findings")
_archive_route(
    ArchiveItemType.finding, "/findings/{item_id}/archive", "Archive a manually added finding (one with no upload)"
)


@router.post("/archive/{batch_id}/restore", response_model=ArchiveJobRead, responses=JOB_RESPONSES)
def restore(
    org_id: uuid.UUID,
    batch_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(_WRITERS),
) -> ArchiveJobRead:
    """Bring back everything one archive action archived. A finding that now
    duplicates an active one is purged instead (summary.duplicates_purged).
    Also undoes an archive that stopped part-way (what it had archived)."""
    return _start(
        db,
        background_tasks,
        response,
        lambda: archive_service.start_batch_job(db, org_id, batch_id, ArchiveAction.restore, membership.user_id),
    )


@router.post("/archive/{batch_id}/purge", response_model=ArchiveJobRead, responses=JOB_RESPONSES)
def purge(
    org_id: uuid.UUID,
    batch_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(_ADMINS),
) -> ArchiveJobRead:
    """Delete an archived item for good. Admins only; recorded in the purge log."""
    return _start(
        db,
        background_tasks,
        response,
        lambda: archive_service.start_batch_job(db, org_id, batch_id, ArchiveAction.purge, membership.user_id),
    )


@router.get("/archive", response_model=Page[ArchivedItemRead])
def list_archived(
    org_id: uuid.UUID,
    item_type: ArchiveItemType = Query(..., description="Which tab: archived uploads, assets or findings"),
    q: str | None = Query(None, description="Name contains this"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[ArchivedItemRead]:
    """What's archived (not restored or purged), newest first, with when
    each will be purged automatically. An item still being archived is
    listed once its archive has finished."""
    conditions = [
        ArchiveBatch.org_id == org_id,
        ArchiveBatch.item_type == item_type,
        ArchiveBatch.state.not_in((ArchiveState.archiving, ArchiveState.restored, ArchiveState.purged)),
    ]
    if (match := contains(q, ArchiveBatch.label)) is not None:
        conditions.append(match)
    total = db.scalar(select(func.count()).select_from(ArchiveBatch).where(*conditions))
    rows = db.execute(
        select(ArchiveBatch, User)
        .outerjoin(User, User.id == ArchiveBatch.created_by)
        .where(*conditions)
        .order_by(ArchiveBatch.created_at.desc(), ArchiveBatch.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    org = db.get(Organization, org_id)
    running = archive_service.running_actions(db, [batch.id for batch, _ in rows])
    return Page(
        items=[
            ArchivedItemRead(
                id=batch.id,
                item_type=batch.item_type,
                item_id=batch.item_id,
                label=batch.label,
                state=batch.state,
                running=running.get(batch.id),
                archived_at=batch.created_at,
                archived_by=_who(user),
                purge_at=archive_service.purge_at(org, batch.created_at),
                counts=batch.counts,
            )
            for batch, user in rows
        ],
        total=total,
    )


@router.get("/archive-jobs", response_model=list[ArchiveJobRead])
def list_archive_jobs(
    org_id: uuid.UUID,
    tracked: bool = Query(
        False,
        description="Only what the import tracker shows: the org's running jobs (anyone's), and the caller's "
        "finished jobs they haven't dismissed",
    ),
    active: bool = Query(False, description="Only pending and running jobs"),
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_member),
) -> list[ArchiveJobRead]:
    query = select(ArchiveJob, ArchiveBatch).join(ArchiveBatch, ArchiveBatch.id == ArchiveJob.batch_id)
    query = query.where(ArchiveJob.org_id == org_id)
    if active:
        query = query.where(ArchiveJob.status.in_(_ACTIVE))
    if tracked:
        query = query.where(
            or_(
                ArchiveJob.status.in_(_ACTIVE),
                and_(ArchiveJob.started_by == membership.user_id, ArchiveJob.dismissed_at.is_(None)),
            )
        )
    elif not active:
        query = query.limit(100)
    rows = db.execute(query.order_by(ArchiveJob.started_at.desc())).all()
    return [_job_read(job, batch) for job, batch in rows]


@router.post("/archive-jobs/{job_id}/dismiss", response_model=ArchiveJobRead)
def dismiss_archive_job(
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_member),
) -> ArchiveJobRead:
    """Hide a finished job's result from the tracker (whoever started it)."""
    job = db.get(ArchiveJob, job_id)
    if not job or job.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.started_by != membership.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only whoever started it can dismiss this")
    if job.status in _ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The job is still running")
    if job.dismissed_at is None:
        job.dismissed_at = datetime.now(timezone.utc)
        db.commit()
    return _job_read(job, db.get(ArchiveBatch, job.batch_id))


UploadSort = Literal["started", "filename", "type", "status", "uploaded_by"]
_UPLOAD_SORT = {
    "started": Scan.started_at,
    "filename": func.lower(Scan.filename),
    "type": Scan.scan_type,
    "status": Scan.status,
    "uploaded_by": func.lower(func.coalesce(User.name, User.email)),
}


@router.get("/uploads", response_model=Page[UploadRead])
def list_uploads(
    org_id: uuid.UUID,
    q: str | None = Query(None, description="File name, type or uploader contains this"),
    sort: UploadSort = Query("started", description="Column to sort by"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[UploadRead]:
    """Every file uploaded to the org that isn't archived, newest first by
    default, without its report's row lists."""
    conditions = [Scan.org_id == org_id, Scan.source == "upload", Scan.archived_at.is_(None)]
    if (match := contains(q, Scan.filename, Scan.scan_type, User.name, User.email)) is not None:
        conditions.append(match)
    base = select(Scan, User).outerjoin(User, User.id == Scan.started_by).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(
        base.order_by(ordered(_UPLOAD_SORT[sort], order), Scan.started_at.desc(), Scan.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    unfinished = archive_service.unfinished_archives(db, org_id, [scan.id for scan, _ in rows])
    items = [
        UploadRead(
            **brief_scan(scan).model_dump(),
            uploaded_by=_who(user),
            **archive_service.archiving_fields(unfinished, scan.id),
        )
        for scan, user in rows
    ]
    return Page(items=items, total=total)


@router.get("/purge-log", response_model=Page[PurgeLogRead])
def list_purge_log(
    org_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(_ADMINS),
) -> Page[PurgeLogRead]:
    """What was purged, newest first. Admins only."""
    total = db.scalar(select(func.count()).select_from(PurgeLogEntry).where(PurgeLogEntry.org_id == org_id))
    rows = db.execute(
        select(PurgeLogEntry, User)
        .outerjoin(User, User.id == PurgeLogEntry.purged_by)
        .where(PurgeLogEntry.org_id == org_id)
        .order_by(PurgeLogEntry.purged_at.desc(), PurgeLogEntry.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return Page(
        items=[
            PurgeLogRead(
                id=entry.id,
                item_type=entry.item_type,
                label=entry.label,
                archived_at=entry.archived_at,
                purged_at=entry.purged_at,
                purged_by=_who(user),
                reason=entry.reason,
                counts=entry.counts,
            )
            for entry, user in rows
        ],
        total=total,
    )
