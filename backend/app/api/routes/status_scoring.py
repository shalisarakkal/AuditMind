import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.api.deps import require_org_member, require_org_role, require_sysadmin
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.finding_verification import OrganizationRiskPolicy
from app.models.membership import OrgMembership
from app.models.session import PlatformSetting
from app.models.user import User
from app.schemas.status_scoring import RiskPolicyRead,RiskPolicyUpdate,PlatformRiskPolicyUpdate,ProofSubmission,ProofReview
from app.services import status_scoring
from app.services.events import record_event
from app.services.knowledge_service import require_active_org,KnowledgeError

router=APIRouter(tags=['status-aware scoring'])


def _refresh(db,org_id):
    from app.services import dashboard_snapshots
    if dashboard_snapshots.configuration(db).enabled:
        dashboard_snapshots.enqueue(db,org_id)


@router.get('/platform/status-scoring',response_model=RiskPolicyRead)
def get_platform_policy(response:Response,db:Session=Depends(get_db),_:User=Depends(require_sysadmin)):
    response.headers['Cache-Control']='no-store'
    value=status_scoring.platform_policy(db)
    return RiskPolicyRead(enabled=value['enabled'],platform_enabled=value['enabled'],version=value['version'],platform_version=value['version'])


@router.patch('/platform/status-scoring',response_model=RiskPolicyRead)
def save_platform_policy(payload:PlatformRiskPolicyUpdate,response:Response,db:Session=Depends(get_db),actor:User=Depends(require_sysadmin)):
    db.execute(select(func.pg_advisory_xact_lock(15,0)))
    current=db.scalar(select(User).where(User.id==actor.id).with_for_update(read=True).execution_options(populate_existing=True))
    if not current or not current.is_active or not current.is_sysadmin:raise HTTPException(403,'Platform permissions changed')
    old=status_scoring.platform_policy(db)
    if old['version']!=payload.expected_version:raise HTTPException(409,'Scoring policy changed; reload before retrying')
    if old['enabled']!=payload.enabled:
        value=dict(enabled=payload.enabled,version=old['version']+1)
        row=db.get(PlatformSetting,status_scoring.KEY)
        if row:row.value=value
        else:db.add(PlatformSetting(key=status_scoring.KEY,value=value))
        record_event(db,'settings_changed',org_id=None,actor=current,item='Status-aware scoring default',details={'from':old,'to':value})
    db.commit()
    return get_platform_policy(response,db,current)


@router.get('/orgs/{org_id}/status-scoring',response_model=RiskPolicyRead)
def get_org_policy(org_id:uuid.UUID,response:Response,db:Session=Depends(get_db),_:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return status_scoring.configuration(db,org_id)


@router.patch('/orgs/{org_id}/status-scoring',response_model=RiskPolicyRead)
def save_org_policy(org_id:uuid.UUID,payload:RiskPolicyUpdate,response:Response,db:Session=Depends(get_db),
        member:OrgMembership=Depends(require_org_role(UserRole.admin))):
    db.execute(select(func.pg_advisory_xact_lock(16,int.from_bytes(org_id.bytes[:4],'big',signed=True))))
    try:require_active_org(db,org_id,lock=True)
    except KnowledgeError as error:raise HTTPException(409,str(error)) from error
    current=db.scalar(select(OrgMembership).where(OrgMembership.org_id==org_id,OrgMembership.user_id==member.user_id)
        .with_for_update().execution_options(populate_existing=True))
    if current is None or current.role!=UserRole.admin:raise HTTPException(403,'Organization permissions changed')
    row=db.scalar(select(OrganizationRiskPolicy).where(OrganizationRiskPolicy.org_id==org_id).with_for_update())
    version=row.version if row else 0
    if version!=payload.expected_version:raise HTTPException(409,'Scoring policy changed; reload before retrying')
    old=row.enabled_override if row else None
    if old!=payload.enabled_override:
        if row is None:
            row=OrganizationRiskPolicy(org_id=org_id,version=0);db.add(row)
        row.enabled_override=payload.enabled_override;row.version+=1
        record_event(db,'settings_changed',org_id=org_id,actor=db.get(User,current.user_id),
            item='Status-aware scoring override',details={'from':old,'to':payload.enabled_override})
    db.commit()
    _refresh(db,org_id)
    return get_org_policy(org_id,response,db,current)


@router.get('/orgs/{org_id}/findings/{finding_id}/risk-verification')
def get_proof(org_id:uuid.UUID,finding_id:uuid.UUID,response:Response,before:int|None=Query(None,ge=1),
        limit:int=Query(20,ge=1,le=50),db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return status_scoring.read_verification(db,org_id,finding_id,member,before=before,limit=limit)


@router.post('/orgs/{org_id}/findings/{finding_id}/risk-verification')
def submit_proof(org_id:uuid.UUID,finding_id:uuid.UUID,payload:ProofSubmission,db:Session=Depends(get_db),
        member:OrgMembership=Depends(require_org_role(UserRole.admin,UserRole.auditor))):
    result=status_scoring.write_verification(db,org_id,finding_id,member,payload)
    _refresh(db,org_id)
    return result


@router.post('/orgs/{org_id}/findings/{finding_id}/risk-verification/review')
def review_proof(org_id:uuid.UUID,finding_id:uuid.UUID,payload:ProofReview,db:Session=Depends(get_db),
        member:OrgMembership=Depends(require_org_role(UserRole.admin))):
    result=status_scoring.write_verification(db,org_id,finding_id,member,payload,review=True)
    _refresh(db,org_id)
    return result
