import uuid
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.asset_context import AssetContextHistory
from app.models.membership import OrgMembership
from app.schemas.asset_context import AssetContextPatch, AssetContextRead, AssetContextHistoryRead
from app.services import asset_context as service

router=APIRouter(prefix="/orgs/{org_id}/assets",tags=["asset-context"])

@router.get("/context-facets")
def facets(org_id:uuid.UUID,response:Response,db:Session=Depends(get_db),_:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return service.facets(db,org_id)

@router.get("/{asset_id}/context",response_model=AssetContextRead)
def read(org_id:uuid.UUID,asset_id:uuid.UUID,response:Response,db:Session=Depends(get_db),_:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return service.get(db,org_id,asset_id)

@router.patch("/{asset_id}/context",response_model=AssetContextRead)
def patch(org_id:uuid.UUID,asset_id:uuid.UUID,payload:AssetContextPatch,response:Response,db:Session=Depends(get_db),member:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    return service.save(db,org_id,asset_id,member.user_id,payload)

@router.get("/{asset_id}/context/history",response_model=list[AssetContextHistoryRead])
def history(org_id:uuid.UUID,asset_id:uuid.UUID,response:Response,limit:int=Query(20,ge=1,le=50),before_version:int|None=Query(None,ge=1),db:Session=Depends(get_db),_:OrgMembership=Depends(require_org_member)):
    response.headers['Cache-Control']='no-store'
    service.get(db,org_id,asset_id);service.require_available(db)
    query=select(AssetContextHistory).where(AssetContextHistory.org_id==org_id,AssetContextHistory.asset_id==asset_id)
    if before_version is not None:query=query.where(AssetContextHistory.version<before_version)
    return db.scalars(query.order_by(AssetContextHistory.version.desc()).limit(limit)).all()
