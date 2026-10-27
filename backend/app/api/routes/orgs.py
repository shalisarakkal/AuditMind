import uuid
import base64

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_org_member, require_org_role
from app.api.routes.platform import invalid_settings, record_settings_change
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.organization_logo import OrganizationLogo
from app.models.user import User
from app.schemas.org_settings import IngestionSettingsRead, IngestionSettingsUpdate
from app.schemas.organization import MyOrganizationRead, OrganizationRead, OrganizationLogoRead
from app.schemas.organization import OrganizationBrandingRead, OrganizationBrandingUpdate
from app.schemas.security import SecuritySettingsRead, SecuritySettingsUpdate
from app.services.events import record_event
from app.services.org_settings import apply_overrides, resolve_ingestion_settings
from app.services.security_policy import change_layer, resolve_org_security, resolve_platform_security
from app.services.organization_logos import MAX_UPLOAD, normalize_logo

router = APIRouter(prefix="/orgs", tags=["orgs"])


def _branding_response(org: Organization) -> dict:
    return {"show_name_in_header": org.show_name_in_header, "header_logo_size": org.header_logo_size,
            "header_name_size": org.header_name_size}


@router.get("/{org_id}/branding", response_model=OrganizationBrandingRead)
def read_branding(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                  _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    org = db.get(Organization, org_id)
    return _branding_response(org)


@router.patch("/{org_id}/branding", response_model=OrganizationBrandingRead)
def update_branding(org_id: uuid.UUID, payload: OrganizationBrandingUpdate, response: Response,
                    db: Session = Depends(get_db), admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    org = db.get(Organization, org_id, with_for_update=True, populate_existing=True)
    if org.show_name_in_header != payload.expected_show_name_in_header:
        raise HTTPException(409, "Branding changed; reload before retrying")
    for field in ("header_logo_size", "header_name_size"):
        value, expected = getattr(payload, field), getattr(payload, "expected_" + field)
        if (value is None) != (expected is None):
            raise HTTPException(422, "Size and expected size must be supplied together")
        if value is not None and getattr(org, field) != expected:
            raise HTTPException(409, "Branding changed; reload before retrying")
    if org.show_name_in_header != payload.show_name_in_header:
        record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                     item="Organization header name", details={"from": org.show_name_in_header, "to": payload.show_name_in_header})
        org.show_name_in_header = payload.show_name_in_header
    for field, label in (("header_logo_size", "Organization header logo size"), ("header_name_size", "Organization header name size")):
        value = getattr(payload, field)
        if value is not None and getattr(org, field) != value:
            record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                         item=label, details={"from": getattr(org, field), "to": value})
            setattr(org, field, value)
    result = _branding_response(org)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


def _logo_response(logo: OrganizationLogo | None) -> dict:
    return {"version": logo.version if logo else None,
            "image_data_url": "data:image/png;base64," + base64.b64encode(logo.image).decode("ascii") if logo else None}


@router.get("/{org_id}/logo", response_model=OrganizationLogoRead)
def read_logo(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
              _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return _logo_response(db.get(OrganizationLogo, org_id))


@router.post("/{org_id}/logo", response_model=OrganizationLogoRead)
def upload_logo(org_id: uuid.UUID, response: Response, file: UploadFile = File(...),
                expected_version: str = Form(...), db: Session = Depends(get_db),
                admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    current = db.get(OrganizationLogo, org_id, populate_existing=True)
    if expected_version != (current.version if current else "none"):
        raise HTTPException(409, "Logo changed; reload before retrying")
    image = normalize_logo(file.file.read(MAX_UPLOAD + 1), file.content_type or "")
    version = str(uuid.uuid4())
    if current is None:
        current = OrganizationLogo(org_id=org_id, version=version, image=image)
        db.add(current)
    else:
        current.version, current.image = version, image
    record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                 item="Organization logo", details={"action": "logo_saved", "version": version})
    # Snapshot before commit expires ORM state: a later admin may immediately
    # replace/remove the row, but must not turn this committed save into a 500.
    result = _logo_response(current)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.delete("/{org_id}/logo", status_code=204)
def remove_logo(org_id: uuid.UUID, expected_version: str, db: Session = Depends(get_db),
                admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    current = db.get(OrganizationLogo, org_id, populate_existing=True)
    if expected_version != (current.version if current else "none"):
        raise HTTPException(409, "Logo changed; reload before retrying")
    if current is not None:
        db.delete(current)
        record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                     item="Organization logo", details={"action": "logo_removed"})
    db.commit()


def _my_org(org: Organization, role: UserRole, access: str = "member") -> MyOrganizationRead:
    return MyOrganizationRead(
        **OrganizationRead.model_validate(org).model_dump(), role=role, access=access, archived=org.archived_at is not None
    )


def _ingestion_settings(org: Organization) -> IngestionSettingsRead:
    effective = resolve_ingestion_settings(org)
    return IngestionSettingsRead(
        import_partial_success=effective.import_partial_success,
        asset_existing_strategy=effective.asset_existing_strategy,
        exact_duplicate_file_policy=effective.exact_duplicate_file_policy,
        nessus_info_severity=effective.nessus_info_severity,
        nessus_domain_map=effective.nessus_domain_map,
        nessus_default_domain=effective.nessus_default_domain,
        overridden=sorted(effective.overridden),
        nessus_domain_map_override=org.ingestion_overrides.get("nessus_domain_map", {}),
        asset_type_aliases=effective.asset_type_aliases,
        asset_type_aliases_override=org.ingestion_overrides.get("asset_type_aliases", {}),
        archive_retention_days=effective.archive_retention_days,
        event_retention_days=effective.event_retention_days,
    )


@router.get("", response_model=list[MyOrganizationRead])
def list_my_orgs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[MyOrganizationRead]:
    """Orgs the caller belongs to, for the org picker, oldest membership
    first; for the Sysadmin, every org (read-only), by name. Orgs being
    purged are gone."""
    if user.is_sysadmin:
        orgs = db.scalars(
            select(Organization).where(Organization.purge_requested_at.is_(None)).order_by(func.lower(Organization.name))
        ).all()
        return [_my_org(org, UserRole.viewer, "sysadmin") for org in orgs]
    memberships = db.scalars(
        select(OrgMembership)
        .join(Organization)
        .where(OrgMembership.user_id == user.id, Organization.purge_requested_at.is_(None))
        .order_by(OrgMembership.created_at)
    ).all()
    return [_my_org(m.organization, m.role) for m in memberships]


@router.get("/{org_id}", response_model=OrganizationRead)
def get_org(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> Organization:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("/{org_id}/settings", response_model=IngestionSettingsRead)
def get_ingestion_settings(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> IngestionSettingsRead:
    """Ingestion settings in effect for this org: its overrides, else the
    global .env defaults. `overridden` lists the keys the org overrides."""
    return _ingestion_settings(db.get(Organization, org_id))


@router.patch("/{org_id}/settings", response_model=IngestionSettingsRead)
def update_ingestion_settings(
    org_id: uuid.UUID,
    payload: IngestionSettingsUpdate,
    db: Session = Depends(get_db),
    admin: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> IngestionSettingsRead:
    """Admins only. Send a value to override a setting, null to clear the
    override; omitted fields are unchanged. Recorded in Activity (the old
    and new values; null = back to the default)."""
    # Dependencies may already have cached this row. Lock AND refresh before
    # merging JSON overrides, otherwise concurrent edits lose omitted fields.
    org = db.get(Organization, org_id, with_for_update=True, populate_existing=True)
    changes = payload.model_dump(mode="json", exclude_unset=True)
    before = dict(org.ingestion_overrides or {})
    apply_overrides(org, changes)
    changed = {key: {"from": before.get(key), "to": value} for key, value in changes.items() if before.get(key) != value}
    if changed:
        record_event(db, "settings_changed", org_id=org_id, actor=admin.user, item=", ".join(changed), details=changed)
    db.commit()
    db.refresh(org)
    return _ingestion_settings(org)


@router.get("/{org_id}/security", response_model=SecuritySettingsRead)
def get_security_settings(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> SecuritySettingsRead:
    """The org's security settings: the platform defaults with the org's
    changes. Every member can read them."""
    org = db.get(Organization, org_id)
    platform = resolve_platform_security(db)
    return SecuritySettingsRead(
        values=resolve_org_security(db, org, platform), changed=sorted(org.security_settings or {}), below=platform
    )


@router.patch("/{org_id}/security", response_model=SecuritySettingsRead)
def update_security_settings(
    org_id: uuid.UUID,
    changes: SecuritySettingsUpdate = Body(...),
    db: Session = Depends(get_db),
    admin: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> SecuritySettingsRead:
    """Admins only. Send a value to change a setting (within its range),
    null to follow the platform default again; settings left out are
    unchanged. For someone in several orgs the strictest applies. Recorded
    in Activity."""
    org = db.get(Organization, org_id, with_for_update=True, populate_existing=True)
    platform = resolve_platform_security(db)
    before = resolve_org_security(db, org, platform)
    try:
        stored, after = change_layer(platform, org.security_settings, changes)
    except (ValueError, ValidationError) as invalid:
        raise invalid_settings(invalid)
    org.security_settings = stored
    record_settings_change(db, org_id, admin.user, before, after)
    db.commit()
    return SecuritySettingsRead(values=after, changed=sorted(stored), below=platform)
