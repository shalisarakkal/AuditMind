import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.uploads import IMPORT_RESPONSES, start_import
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.schemas.asset import AssetCreate, AssetRead
from app.schemas.ingestion import ImportResponse
from app.services.asset_types import resolve_asset_type
from app.services.org_settings import resolve_ingestion_settings

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
    aliases = resolve_ingestion_settings(db.get(Organization, org_id)).asset_type_aliases
    try:
        asset_type, alias_subtype = resolve_asset_type(payload.type, aliases)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    asset = Asset(
        org_id=org_id,
        **payload.model_dump(exclude={"type", "subtype"}),
        type=asset_type,
        subtype=payload.subtype or alias_subtype,
    )
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
    network_device, database, cloud_resource, application, or a known name for
    one such as laptop or VM), subtype, hostname and/or ip (at least one),
    cloud_id, environment, criticality, tags (";"-separated in CSV, a list in
    JSON). Existing assets are matched by hostname and category, else IP. For other column
    layouts, use POST /orgs/{org_id}/imports with an import profile."""
    return await start_import(
        db=db, background_tasks=background_tasks, response=response, org_id=org_id, file=file, kind="assets"
    )


@router.post("/discover", status_code=status.HTTP_202_ACCEPTED)
def discover_assets(
    org_id: uuid.UUID, _: OrgMembership = Depends(require_org_role(UserRole.admin))
) -> dict[str, str]:
    # Placeholder: wire up to a connector (CONNECTORS_SPEC.md) in a later milestone.
    return {"status": "not_implemented", "message": "Connector-based discovery is not wired up yet."}
