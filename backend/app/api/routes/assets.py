import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select, union
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import (
    PageParams,
    SortOrder,
    any_of,
    contains,
    contains_pattern,
    distinct_values,
    labelled,
    one_of,
    page_params,
)
from app.api.uploads import IMPORT_RESPONSES, confirm_form, start_import
from app.db.session import get_db
from app.db.asset_search import expression as search_expression, useful_trigrams, selective_candidates
from app.models.asset import Asset
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.schemas.asset import AssetCreate, AssetFacets, AssetListItem, AssetRead
from app.schemas.ingestion import ImportResponse
from app.schemas.paging import SeekPage
from app.services import list_pages, asset_context
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


@router.get("", response_model=SeekPage[AssetListItem])
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
    managed_owner: list[str] | None = Query(None, max_length=100),
    managed_environment: list[str] | None = Query(None, max_length=100),
    business_criticality: list[str] | None = Query(None, max_length=100),
    sort: AssetSort = Query("created", description="Column to sort by"),
    order: SortOrder = Query("asc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> SeekPage[AssetListItem]:
    """The org's assets, a page at a time: by default in the order they were
    added. Filters combine (all must match); text filters match partially."""
    tag_text = func.array_to_string(Asset.tags, " ")
    search = any_of(contains(q, Asset.hostname, Asset.ip, Asset.cloud_id, Asset.subtype,
        Asset.environment, Asset.criticality, tag_text), labelled(q, Asset.type, _TYPE_LABELS))
    ready = asset_context.available(db)
    if not ready and any((managed_owner, managed_environment, business_criticality)):
        asset_context.require_available(db)
    source_search = search
    context_ids = asset_context.search_ids(org_id, q) if ready else None
    context_search = Asset.id.in_(context_ids) if context_ids is not None else None
    if context_search is not None: search = or_(search, context_search)
    tag_filter = contains(tags, tag_text)
    q_index = contains(q, search_expression(Asset)) if useful_trigrams(q) else None
    candidates = [(candidate, original, contains_pattern(value)) for value,candidate,original in (
        (q,q_index,source_search),(tags,contains(tags,search_expression(Asset)),tag_filter))
        if candidate is not None and useful_trigrams(value)]
    selected = selective_candidates(db, Asset, org_id, candidates)
    if context_ids is not None and any(c is q_index for c in selected):
        # An OR with an IN subplan is often estimated at 50% of the entire
        # inventory. Estimate the narrow context query directly instead; keep
        # the existing source accelerator when context candidates are bounded.
        if asset_context.estimated_rows(db,context_ids) <= 5000:
            source_ids = select(Asset.id).where(Asset.org_id==org_id,Asset.archived_at.is_(None),source_search,q_index)
            combined = Asset.id.in_(union(source_ids,context_ids))
            selected = [combined if c is q_index else c for c in selected]
        else:
            selected = [c for c in selected if c is not q_index]
    conditions = [
        # Indexed candidate superset; retain the original per-field predicate
        # below to reject matches spanning field boundaries or type labels.
        *selected,
        search,
        contains(hostname, Asset.hostname),
        contains(ip, Asset.ip),
        contains(cloud_id, Asset.cloud_id),
        tag_filter,
        one_of(Asset.type, type),
        one_of(Asset.subtype, subtype),
        one_of(Asset.environment, environment),
        one_of(Asset.criticality, criticality),
        *([asset_context.filter_condition(org_id, field, values) for field, values in (("owner_id", managed_owner), ("environment", managed_environment), ("business_criticality", business_criticality))] if ready else []),
    ]
    query = db.query(Asset).filter(
        Asset.org_id == org_id, Asset.archived_at.is_(None), *(c for c in conditions if c is not None)
    )
    key = {"q": (q or "").strip(), "hostname": (hostname or "").strip(), "ip": (ip or "").strip(),
        "cloud_id": (cloud_id or "").strip(), "tags": (tags or "").strip(),
        **{name: list_pages.choices(value) for name, value in (
            ("type", type), ("subtype", subtype), ("environment", environment), ("criticality", criticality), ("managed_owner", managed_owner), ("managed_environment", managed_environment), ("business_criticality", business_criticality))}}
    stamp = list_pages.revision_stamp(db, org_id, "assets")
    total = list_pages.exact_counts(db, stamp, "assets", key, query.count).value
    terms = [list_pages.Term(_SORT_COLUMNS[sort], order == "asc")]
    if sort != "created": terms.append(list_pages.Term(Asset.created_at))
    terms.append(list_pages.Term(Asset.id))
    scope = list_pages.fingerprint({"kind": "assets-v2-context", "org": org_id, "filters": key, "sort": sort, "order": order})
    positions = list_pages.page_rows(query.with_entities(Asset.id, *(term.column for term in terms)),
        terms, page, stamp, scope, indexed=sort in {"created", "hostname", "ip"}) if page.offset < total else []
    ids = [row[0] for row in positions]
    # Sorting/offset operates on narrow IDs/keys. Fetch payload only for this page.
    items = db.query(Asset).filter(Asset.org_id == org_id, Asset.archived_at.is_(None), Asset.id.in_(ids)).all() if ids else []
    position = {id_: index for index, id_ in enumerate(ids)}
    items.sort(key=lambda item: position[item.id])
    navigation = list_pages.navigation(positions, stamp, scope, page, total) if list_pages.revision_stamp(db, org_id, "assets") == stamp else {}
    contexts = asset_context.read_many(db, org_id, [a.id for a in items], ready=ready)
    unfinished = unfinished_archives(db, org_id, [a.id for a in items])
    return SeekPage(
        items=[
            AssetListItem(**AssetRead.model_validate(a).model_dump(), context=contexts[a.id], **archiving_fields(unfinished, a.id))
            for a in items
        ],
        total=total,
        **navigation,
    )


@router.get("/facets", response_model=AssetFacets)
def asset_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> AssetFacets:
    """The values each pick-list filter can offer ("" first when some assets
    have none)."""
    assets = db.query(Asset).filter(Asset.org_id == org_id, Asset.archived_at.is_(None))
    return AssetFacets(
        type=distinct_values(assets, Asset.type, indexed=True),
        subtype=distinct_values(assets, Asset.subtype, indexed=True),
        environment=distinct_values(assets, Asset.environment, indexed=True),
        criticality=distinct_values(assets, Asset.criticality, indexed=True),
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
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
