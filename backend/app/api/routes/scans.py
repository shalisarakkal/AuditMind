import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.enums import ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.scan import ScanCreate, ScanRead

router = APIRouter(prefix="/orgs/{org_id}/scans", tags=["scans"])


_ACTIVE = (ScanStatus.pending, ScanStatus.running)


@router.get("", response_model=list[ScanRead])
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
    query = db.query(Scan).filter(Scan.org_id == org_id)
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
    completed/failed, and summary then holds the import report."""
    scan = db.get(Scan, scan_id)
    if not scan or scan.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    return scan


@router.post("/{scan_id}/dismiss", response_model=ScanRead)
def dismiss_scan(
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_member),
) -> Scan:
    """Hide a finished import's report for good (its uploader only)."""
    scan = db.get(Scan, scan_id)
    if not scan or scan.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    if scan.started_by != membership.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader can dismiss this report")
    if scan.status in _ACTIVE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The import is still running")
    if scan.dismissed_at is None:
        scan.dismissed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(scan)
    return scan
