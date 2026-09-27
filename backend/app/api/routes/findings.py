import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.uploads import IMPORT_RESPONSES, start_import
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.schemas.finding import FindingCreate, FindingRead
from app.schemas.ingestion import ImportResponse

router = APIRouter(prefix="/orgs/{org_id}", tags=["findings"])


@router.get("/findings", response_model=list[FindingRead])
def list_findings(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[Finding]:
    return db.query(Finding).filter(Finding.org_id == org_id).order_by(Finding.created_at.desc()).all()


@router.post("/findings", response_model=FindingRead, status_code=status.HTTP_201_CREATED)
def create_finding(
    org_id: uuid.UUID,
    payload: FindingCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Finding:
    finding = Finding(org_id=org_id, **payload.model_dump())
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding


@router.post(
    "/findings/import",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses=IMPORT_RESPONSES,
)
async def import_findings(
    org_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="Findings: .csv, .json, or a native .nessus export"),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> ImportResponse:
    """Upload findings. CSV/JSON columns: hostname and/or ip (at least one),
    domain and severity (required), category, description, source (default
    "manual"). Hosts not yet in the inventory are added as assets. A finding
    already recorded for the same asset, source and category is skipped as a
    duplicate."""
    return await start_import(
        db=db, background_tasks=background_tasks, response=response, org_id=org_id, file=file, kind="findings"
    )


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
        .order_by(Finding.created_at.desc())
        .all()
    )
