"""Archive, restore and purge (Phase 2d part 2), the Imports page's list of
uploads and the Archived page. The work itself is in
app/services/archive_service.py; what was purged is in Activity."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import refuse_if_archived, require_org_member, require_org_role
from app.api.paging import (
    DateRange,
    PageParams,
    SortOrder,
    contains,
    date_range,
    distinct_values,
    one_of,
    ordered,
    page_params,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.archive import ArchiveBatch, ArchiveJob
from app.models.enums import ArchiveAction, ArchiveItemType, ArchiveState, ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.schemas.archive import ArchivedItemRead, ArchivedPage, ArchiveJobRead, UploadRead
from app.schemas.paging import Page
from app.schemas.scan import ScanRead, brief_scan
from app.services import archive_service
from app.services.archive_service import ArchiveError
from app.services.org_lock import org_is_busy

router = APIRouter(prefix="/orgs/{org_id}", tags=["archive"])

_WRITERS = require_org_role(UserRole.admin, UserRole.auditor)
_ADMINS = require_org_role(UserRole.admin)
_ACTIVE = (ScanStatus.pending, ScanStatus.running)

JOB_RESPONSES = {202: {"model": ArchiveJobRead, "description": "Large job accepted; the background worker runs it"}}


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
        heartbeat_at=job.heartbeat_at,
    )


def _start(db: Session, response: Response, start) -> ArchiveJobRead:
    """Start a job (`start` creates it, pending) and run it now (200,
    finished) or leave it for the background worker (202): above
    ARCHIVE_SYNC_MAX_ROWS rows, or when the org is busy (an upload writing
    its rows holds the org's lock for minutes; the request would wait for
    it, so the job queues behind it instead)."""
    try:
        job = start()
    except ArchiveError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    small = archive_service.estimated_rows(db, job) <= settings.ARCHIVE_SYNC_MAX_ROWS and not org_is_busy(db, job.org_id)
    # Claimed first: the worker may be looking at it too.
    if small and archive_service.claim_job(db, job.id):
        job = archive_service.run_job(db, job.id)
        response.status_code = status.HTTP_200_OK
    else:
        db.refresh(job)
        response.status_code = status.HTTP_202_ACCEPTED
    return _job_read(job, db.get(ArchiveBatch, job.batch_id))


def _archive_route(item_type: ArchiveItemType, path: str, summary: str):
    @router.post(path, response_model=ArchiveJobRead, responses=JOB_RESPONSES, summary=summary)
    def archive_item(
        org_id: uuid.UUID,
        item_id: uuid.UUID,
        response: Response,
        db: Session = Depends(get_db),
        membership: OrgMembership = Depends(_WRITERS),
    ) -> ArchiveJobRead:
        return _start(
            db,
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


@router.get(
    "/archive/{batch_id}/report",
    response_model=ScanRead,
    responses={404: {"description": "No such archived upload in this org (not an upload, restored, or purged)"}},
)
def archived_upload_report(
    org_id: uuid.UUID,
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Scan:
    """An archived upload's full report, read-only, from the Archived page
    (to decide whether to restore or purge it). The normal route,
    GET /scans/{id}, doesn't serve archived uploads; once restored it does
    again, and once purged the report is gone."""
    batch = db.get(ArchiveBatch, batch_id)
    scan = db.get(Scan, batch.item_id) if batch and batch.item_type == ArchiveItemType.upload else None
    if not batch or batch.org_id != org_id or scan is None or scan.archived_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archived upload not found")
    return scan


@router.post("/archive/{batch_id}/restore", response_model=ArchiveJobRead, responses=JOB_RESPONSES)
def restore(
    org_id: uuid.UUID,
    batch_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(_WRITERS),
) -> ArchiveJobRead:
    """Bring back everything one archive action archived. A finding that now
    duplicates an active one is purged instead (summary.duplicates_purged).
    Also undoes an archive that stopped part-way (what it had archived)."""
    return _start(
        db,
        response,
        lambda: archive_service.start_batch_job(db, org_id, batch_id, ArchiveAction.restore, membership.user_id),
    )


@router.post("/archive/{batch_id}/purge", response_model=ArchiveJobRead, responses=JOB_RESPONSES)
def purge(
    org_id: uuid.UUID,
    batch_id: uuid.UUID,
    response: Response,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(_ADMINS),
) -> ArchiveJobRead:
    """Delete an archived item for good. Admins only; a Critical event in Activity."""
    return _start(
        db,
        response,
        lambda: archive_service.start_batch_job(db, org_id, batch_id, ArchiveAction.purge, membership.user_id),
    )


BULK_MAX = 500


class BulkRequest(BaseModel):
    """Several items at once: archive uploads, assets or (manually added)
    findings by their ids, or restore or purge archived items by theirs (the
    Archived list's ids)."""

    action: ArchiveAction
    item_type: ArchiveItemType | None = Field(None, description="What `ids` are, for archive")
    ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX)


class BulkRefused(BaseModel):
    id: uuid.UUID
    detail: str


class BulkResult(BaseModel):
    """A job per item, queued for the background worker in the order given;
    items that couldn't start (already archived, a job running on them...)
    are listed with why."""

    jobs: list[ArchiveJobRead]
    refused: list[BulkRefused]


@router.post("/archive-jobs/bulk", response_model=BulkResult, status_code=status.HTTP_202_ACCEPTED)
def start_bulk(
    org_id: uuid.UUID,
    body: BulkRequest,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_member),
) -> BulkResult:
    """Archive, restore or purge the selected items: one job, one archived
    entry and one Activity event per item, as if each were done by hand.
    Archive and restore: admins and auditors; purge: admins only."""
    allowed = (UserRole.admin,) if body.action == ArchiveAction.purge else (UserRole.admin, UserRole.auditor)
    if membership.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    refuse_if_archived(membership)
    if body.action == ArchiveAction.archive and body.item_type is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Say which item_type the ids are")
    jobs, refused = [], []
    for item_id in dict.fromkeys(body.ids):  # each once, in order
        try:
            if body.action == ArchiveAction.archive:
                job = archive_service.start_archive(db, org_id, body.item_type, item_id, membership.user_id)
            else:
                job = archive_service.start_batch_job(db, org_id, item_id, body.action, membership.user_id)
        except ArchiveError as exc:
            db.rollback()
            refused.append(BulkRefused(id=item_id, detail=str(exc)))
            continue
        jobs.append(_job_read(job, db.get(ArchiveBatch, job.batch_id)))
    return BulkResult(jobs=jobs, refused=refused)


ArchivedSort = Literal["name", "type", "archived", "archived_by", "purge"]
# Uploads, then assets, then findings, as the page's chips.
_TYPE_ORDER = case({t: i for i, t in enumerate(ArchiveItemType)}, value=ArchiveBatch.item_type)


@router.get("/archive", response_model=ArchivedPage)
def list_archived(
    org_id: uuid.UUID,
    type: list[ArchiveItemType] | None = Query(None, description="Uploads, assets or findings: one of these (all if left out)"),
    q: str | None = Query(None, description="Search the shown columns: name or who archived it contains this"),
    name: str | None = Query(None, description="Name contains this"),
    archived_by: str | None = Query(None, description="Who archived it contains this"),
    dates: DateRange = Depends(date_range),
    sort: ArchivedSort = Query("archived", description="Column to sort by (purge follows archived)"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> ArchivedPage:
    """What's archived (not restored or purged), newest first, with when
    each will be purged automatically. An item still being archived is
    listed once its archive has finished. type_counts counts each type
    under every filter but the type one (the page's chips)."""
    conditions = [
        ArchiveBatch.org_id == org_id,
        ArchiveBatch.state.not_in((ArchiveState.archiving, ArchiveState.restored, ArchiveState.purged)),
    ]
    who = func.coalesce(User.name, User.email)
    for match in (contains(q, ArchiveBatch.label, who), contains(name, ArchiveBatch.label), contains(archived_by, who)):
        if match is not None:
            conditions.append(match)
    conditions += dates.conditions(ArchiveBatch.created_at)
    with_user = select(ArchiveBatch.item_type, func.count()).outerjoin(User, User.id == ArchiveBatch.created_by)
    type_counts = dict(db.execute(with_user.where(*conditions).group_by(ArchiveBatch.item_type)).all())
    if type:
        conditions.append(ArchiveBatch.item_type.in_(type))
    base = select(ArchiveBatch, User).outerjoin(User, User.id == ArchiveBatch.created_by).where(*conditions)
    total = sum(n for t, n in type_counts.items() if not type or t in type)
    sort_column = {
        "name": func.lower(ArchiveBatch.label),
        "type": _TYPE_ORDER,
        "archived": ArchiveBatch.created_at,
        "archived_by": func.lower(who),
    }["archived" if sort == "purge" else sort]
    rows = db.execute(
        base.order_by(ordered(sort_column, order), ArchiveBatch.created_at.desc(), ArchiveBatch.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    org = db.get(Organization, org_id)
    running = archive_service.running_actions(db, [batch.id for batch, _ in rows])
    return ArchivedPage(
        type_counts=type_counts,
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


def _upload_conditions(org_id: uuid.UUID) -> list:
    return [Scan.org_id == org_id, Scan.source == "upload", Scan.archived_at.is_(None)]


class UploadFacets(BaseModel):
    """The values the Imports pick-lists can offer."""

    type: list[str]
    status: list[str]


@router.get("/uploads/facets", response_model=UploadFacets)
def upload_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> UploadFacets:
    uploads = db.query(Scan).filter(*_upload_conditions(org_id))
    return UploadFacets(type=distinct_values(uploads, Scan.scan_type), status=distinct_values(uploads, Scan.status))


@router.get("/uploads", response_model=Page[UploadRead])
def list_uploads(
    org_id: uuid.UUID,
    q: str | None = Query(None, description="Search the shown columns: file name, type or uploader contains this"),
    filename: str | None = Query(None, description="File name contains this"),
    type: list[str] | None = Query(None, description="Type (scan_type) is one of these"),
    uploaded_by: str | None = Query(None, description="Uploader contains this"),
    status: list[ScanStatus] | None = Query(None, description="Status is one of these"),
    dates: DateRange = Depends(date_range),
    sort: UploadSort = Query("started", description="Column to sort by"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[UploadRead]:
    """Every file uploaded to the org that isn't archived, newest first by
    default, without its report's row lists."""
    conditions = _upload_conditions(org_id)
    for match in (
        contains(q, Scan.filename, Scan.scan_type, User.name, User.email),
        contains(filename, Scan.filename),
        contains(uploaded_by, User.name, User.email),
        one_of(Scan.scan_type, type),
        one_of(Scan.status, [s.value for s in status] if status else None),
    ):
        if match is not None:
            conditions.append(match)
    conditions += dates.conditions(Scan.started_at)
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
