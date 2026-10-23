import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.uploads import upload_path
from app.db.session import get_db
from app.models.enums import ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.ingestion import ImportResponse
from app.schemas.scan import ScanCreate, ScanRead

router = APIRouter(prefix="/orgs/{org_id}/scans", tags=["scans"])


_ACTIVE = (ScanStatus.pending, ScanStatus.running)


def _admit_scan(db: Session, org_id: uuid.UUID) -> None:
    from app.services.knowledge_service import KnowledgeError, require_active_org
    try:
        require_active_org(db, org_id, lock=True)
    except KnowledgeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get(
    "",
    response_model=list[ScanRead],
    responses={400: {"description": "Neither tracked nor active: GET /orgs/{org_id}/uploads lists all uploads"}},
)
def list_scans(
    org_id: uuid.UUID,
    tracked: bool = Query(
        False,
        description="Only what the app's import tracker shows: the org's running imports (anyone's), "
        "and the caller's finished imports whose report they haven't dismissed",
    ),
    active: bool = Query(
        False, description="Only pending and running scans (small: no reports), for polling while imports run"
    ),
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_member),
) -> list[Scan]:
    """The import tracker's scans (tracked) or the running ones (active).
    Every upload, a page at a time: GET /orgs/{org_id}/uploads."""
    if not (tracked or active):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass tracked=true or active=true; GET /orgs/{org_id}/uploads lists all uploads, a page at a time",
        )
    query = db.query(Scan).filter(Scan.org_id == org_id, Scan.archived_at.is_(None))
    if active:
        query = query.filter(Scan.status.in_(_ACTIVE))
    if tracked:
        query = query.filter(
            or_(
                Scan.status.in_(_ACTIVE),
                and_(Scan.started_by == membership.user_id, Scan.dismissed_at.is_(None)),
            )
        )
    return query.order_by(Scan.started_at.desc().nulls_last()).all()


@router.post("", response_model=ScanRead, status_code=status.HTTP_201_CREATED)
def create_scan(
    org_id: uuid.UUID,
    payload: ScanCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Scan:
    _admit_scan(db, org_id)
    scan = Scan(
        org_id=org_id,
        status=ScanStatus.pending,
        started_at=datetime.now(timezone.utc),
        **payload.model_dump(),
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


@router.get("/{scan_id}", response_model=ScanRead)
def get_scan(
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Scan:
    """Poll this for a background import: status goes pending -> running ->
    completed/failed, and summary then holds the import report. An archived
    upload isn't found here (the Archived page lists it)."""
    return _active_scan(db, org_id, scan_id)


@router.post("/{scan_id}/dismiss", response_model=ScanRead)
def dismiss_scan(
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_member),
) -> Scan:
    """Hide a finished import's report for good (its uploader only)."""
    scan = _active_scan(db, org_id, scan_id)
    if scan.started_by != membership.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader can dismiss this report")
    if scan.status in _ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The import is still running")
    if scan.dismissed_at is None:
        scan.dismissed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(scan)
    return scan


@router.post(
    "/{scan_id}/retry",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "It can't be retried: not failed, failed for its content, or its file is gone"}},
)
def retry_scan(
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> ImportResponse:
    """Run a failed large upload again from its kept file (see
    ScanRead.retryable), without uploading it again: a new upload, queued
    for the background worker; the failed one's report is dismissed for
    the caller. The uploader or an admin."""
    _admit_scan(db, org_id)
    old = _active_scan(db, org_id, scan_id)
    if old.started_by != membership.user_id and membership.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader or an admin can retry this")
    if not old.retryable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This upload can't be retried (it didn't fail, its content was rejected, or its file is gone): "
            "upload the file again",
        )
    now = datetime.now(timezone.utc)
    new = Scan(
        org_id=org_id,
        scan_type=old.scan_type,
        profile=old.profile,
        source="upload",
        filename=old.filename,
        status=ScanStatus.pending,
        started_at=now,
        started_by=membership.user_id,
        content_hash=old.content_hash,
    )
    db.add(new)
    db.flush()
    os.replace(upload_path(old.id), upload_path(new.id))  # the old one isn't retryable any more
    if old.started_by == membership.user_id and old.dismissed_at is None:
        old.dismissed_at = now
    try:
        db.commit()
    except Exception:
        os.replace(upload_path(new.id), upload_path(old.id))
        raise
    return ImportResponse(scan_id=new.id, status=new.status)


def _active_scan(db: Session, org_id: uuid.UUID, scan_id: uuid.UUID) -> Scan:
    """The org's scan, unless it's archived (then it's left alone until
    restored, like everything archived)."""
    scan = db.get(Scan, scan_id)
    if not scan or scan.org_id != org_id or scan.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan
