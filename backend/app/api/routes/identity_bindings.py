import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import IdentityTool
from app.models.user import User
from app.schemas.identity_binding import ToolCreate, IdentityBind, IdentityDecision
from app.schemas.identity_binding import IdentityReference, IdentityCarryForward
from app.services.identity_comparison import compare_observation, carry_forward
from app.schemas.identity_binding import CanonicalSelection
from app.models.finding_canonical import FindingCanonicalDecision
from app.services import finding_canonical
from app.schemas.finding_observation import FindingObservationRead
from app.services.events import record_event
from app.services import finding_identity
from app.services.identity_bindings import read_observations, write_binding

router = APIRouter(prefix="/orgs/{org_id}", tags=["finding identity"])


def tool_read(row):
    return dict(id=str(row.id), name=row.name, active=row.active, version=row.version,
                source_mapping=finding_identity.NESSUS_MAPPING)


@router.get("/identity-tools")
def list_tools(org_id: uuid.UUID, offset: int = Query(0, ge=0),
               db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    return [tool_read(row) for row in db.scalars(select(IdentityTool).where(
        IdentityTool.org_id == org_id).order_by(IdentityTool.name, IdentityTool.id).offset(offset).limit(100))]


@router.post("/identity-tools", status_code=201)
def create_tool(org_id: uuid.UUID, payload: ToolCreate, db: Session = Depends(get_db),
                member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    if db.scalar(select(IdentityTool.id).where(IdentityTool.org_id == org_id,
            func.lower(IdentityTool.name) == func.lower(payload.name))) is not None:
        raise HTTPException(409, "A tool instance with this name already exists")
    tool = IdentityTool(org_id=org_id, name=payload.name)
    db.add(tool)
    db.flush()
    record_event(db, "identity_tool_created", org_id=org_id, actor=db.get(User, member.user_id),
        item=tool.name, details=dict(tool_id=str(tool.id), rationale=payload.rationale))
    db.commit()
    return tool_read(tool)


@router.post("/identity-tools/{tool_id}/retire")
def retire_tool(org_id: uuid.UUID, tool_id: uuid.UUID, payload: IdentityDecision,
                db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    from app.services.org_lock import lock_org
    def busy():
        raise HTTPException(409, "Inventory publication is busy; retry tool retirement after the current batch")
    lock_org(db, org_id, on_wait=busy)
    tool = db.scalar(select(IdentityTool).where(IdentityTool.org_id == org_id, IdentityTool.id == tool_id))
    if tool is None:
        raise HTTPException(404, "Tool instance not found")
    if tool.version != payload.expected_version or not tool.active:
        raise HTTPException(409, "Tool instance changed or retired; reload before retrying")
    from app.services.consolidation_lifecycle import ensure_free
    ensure_free(db,org_id,'tool',tool_id)
    tool.active = False
    tool.version += 1
    record_event(db, "identity_tool_retired", org_id=org_id, actor=db.get(User, member.user_id),
        item=tool.name, details=dict(tool_id=str(tool.id), rationale=payload.rationale))
    db.commit()
    return tool_read(tool)


def observation(db, org_id, finding_id, observation_id):
    finding = db.scalar(select(Finding).where(Finding.org_id == org_id, Finding.id == finding_id))
    if finding is None:
        raise HTTPException(404, "Finding not found")
    if finding.archived_at is not None:
        raise HTTPException(409, "Restore the finding before reviewing its identity")
    row = db.scalar(select(FindingObservation).where(FindingObservation.org_id == org_id,
        FindingObservation.finding_id == finding_id, FindingObservation.id == observation_id))
    if row is None:
        raise HTTPException(404, "Observation not found")
    return row


@router.get("/findings/{finding_id}/observations/{observation_id}/identity-binding", response_model=FindingObservationRead)
def read_binding(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                 db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    return read_observations(db, org_id, [observation(db, org_id, finding_id, observation_id)])[0]


@router.put("/findings/{finding_id}/observations/{observation_id}/identity-binding", response_model=FindingObservationRead)
def bind_identity(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                  payload: IdentityBind, db: Session = Depends(get_db),
                  member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    return write_binding(db, org_id, observation(db, org_id, finding_id, observation_id), member.user_id, payload)


@router.post("/findings/{finding_id}/observations/{observation_id}/identity-binding/revoke", response_model=FindingObservationRead)
def revoke_identity(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                    payload: IdentityDecision, db: Session = Depends(get_db),
                    member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    return write_binding(db, org_id, observation(db, org_id, finding_id, observation_id), member.user_id, payload, revoke=True)


@router.post("/findings/{finding_id}/observations/{observation_id}/identity-binding/compare")
def compare_identity(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                     payload: IdentityReference, db: Session = Depends(get_db),
                     _: OrgMembership = Depends(require_org_member)):
    return compare_observation(db, org_id, observation(db, org_id, finding_id, observation_id), payload.source_observation_id)


@router.post("/findings/{finding_id}/observations/{observation_id}/identity-binding/carry-forward", response_model=FindingObservationRead)
def carry_forward_identity(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                           payload: IdentityCarryForward, db: Session = Depends(get_db),
                           member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    return carry_forward(db, org_id, observation(db, org_id, finding_id, observation_id), member.user_id, payload)


@router.post("/findings/{finding_id}/observations/{observation_id}/identity-binding/canonical/preview")
def preview_canonical(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                      payload: IdentityReference, db: Session = Depends(get_db),
                      _: OrgMembership = Depends(require_org_member)):
    return finding_canonical.preview(db, org_id, observation(db, org_id, finding_id, observation_id), payload.source_observation_id)


@router.post("/findings/{finding_id}/observations/{observation_id}/identity-binding/canonical")
def select_canonical(org_id: uuid.UUID, finding_id: uuid.UUID, observation_id: uuid.UUID,
                     payload: CanonicalSelection, db: Session = Depends(get_db),
                     member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    return finding_canonical.save(db, org_id, observation(db, org_id, finding_id, observation_id), member.user_id, payload)


@router.get("/findings/{finding_id}/canonical-decisions")
def canonical_history(org_id: uuid.UUID, finding_id: uuid.UUID, offset: int = Query(0, ge=0),
                      db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    # Historical UUIDs remain readable after purge, scoped to this organization.
    rows = db.scalars(select(FindingCanonicalDecision).where(FindingCanonicalDecision.org_id == org_id,
        or_(FindingCanonicalDecision.finding_a_id == finding_id, FindingCanonicalDecision.finding_b_id == finding_id))
        .order_by(FindingCanonicalDecision.created_at.desc(), FindingCanonicalDecision.id.desc()).offset(offset).limit(20)).all()
    versions = dict(db.execute(select(FindingCanonicalDecision.pair_key, FindingCanonicalDecision.version).where(
        FindingCanonicalDecision.org_id == org_id, FindingCanonicalDecision.pair_key.in_({row.pair_key for row in rows}))
        .order_by(FindingCanonicalDecision.pair_key, FindingCanonicalDecision.version.desc())
        .distinct(FindingCanonicalDecision.pair_key)).all()) if rows else {}
    return [{**finding_canonical.receipt(row), "latest": row.version == versions.get(row.pair_key)} for row in rows]


@router.post("/canonical-decisions/{decision_id}/revoke")
def revoke_canonical(org_id: uuid.UUID, decision_id: uuid.UUID, payload: IdentityDecision,
                     db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    return finding_canonical.revoke(db, org_id, decision_id, member.user_id, payload)
