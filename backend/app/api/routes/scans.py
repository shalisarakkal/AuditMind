import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.enums import ScanStatus, UserRole
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.scan import ScanCreate, ScanRead

router = APIRouter(prefix="/orgs/{org_id}/scans", tags=["scans"])


@router.get("", response_model=list[ScanRead])
def list_scans(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[Scan]:
    return (
        db.query(Scan)
        .filter(Scan.org_id == org_id)
        .order_by(Scan.started_at.desc().nulls_last())
        .all()
    )


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
