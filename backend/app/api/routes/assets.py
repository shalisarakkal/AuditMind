import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import (
    PageParams,
    SortOrder,
    any_of,
    contains,
    distinct_values,
    labelled,
    one_of,
    ordered,
    page_params,
)
from app.api.uploads import IMPORT_RESPONSES, confirm_form, start_import
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.schemas.asset import AssetCreate, AssetFacets, AssetListItem, AssetRead
from app.schemas.ingestion import ImportResponse
from app.schemas.paging import Page
from app.services.archive_service import archiving_fields, unfinished_archives
from app.services.asset_types import resolve_asset_type
from app.services.events import record_event
from app.services.org_settings import resolve_ingestion_settings

router = APIRouter(prefix="/orgs/{org_id}/assets", tags=["assets"])


# Sortable columns (the default, "created", is the order assets were added).
AssetSort = Literal["hostname", "ip", "cloud_id", "type", "subtype", "environment", "criticality", "created"]
_SORT_COLUMNS = {
    "hostname": func.lower(Asset.hostname),
    "ip": Asset.ip,
    "cloud_id": func.lower(Asset.cloud_id),
    "type": Asset.type,
    "subtype": func.lower(Asset.subtype),
    "environment": func.lower(Asset.environment),
    "criticality": func.lower(Asset.criticality),
    "created": Asset.created_at,
}
_BLANK_HELP = 'Several allowed; "" for no value'
# The types' labels as the app shows them (frontend/src/lib/domain.ts), so the
# search box finds "Network device" by what's on screen.
_TYPE_LABELS = {
    "server": "Server",
    "workstation": "Workstation",
    "network_device": "Network device",
    "database": "Database",
    "cloud_resource": "Cloud resource",
    "application": "Application",
}


@router.get("", response_model=Page[AssetListItem])
def list_assets(
    org_id: uuid.UUID,
    q: str | None = Query(
        None,
        description="Search every shown column: hostname, IP, cloud ID, type, subtype, environment, criticality "
        "or tags contains this",
    ),
    hostname: str | None = Query(None, description="Hostname contains this"),
    ip: str | None = Query(None, description="IP contains this"),
    cloud_id: str | None = Query(None, description="Cloud ID (ARN, resource ID...) contains this"),
    tags: str | None = Query(None, description="A tag contains this"),
    type: list[str] | None = Query(None, description=f"Type is one of these. {_BLANK_HELP}"),
    subtype: list[str] | None = Query(None, description=f"Subtype is one of these. {_BLANK_HELP}"),
    environment: list[str] | None = Query(None, description=f"Environment is one of these. {_BLANK_HELP}"),
    criticality: list[str] | None = Query(None, description=f"Criticality is one of these. {_BLANK_HELP}"),
    sort: AssetSort = Query("created", description="Column to sort by"),
    order: SortOrder = Query("asc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[AssetListItem]:
    """The org's assets, a page at a time: by default in the order they were
    added. Filters combine (all must match); text filters match partially."""
    tag_text = func.array_to_string(Asset.tags, " ")
    conditions = [
        any_of(
            contains(
                q,
                Asset.hostname,
                Asset.ip,
                Asset.cloud_id,
                Asset.subtype,
                Asset.environment,
                Asset.criticality,
                tag_text,
            ),
            labelled(q, Asset.type, _TYPE_LABELS),
        ),
        contains(hostname, Asset.hostname),
        contains(ip, Asset.ip),
        contains(cloud_id, Asset.cloud_id),
        contains(tags, tag_text),
        one_of(Asset.type, type),
        one_of(Asset.subtype, subtype),
        one_of(Asset.environment, environment),
        one_of(Asset.criticality, criticality),
    ]
    query = db.query(Asset).filter(
        Asset.org_id == org_id, Asset.archived_at.is_(None), *(c for c in conditions if c is not None)
    )
    total = query.count()
    items = (
        query.order_by(ordered(_SORT_COLUMNS[sort], order), Asset.created_at, Asset.id)
        .offset(page.offset)
        .limit(page.limit)
        .all()
    )
    unfinished = unfinished_archives(db, org_id, [a.id for a in items])
    return Page(
        items=[
            AssetListItem(**AssetRead.model_validate(a).model_dump(), **archiving_fields(unfinished, a.id))
            for a in items
        ],
        total=total,
    )


@router.get("/facets", response_model=AssetFacets)
def asset_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> AssetFacets:
    """The values each pick-list filter can offer ("" first when some assets
    have none)."""
    assets = db.query(Asset).filter(Asset.org_id == org_id, Asset.archived_at.is_(None))
    return AssetFacets(
        type=distinct_values(assets, Asset.type),
        subtype=distinct_values(assets, Asset.subtype),
        environment=distinct_values(assets, Asset.environment),
        criticality=distinct_values(assets, Asset.criticality),
    )


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    org_id: uuid.UUID,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
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
    record_event(
        db,
        "asset_added",
        org_id=org_id,
        actor=membership.user,
        item=asset.hostname or asset.ip or asset.cloud_id,
        details={"type": asset_type},
    )
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
    response: Response,
    file: UploadFile = File(..., description="Asset inventory: .csv or .json"),
    confirm: bool = confirm_form(),
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> ImportResponse:
    """Import an asset inventory. Columns: type (required; server, workstation,
    network_device, database, cloud_resource, application, or a known name for
    one such as laptop or VM), subtype, hostname and/or ip (at least one),
    cloud_id, environment, criticality, tags (";"-separated in CSV, a list in
    JSON). Existing assets are matched by hostname and category, else IP. For other column
    layouts, use POST /orgs/{org_id}/imports with an import profile."""
    return await start_import(
        db=db,
        response=response,
        org_id=org_id,
        file=file,
        kind="assets",
        started_by=membership.user_id,
        confirm=confirm,
    )


@router.post(
    "/discover",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={501: {"description": "Not available yet: connectors arrive in Phase 5 (CONNECTORS_SPEC.md)"}},
)
def discover_assets(org_id: uuid.UUID, _: OrgMembership = Depends(require_org_role(UserRole.admin))) -> None:
    """Asset discovery through a connector: not available yet (501), so no
    client waits for a scan that would never run."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Asset discovery through connectors isn't available yet"
    )
