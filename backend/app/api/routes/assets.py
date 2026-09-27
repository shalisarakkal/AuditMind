import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.uploads import IMPORT_RESPONSES, start_import
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.schemas.asset import AssetCreate, AssetRead
from app.schemas.ingestion import ImportResponse

router = APIRouter(prefix="/orgs/{org_id}/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
def list_assets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[Asset]:
    return db.query(Asset).filter(Asset.org_id == org_id).order_by(Asset.created_at).all()


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    org_id: uuid.UUID,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Asset:
    asset = Asset(org_id=org_id, **payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses=IMPORT_RESPONSES,
)
async def import_assets(
    org_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="Asset inventory: .csv or .json"),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> ImportResponse:
    """Import an asset inventory. Columns: type (required; server, workstation,
    network_device, database, cloud_resource, application), hostname and/or ip
    (at least one), cloud_id, environment, criticality, tags (";"-separated in
    CSV, a list in JSON). Existing assets are matched by hostname, else IP."""
    return await start_import(
        db=db, background_tasks=background_tasks, response=response, org_id=org_id, file=file, kind="assets"
    )


@router.post("/discover", status_code=status.HTTP_202_ACCEPTED)
def discover_assets(
    org_id: uuid.UUID, _: OrgMembership = Depends(require_org_role(UserRole.admin))
) -> dict[str, str]:
    # Placeholder: wire up to a connector (CONNECTORS_SPEC.md) in a later milestone.
    return {"status": "not_implemented", "message": "Connector-based discovery is not wired up yet."}
