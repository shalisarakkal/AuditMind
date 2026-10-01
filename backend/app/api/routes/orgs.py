import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_org_member, require_org_role
from app.api.routes.platform import invalid_settings, record_settings_change
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.org_settings import IngestionSettingsRead, IngestionSettingsUpdate
from app.schemas.organization import MyOrganizationRead, OrganizationRead
from app.schemas.security import SecuritySettingsRead, SecuritySettingsUpdate
from app.services.events import record_event
from app.services.org_settings import apply_overrides, resolve_ingestion_settings
from app.services.security_policy import change_layer, resolve_org_security, resolve_platform_security

router = APIRouter(prefix="/orgs", tags=["orgs"])


def _my_org(org: Organization, role: UserRole, access: str = "member") -> MyOrganizationRead:
    return MyOrganizationRead(
        **OrganizationRead.model_validate(org).model_dump(), role=role, access=access, archived=org.archived_at is not None
    )


def _ingestion_settings(org: Organization) -> IngestionSettingsRead:
    effective = resolve_ingestion_settings(org)
    return IngestionSettingsRead(
        import_partial_success=effective.import_partial_success,
        asset_existing_strategy=effective.asset_existing_strategy,
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
    org = db.get(Organization, org_id)
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
    org = db.get(Organization, org_id, with_for_update=True)
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
