"""Version-fenced business context; imports never write these tables."""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import DBAPIError
from app.api.deps import authorize_org_write
from app.api.paging import contains
from app.models.asset import Asset
from app.models.asset_context import AssetContext, AssetContextHistory
from app.models.membership import OrgMembership
from app.models.user import User
from app.models.archive import ArchiveBatch, ArchiveJob, AssetScan
from app.models.enums import UserRole
from app.schemas.asset_context import AssetContextRead
from app.services.events import record_event


def available(db):
    # Metadata-only readiness also tolerates pre-migration/partial databases.
    from sqlalchemy import text
    return bool(db.scalar(text("""SELECT
      to_regclass('asset_contexts') IS NOT NULL AND to_regclass('asset_context_history') IS NOT NULL
      AND to_regclass('organization_asset_context_revisions') IS NOT NULL
      AND to_regprocedure('am_asset_context_guard_v1()') IS NOT NULL
      AND to_regprocedure('am_asset_context_tenant_v1()') IS NOT NULL
      AND to_regprocedure('am_asset_context_revision_v1()') IS NOT NULL
      AND (SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgenabled IN ('O','A') AND (
        (tgname='am_asset_context_guard' AND tgrelid IN (to_regclass('asset_contexts'),to_regclass('asset_context_history')))
        OR (tgname='am_asset_context_tenant' AND tgrelid=to_regclass('assets'))
        OR (tgname IN ('am_asset_context_revision_insert','am_asset_context_revision_update','am_asset_context_revision_delete','am_asset_context_revision_truncate')
          AND tgrelid IN (to_regclass('asset_contexts'),to_regclass('users'),to_regclass('org_memberships')))))=15""")))


def require_available(db):
    if not available(db):raise HTTPException(409, 'Asset context requires coordinated database activation')


def owner_label(name,email):
    label=f"{name} ({email})" if name else email
    return label if len(label)<=255 else email


def labels(db, org_id, ids):
    if not ids:return {}
    rows=db.execute(select(User.id,User.name,User.email,User.is_active).join(OrgMembership,OrgMembership.user_id==User.id)
        .where(OrgMembership.org_id==org_id,User.id.in_(ids)))
    return {r.id:(owner_label(r.name,r.email),'active' if r.is_active else 'inactive') for r in rows}


def read_many(db, org_id, ids, *, ready=None):
    if ready is None:ready=available(db)
    if not ready:return {id_:AssetContextRead(available=False) for id_ in ids}
    rows=db.scalars(select(AssetContext).where(AssetContext.org_id==org_id,AssetContext.asset_id.in_(ids))).all() if ids else []
    owners=labels(db,org_id,[r.owner_id for r in rows if r.owner_id])
    result={id_:AssetContextRead() for id_ in ids}
    for r in rows:
        label,state=owners.get(r.owner_id,(r.owner_label or 'Former/unavailable owner','former')) if r.owner_id else (None,'unassigned')
        result[r.asset_id]=AssetContextRead(version=r.version,owner_id=r.owner_id,owner_label=label,owner_status=state,
            environment=r.environment,business_criticality=r.business_criticality,updated_at=r.updated_at)
    return result


def get(db,org_id,asset_id):
    asset=db.execute(select(Asset.archived_at).where(Asset.id==asset_id,Asset.org_id==org_id)).one_or_none()
    if asset is None:raise HTTPException(404,'Asset not found')
    result=read_many(db,org_id,[asset_id])[asset_id]
    return result.model_copy(update={'asset_archived':asset.archived_at is not None})


def state(row):
    return dict(owner_id=str(row.owner_id) if row and row.owner_id else None,
        owner_label=row.owner_label if row else None,environment=row.environment if row else None,
        business_criticality=row.business_criticality if row else None)


def save(db,org_id,asset_id,actor_id,payload):
    try:
        actor=authorize_org_write(db,org_id,actor_id,(UserRole.admin,UserRole.auditor))
        require_available(db)
        # KEY SHARE permits scanner non-key updates; the separate context row
        # serializes context edits. Job admission fences archive/restore starts.
        asset=db.execute(select(Asset.id,Asset.hostname,Asset.ip,Asset.cloud_id,Asset.archived_at).where(Asset.id==asset_id,Asset.org_id==org_id)
            .with_for_update(read=True,key_share=True,nowait=True)).one_or_none()
        if asset is None or asset.archived_at:raise HTTPException(404,'Asset not found or archived')
        owned_scans=select(AssetScan.scan_id).where(AssetScan.asset_id==asset_id,AssetScan.created.is_(True))
        active_job=exists(select(ArchiveJob.id).where(ArchiveJob.batch_id==ArchiveBatch.id,ArchiveJob.status.in_(('pending','running'))))
        if db.scalar(select(ArchiveBatch.id).where(ArchiveBatch.org_id==org_id,
                or_(ArchiveBatch.item_id==asset_id,ArchiveBatch.item_id.in_(owned_scans)),
                or_(ArchiveBatch.state=='archiving',active_job)).limit(1)):
            raise HTTPException(409,'Asset or its owner import has an unfinished lifecycle operation')
        row=db.scalar(select(AssetContext).where(AssetContext.asset_id==asset_id,AssetContext.org_id==org_id)
            .with_for_update(nowait=True).execution_options(populate_existing=True))
        if row is None and db.scalar(select(AssetContextHistory.id).where(AssetContextHistory.asset_id==asset_id).limit(1)):
            raise HTTPException(409,'Retained context history requires version recovery')
        if payload.expected_version!=(row.version if row else 0):
            raise HTTPException(409,'Asset context changed; reload before retrying')
        before=state(row);after={**before,**payload.model_dump(exclude_unset=True,exclude={'expected_version','rationale'})}
        if 'owner_id' in after and after['owner_id'] is not None:after['owner_id']=str(after['owner_id'])
        if after['owner_id']!=before['owner_id']:
            if after['owner_id']:
                owner_id=uuid.UUID(after['owner_id'])
                member=db.scalar(select(OrgMembership).where(OrgMembership.org_id==org_id,OrgMembership.user_id==owner_id).with_for_update())
                user=db.scalar(select(User).where(User.id==owner_id).with_for_update().execution_options(populate_existing=True))
                if member is None or user is None or not user.is_active:raise HTTPException(422,'Owner must be an active organization member')
                after['owner_label']=owner_label(user.name,user.email)
            else:after['owner_label']=None
        if before==after:
            result=get(db,org_id,asset_id);db.rollback();return result
        if row is None:
            row=AssetContext(asset_id=asset_id,org_id=org_id,version=0)
            db.add(row)
        row.owner_id=uuid.UUID(after['owner_id']) if after['owner_id'] else None
        row.owner_label=after['owner_label'];row.environment=after['environment'];row.business_criticality=after['business_criticality']
        row.version+=1;row.updated_at=datetime.now(timezone.utc)
        db.add(AssetContextHistory(org_id=org_id,asset_id=asset_id,actor_id=actor_id,actor_label=actor.user.name or actor.user.email,
            version=row.version,before=before,after=after,rationale=payload.rationale))
        record_event(db,'asset_context_changed',org_id=org_id,actor=actor.user,item=asset.hostname or asset.ip or asset.cloud_id,
            details={'asset_id':str(asset_id),'version':row.version,'before':before,'after':after,'rationale':payload.rationale})
        db.commit()
        return get(db,org_id,asset_id)
    except DBAPIError as exc:
        db.rollback()
        if getattr(exc.orig,'sqlstate',None) in ('55P03','40001','40P01'):
            raise HTTPException(409,'Asset context or lifecycle is busy; reload and retry') from exc
        raise
    except BaseException:
        db.rollback();raise


def filter_condition(org_id,field,values):
    if not values:return None
    column=getattr(AssetContext,field)
    defined=select(AssetContext.asset_id).where(AssetContext.org_id==org_id,column.is_not(None))
    ordinary=[v for v in values if v!='']
    if field=='owner_id':
        try:ordinary=[uuid.UUID(v) for v in ordinary]
        except ValueError:raise HTTPException(422,'Owner filter must contain organization owner IDs or an empty value')
    if field=='business_criticality' and any(v not in ('critical','high','medium','low') for v in ordinary):
        raise HTTPException(422,'Unknown business criticality')
    found=Asset.id.in_(defined.where(column.in_(ordinary))) if ordinary else None
    missing=~Asset.id.in_(defined) if '' in values else None
    return or_(*(c for c in (found,missing) if c is not None))


def search_ids(org_id,q):
    if not q or not q.strip():return None
    current=select(User.id).join(OrgMembership,OrgMembership.user_id==User.id).where(OrgMembership.org_id==org_id,contains(q,User.name,User.email))
    matches=or_(contains(q,AssetContext.owner_label,AssetContext.environment,AssetContext.business_criticality),AssetContext.owner_id.in_(current))
    return select(AssetContext.asset_id).join(Asset,Asset.id==AssetContext.asset_id).where(AssetContext.org_id==org_id,Asset.org_id==org_id,Asset.archived_at.is_(None),matches)


def estimated_rows(db,statement):
    connection=db.connection()
    compiled=statement.compile(dialect=connection.dialect,compile_kwargs={'render_postcompile':True})
    plan=connection.exec_driver_sql('EXPLAIN (FORMAT JSON) '+str(compiled),compiled.params).scalar_one()
    return plan[0]['Plan']['Plan Rows']


def facets(db,org_id):
    if not available(db):return dict(managed_owner=[],managed_owner_labels={},managed_environment=[],business_criticality=[])
    query=select(AssetContext).join(Asset,Asset.id==AssetContext.asset_id).where(AssetContext.org_id==org_id,Asset.org_id==org_id,Asset.archived_at.is_(None))
    def distinct(column):return db.scalars(query.with_only_columns(column).where(column.is_not(None)).distinct().order_by(column)).all()
    owners=distinct(AssetContext.owner_id);names=labels(db,org_id,owners)
    snapshots=dict(db.execute(query.with_only_columns(AssetContext.owner_id,func.min(AssetContext.owner_label)).where(AssetContext.owner_id.is_not(None)).group_by(AssetContext.owner_id)).all())
    return dict(managed_owner=[str(i) for i in owners],managed_owner_labels={str(i):names.get(i,(snapshots.get(i) or 'Former owner','former'))[0] for i in owners},
        managed_environment=distinct(AssetContext.environment),business_criticality=distinct(AssetContext.business_criticality))
