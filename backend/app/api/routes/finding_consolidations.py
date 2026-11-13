"""Retained ledger, diagnostic preview and separately authorized default-off pair actions."""
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


from app.schemas.finding_consolidation import ConsolidationSettingUpdate, ConsolidationUndoRequest
from app.services.consolidation_transactions import MetadataRequest
from app.services import consolidation_policy, consolidation_publication


@router.get('/settings')
def read_settings(org_id:uuid.UUID,response:Response,db:Session=Depends(get_db),
        _:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return consolidation_policy.configuration(db,org_id)


@router.patch('/settings')
def save_settings(org_id:uuid.UUID,payload:ConsolidationSettingUpdate,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return consolidation_policy.update(db,org_id,member.user_id,payload)


@router.get('/for-finding/{finding_id}')
def read_finding_groups(org_id:uuid.UUID,finding_id:uuid.UUID,response:Response,limit:int=Query(20,ge=1,le=100),
        offset:int=Query(0,ge=0,le=2147483647),db:Session=Depends(get_db),
        _:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    release_request_reads(db)
    return consolidation_publication.for_finding(db,org_id,finding_id,limit=limit,offset=offset)


@router.post('/publication-preview')
def preview_publication(org_id:uuid.UUID,payload:ConsolidationPreviewRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    actor_id=member.user_id
    release_request_reads(db)
    return consolidation_publication.preview(db,org_id,actor_id,payload.canonical_decision_id)


@router.post('/apply')
def apply_publication(org_id:uuid.UUID,payload:MetadataRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return consolidation_publication.apply_reviewed(db,org_id,member.user_id,payload)


@router.post('/{group_id}/undo-preview')
def preview_undo(org_id:uuid.UUID,group_id:uuid.UUID,response:Response,db:Session=Depends(get_db),
        member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    actor_id=member.user_id
    release_request_reads(db)
    return consolidation_publication.undo_preview(db,org_id,actor_id,group_id)


@router.post('/{group_id}/undo')
def undo_publication(org_id:uuid.UUID,group_id:uuid.UUID,payload:ConsolidationUndoRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return consolidation_publication.undo(db,org_id,member.user_id,group_id,payload)
