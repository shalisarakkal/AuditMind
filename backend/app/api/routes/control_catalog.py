import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_sysadmin
from app.db.session import get_db
from app.models.control_catalog import FindingControlRule, FindingControlDecision
from app.models.membership import OrgMembership
from app.models.user import User
from app.schemas.control_catalog import MappingKey, MappingProposal, MappingApproval
from app.services import control_catalog as service

router = APIRouter(tags=["control-catalog"])


def no_store(response):
    response.headers["Cache-Control"] = "no-store"


@router.get("/platform/control-catalogs")
def platform_catalogs(response: Response, db: Session = Depends(get_db), _: User = Depends(require_sysadmin)):
    no_store(response)
    return service.catalogs(db)


@router.post("/platform/control-catalogs/baseline")
def install(response: Response, db: Session = Depends(get_db), actor: User = Depends(require_sysadmin)):
    no_store(response)
    return service.install_baseline(db, actor.id)


@router.get("/platform/control-catalogs/{catalog_id}")
def platform_controls(catalog_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: User = Depends(require_sysadmin)):
    no_store(response)
    return service.catalog_controls(db, catalog_id)


@router.get("/orgs/{org_id}/control-catalogs")
def catalogs(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.catalogs(db)


@router.get("/orgs/{org_id}/control-catalogs/{catalog_id}")
def controls(org_id: uuid.UUID, catalog_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.catalog_controls(db, catalog_id)


@router.get("/orgs/{org_id}/findings/{finding_id}/control-mapping")
def mapping(org_id: uuid.UUID, finding_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.read(db, org_id, finding_id)


@router.post("/orgs/{org_id}/findings/{finding_id}/control-mapping/proposals")
def propose(org_id: uuid.UUID, finding_id: uuid.UUID, payload: MappingProposal, response: Response, db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.change(db, org_id, finding_id, member.user_id, payload, "propose")


@router.post("/orgs/{org_id}/findings/{finding_id}/control-mapping/approve")
def approve(org_id: uuid.UUID, finding_id: uuid.UUID, payload: MappingApproval, response: Response, db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.change(db, org_id, finding_id, member.user_id, payload, "approve")


@router.post("/orgs/{org_id}/findings/{finding_id}/control-mapping/withdraw")
def withdraw(org_id: uuid.UUID, finding_id: uuid.UUID, payload: MappingKey, response: Response, db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.change(db, org_id, finding_id, member.user_id, payload, "withdraw")


@router.get("/orgs/{org_id}/control-rules/{rule_id}/history")
def history(org_id: uuid.UUID, rule_id: uuid.UUID, response: Response, limit: int = Query(20, ge=1, le=50), before_version: int | None = Query(None, ge=1), db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    no_store(response)
    service.require_available(db)
    if db.scalar(select(FindingControlRule.id).where(FindingControlRule.org_id == org_id, FindingControlRule.id == rule_id)) is None:
        raise HTTPException(404, "Mapping rule not found")
    query = select(FindingControlDecision).where(FindingControlDecision.org_id == org_id, FindingControlDecision.rule_id == rule_id)
    if before_version is not None:
        query = query.where(FindingControlDecision.version < before_version)
    rows = db.scalars(query.order_by(FindingControlDecision.version.desc()).limit(limit)).all()
    return list(service.decisions_data(db, rows).values())


@router.get("/orgs/{org_id}/control-rules/{rule_id}")
def retained_rule(org_id: uuid.UUID, rule_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.read_rule(db, org_id, rule_id)


@router.post("/orgs/{org_id}/control-rules/{rule_id}/proposals")
def propose_rule(org_id: uuid.UUID, rule_id: uuid.UUID, payload: MappingProposal, response: Response, db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.change(db, org_id, None, member.user_id, payload, "propose", rule_id=rule_id)


@router.post("/orgs/{org_id}/control-rules/{rule_id}/approve")
def approve_rule(org_id: uuid.UUID, rule_id: uuid.UUID, payload: MappingApproval, response: Response, db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.change(db, org_id, None, member.user_id, payload, "approve", rule_id=rule_id)


@router.post("/orgs/{org_id}/control-rules/{rule_id}/withdraw")
def withdraw_rule(org_id: uuid.UUID, rule_id: uuid.UUID, payload: MappingKey, response: Response, db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    no_store(response)
    return service.change(db, org_id, None, member.user_id, payload, "withdraw", rule_id=rule_id)
