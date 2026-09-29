import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.uploads import IMPORT_RESPONSES, start_import
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.import_profile import ImportProfile
from app.models.membership import OrgMembership
from app.schemas.import_profile import ImportProfileCreate, ImportProfileRead, ImportProfileUpdate
from app.schemas.ingestion import ImportResponse
from app.services.import_profiles import (
    FAMILIES,
    Family,
    builtin_profile,
    custom_profile,
    find_custom_profile,
    params_json,
    resolve_profile,
    validate_profile_parts,
)
from app.services.ingestion_service import IngestionError

router = APIRouter(prefix="/orgs/{org_id}", tags=["imports"])


def _read(
    *, key: str, name: str, family: Family, column_map: dict, params: dict, row: ImportProfile | None = None
) -> ImportProfileRead:
    return ImportProfileRead(
        key=key,
        name=name,
        family=family.key,
        family_label=family.label,
        builtin=row is None,
        creates_assets=family.creates_assets,
        creates_findings=family.creates_findings,
        fields=list(family.fields),
        column_map=column_map,
        params=params,
        created_at=row.created_at if row else None,
        updated_at=row.updated_at if row else None,
    )


def _read_builtin(family: Family) -> ImportProfileRead:
    config = builtin_profile(family)
    return _read(
        key=config.key, name=config.name, family=family, column_map=config.column_map, params=params_json(config.params)
    )


def _read_row(row: ImportProfile) -> ImportProfileRead:
    try:
        config = custom_profile(row)
        column_map, params = config.column_map, params_json(config.params)
    except ValueError:
        # Stored settings that no longer validate: show them as stored, so an
        # admin can see and fix them.
        column_map, params = row.column_map, row.params
    return _read(
        key=str(row.id), name=row.name, family=FAMILIES[row.family], column_map=column_map, params=params, row=row
    )


def _own_profile(db: Session, org_id: uuid.UUID, key: str) -> ImportProfile:
    if key in FAMILIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in profiles can't be changed; make a copy and change that instead",
        )
    profile = find_custom_profile(db, org_id, key)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import profile not found")
    return profile


def _check_name_free(db: Session, org_id: uuid.UUID, name: str, except_id: uuid.UUID | None = None) -> None:
    query = db.query(ImportProfile.id).filter(
        ImportProfile.org_id == org_id, func.lower(ImportProfile.name) == name.lower()
    )
    if except_id:
        query = query.filter(ImportProfile.id != except_id)
    if db.query(query.exists()).scalar() or name.lower() in {f.label.lower() for f in FAMILIES.values()}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A profile named {name!r} already exists")


def _validated(family, column_map: dict, params: dict) -> tuple[dict, dict]:
    try:
        cleaned, parsed = validate_profile_parts(family, column_map, params)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return cleaned, params_json(parsed)


@router.get("/import-profiles", response_model=list[ImportProfileRead])
def list_import_profiles(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[ImportProfileRead]:
    """The built-in profiles, then the org's own copies by name."""
    own = db.query(ImportProfile).filter(ImportProfile.org_id == org_id).order_by(func.lower(ImportProfile.name))
    return [_read_builtin(family) for family in FAMILIES.values()] + [_read_row(row) for row in own]


@router.get("/import-profiles/{key}", response_model=ImportProfileRead)
def get_import_profile(
    org_id: uuid.UUID, key: str, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> ImportProfileRead:
    if key in FAMILIES:
        return _read_builtin(FAMILIES[key])
    profile = find_custom_profile(db, org_id, key)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import profile not found")
    return _read_row(profile)


@router.post("/import-profiles", response_model=ImportProfileRead, status_code=status.HTTP_201_CREATED)
def create_import_profile(
    org_id: uuid.UUID,
    payload: ImportProfileCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> ImportProfileRead:
    """Admins only. Copies `copy_from` (a built-in key or one of the org's
    profile ids) under a new name; column_map/params, when given, replace the
    copied ones."""
    try:
        source = resolve_profile(db, org_id, payload.copy_from)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    _check_name_free(db, org_id, payload.name)
    column_map, params = _validated(
        source.family,
        payload.column_map if payload.column_map is not None else source.column_map,
        payload.params if payload.params is not None else params_json(source.params),
    )
    profile = ImportProfile(
        org_id=org_id, name=payload.name, family=source.family.key, column_map=column_map, params=params
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _read_row(profile)


@router.patch("/import-profiles/{key}", response_model=ImportProfileRead)
def update_import_profile(
    org_id: uuid.UUID,
    key: str,
    payload: ImportProfileUpdate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> ImportProfileRead:
    """Admins only. Omitted parts are unchanged; column_map and params are
    replaced wholesale."""
    profile = _own_profile(db, org_id, key)
    if payload.name is not None:
        _check_name_free(db, org_id, payload.name, except_id=profile.id)
        profile.name = payload.name
    if payload.column_map is not None or payload.params is not None:
        column_map, params = _validated(
            FAMILIES[profile.family],
            payload.column_map if payload.column_map is not None else profile.column_map,
            payload.params if payload.params is not None else profile.params,
        )
        profile.column_map = column_map
        profile.params = params
    db.commit()
    db.refresh(profile)
    return _read_row(profile)


@router.delete("/import-profiles/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_import_profile(
    org_id: uuid.UUID,
    key: str,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> Response:
    """Admins only. Past imports keep their reports."""
    db.delete(_own_profile(db, org_id, key))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/imports",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**IMPORT_RESPONSES, 400: {"description": "Unsupported file type or unknown profile"}},
)
async def import_with_profile(
    org_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="A .csv or .json export"),
    profile: str = Form(..., description="Profile key: a built-in (e.g. endpoint_agent) or one of the org's profile ids"),
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> ImportResponse:
    """Import a file with an import profile (GET /import-profiles lists them).
    Each row becomes an asset plus any findings the profile's rules raise, in
    one scan. The report counts assets in created/updated/skipped and findings
    in findings_created/duplicates."""
    try:
        config = resolve_profile(db, org_id, profile)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return await start_import(
        db=db,
        background_tasks=background_tasks,
        response=response,
        org_id=org_id,
        file=file,
        kind="profile",
        started_by=membership.user_id,
        profile=config,
    )
