"""Public actions are separate from read-only previews and legacy core stubs."""
import uuid
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.membership import OrgMembership
from app.services import publication_actions as actions
from app.services.publication_transactions import PublicationRequest, SettingRequest
from app.schemas.observation_publication import PublicationPreviewRequest

router=APIRouter(prefix='/orgs/{org_id}/observation-publication', tags=['observation-publication'])


def release_reads(db):
    from fastapi import HTTPException
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, 'Complete pending database changes first')
    db.rollback()


@router.get('/settings')
def setting(org_id:uuid.UUID,response:Response,db:Session=Depends(get_db),_:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return actions.configuration(db,org_id)


@router.patch('/settings')
def update_setting(org_id:uuid.UUID,payload:SettingRequest,response:Response,db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return actions.update_setting(db,org_id,member.user_id,payload)


@router.post('/findings/{finding_id}/observations/{observation_id}/preview')
def preview(org_id:uuid.UUID,finding_id:uuid.UUID,observation_id:uuid.UUID,payload:PublicationPreviewRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    actor_id=member.user_id;response.headers['Cache-Control']='no-store';release_reads(db)
    return actions.preview(db,org_id,actor_id,finding_id,observation_id)


@router.post('/findings/{finding_id}/observations/{observation_id}/publish')
def publish(org_id:uuid.UUID,finding_id:uuid.UUID,observation_id:uuid.UUID,payload:PublicationRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return actions.apply(db,org_id,member.user_id,finding_id,payload,observation_id)


@router.post('/findings/{finding_id}/undo-preview')
def undo_preview(org_id:uuid.UUID,finding_id:uuid.UUID,payload:PublicationPreviewRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    actor_id=member.user_id;response.headers['Cache-Control']='no-store';release_reads(db)
    return actions.preview(db,org_id,actor_id,finding_id)


@router.post('/findings/{finding_id}/undo')
def undo(org_id:uuid.UUID,finding_id:uuid.UUID,payload:PublicationRequest,response:Response,
        db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return actions.apply(db,org_id,member.user_id,finding_id,payload)
