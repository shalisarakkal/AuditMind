import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.schemas.finding import FindingCreate, FindingRead

router = APIRouter(prefix="/orgs/{org_id}", tags=["findings"])


@router.get("/findings", response_model=list[FindingRead])
def list_findings(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[Finding]:
    return db.query(Finding).filter(Finding.org_id == org_id).all()


@router.post("/findings", response_model=FindingRead, status_code=status.HTTP_201_CREATED)
def create_finding(
    org_id: uuid.UUID,
    payload: FindingCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Finding:
    finding = Finding(org_id=org_id, **payload.model_dump())
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@router.get("/assets/{asset_id}/findings", response_model=list[FindingRead])
def list_asset_findings(
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> list[Finding]:
    return (
        db.query(Finding)
        .filter(Finding.org_id == org_id, Finding.asset_id == asset_id)
        .all()
    )
