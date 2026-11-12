"""Tenant-scoped suppression review and publication."""
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.membership import OrgMembership
from app.models.enums import UserRole
from app.schemas.finding_suppression import SuppressionTarget, SuppressionWrite
from app.schemas.finding_suppression import SuppressionPage, SuppressionHistoryPage
from app.services import finding_suppressions

router = APIRouter(prefix="/orgs/{org_id}/finding-suppressions", tags=["finding suppression ledger"])


@router.get("", response_model=SuppressionPage)
def list_suppressions(org_id: uuid.UUID, response: Response,
        state: Literal["suppressed", "cleared", "all"] = "suppressed",
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return finding_suppressions.page(db, org_id, state=state, limit=limit, offset=offset)


@router.get("/{suppression_id}/history", response_model=SuppressionHistoryPage)
def suppression_history(org_id: uuid.UUID, suppression_id: uuid.UUID, response: Response,
        limit: int = Query(50, ge=1, le=100), before_version: int | None = Query(None, ge=1),
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return finding_suppressions.history(db, org_id, suppression_id, limit=limit, before_version=before_version)


@router.post("/preview")
def preview_suppression(org_id: uuid.UUID, payload: SuppressionTarget, response: Response,
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    prepared = finding_suppressions.preview(db, org_id, payload)
    prepared.pop("context", None)
    return prepared


@router.post("/decisions")
def decide_suppression(org_id: uuid.UUID, payload: SuppressionWrite, response: Response,
        db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor))):
    response.headers["Cache-Control"] = "no-store"
    return finding_suppressions.decide(db, org_id, member, payload)


@router.get("/{suppression_id}/reappearances")
def suppression_reappearances(org_id: uuid.UUID, suppression_id: uuid.UUID, response: Response,
        limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return finding_suppressions.reappearances(db, org_id, suppression_id, limit=limit, offset=offset)
