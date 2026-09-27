import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.asset import Asset
from app.models.membership import OrgMembership
from app.schemas.asset import AssetCreate, AssetRead

router = APIRouter(prefix="/orgs/{org_id}/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
def list_assets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[Asset]:
    return db.query(Asset).filter(Asset.org_id == org_id).all()


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    org_id: uuid.UUID,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Asset:
    asset = Asset(org_id=org_id, **payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/discover", status_code=status.HTTP_202_ACCEPTED)
def discover_assets(
    org_id: uuid.UUID, _: OrgMembership = Depends(require_org_member)
) -> dict[str, str]:
    # Placeholder: wire up to a connector (CONNECTORS_SPEC.md) in a later milestone.
    return {"status": "not_implemented", "message": "Connector-based discovery is not wired up yet."}
