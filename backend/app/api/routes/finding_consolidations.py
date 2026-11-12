"""Read-only consolidation foundation; no apply/undo/publish route exists."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.membership import OrgMembership
from app.schemas.finding_consolidation import ConsolidationPreviewRequest, ConsolidationPage, ConsolidationHistoryPage
from app.services import finding_consolidations

router = APIRouter(prefix="/orgs/{org_id}/finding-consolidations", tags=["finding consolidation foundation"])


def release_request_reads(db):
    # Authentication commits its activity update before membership is read.
    # End only this route's read transaction before acquiring the independent
    # snapshot, otherwise concurrent requests can exhaust the same pool twice.
    # Never flush or discard a caller's pending ORM changes.
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, "Pending database changes must be completed before preview")
    db.rollback()


@router.get("", response_model=ConsolidationPage)
def list_groups(org_id: uuid.UUID, response: Response, limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0, le=2_147_483_647), db: Session = Depends(get_db),
        _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return finding_consolidations.page(db, org_id, limit=limit, offset=offset)


@router.get("/{group_id}/history", response_model=ConsolidationHistoryPage)
def group_history(org_id: uuid.UUID, group_id: uuid.UUID, response: Response,
        limit: int = Query(20, ge=1, le=100), before_version: int | None = Query(None, ge=1),
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return finding_consolidations.history(db, org_id, group_id, limit=limit, before_version=before_version)


@router.post("/preview")
def preview_group(org_id: uuid.UUID, payload: ConsolidationPreviewRequest, response: Response,
        db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    actor_id = member.user_id
    release_request_reads(db)
    return finding_consolidations.preview(db, org_id, actor_id, payload.canonical_decision_id)
