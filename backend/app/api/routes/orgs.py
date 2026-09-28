import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_org_member, require_org_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.org_settings import IngestionSettingsRead, IngestionSettingsUpdate
from app.schemas.organization import MemberAdd, MyOrganizationRead, OrganizationCreate, OrganizationRead
from app.schemas.user import MemberRead, UserRead
from app.services.org_settings import apply_overrides, resolve_ingestion_settings

router = APIRouter(prefix="/orgs", tags=["orgs"])


def _my_org(membership: OrgMembership) -> MyOrganizationRead:
    return MyOrganizationRead(
        **OrganizationRead.model_validate(membership.organization).model_dump(), role=membership.role
    )


def _member(membership: OrgMembership) -> MemberRead:
    return MemberRead(**UserRead.model_validate(membership.user).model_dump(), role=membership.role)


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
    )


@router.get("", response_model=list[MyOrganizationRead])
def list_my_orgs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[MyOrganizationRead]:
    """Orgs the caller belongs to, for the org picker. Oldest membership first."""
    memberships = (
        db.query(OrgMembership)
        .filter(OrgMembership.user_id == user.id)
        .order_by(OrgMembership.created_at)
        .all()
    )
    return [_my_org(m) for m in memberships]


@router.post("", response_model=MyOrganizationRead, status_code=status.HTTP_201_CREATED)
def create_org(
    payload: OrganizationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> MyOrganizationRead:
    org = Organization(name=payload.name, industry=payload.industry, size=payload.size)
    db.add(org)
    db.flush()
    membership = OrgMembership(user_id=user.id, org_id=org.id, role=UserRole.admin)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return _my_org(membership)


@router.get("/{org_id}", response_model=OrganizationRead)
def get_org(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> Organization:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("/{org_id}/users", response_model=list[MemberRead])
def list_org_users(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[MemberRead]:
    memberships = db.query(OrgMembership).filter(OrgMembership.org_id == org_id).all()
    return [_member(m) for m in memberships]


@router.post("/{org_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    org_id: uuid.UUID,
    payload: MemberAdd,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> MemberRead:
    """Give an existing user access to this org. Admins only."""
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No user with that email")
    if db.get(OrgMembership, (user.id, org_id)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    membership = OrgMembership(user_id=user.id, org_id=org_id, role=payload.role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return _member(membership)


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
    _: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> IngestionSettingsRead:
    """Admins only. Send a value to override a setting, null to clear the
    override; omitted fields are unchanged."""
    org = db.get(Organization, org_id)
    apply_overrides(org, payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    db.refresh(org)
    return _ingestion_settings(org)
