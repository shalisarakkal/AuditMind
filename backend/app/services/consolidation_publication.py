"""Authorized native pair publication/undo; caller request IDs survive unknown responses."""
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import String, and_, cast, delete, func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.models.finding import Finding
from app.models.finding_consolidation import FindingConsolidation, FindingConsolidationDecision, FindingConsolidationMember
from app.models.archive import ArchiveJob, ArchiveBatch
from app.models.scan import Scan
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.services.consolidation_transactions import _admit, _bounded_lock_wait, _digest, _receipt, metadata_preview
from app.services.consolidation_visibility import _stage_with_visibility, _clear_after_undo
from app.services.consolidation_policy import configuration
from app.services.events import actor_label, record_event


def _clean(db):
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409,'Complete pending database changes first')
    if db.connection().get_isolation_level()!='READ COMMITTED':
        raise HTTPException(409,'A fresh read-committed transaction is required')


def preview(db,org_id,actor_id,identifier):
    result=metadata_preview(db,org_id,actor_id,identifier)
    if not result['context']['feature_enabled']:
        raise HTTPException(409,'Enable reviewed finding consolidation in organization Settings first')
    return dict(review_token=result['review_token'],expected_version=result['expected_version'],
        canonical_decision_id=result['canonical_decision_id'],members=result['context']['members'],findings=result['findings'],
        source_counts={kind:sum(r['resource_kind']==kind for r in result['context']['resources'])
            for kind in ('finding','observation','scan','asset')},apply_available=True)


def apply_reviewed(db,org_id,actor_id,payload):
    _clean(db)
    try:
        with db.begin_nested(),_bounded_lock_wait(db):
            actor=_admit(db,org_id,actor_id)
            previous=db.scalar(select(FindingConsolidationDecision.id).where(FindingConsolidationDecision.org_id==org_id,
                FindingConsolidationDecision.request_id==payload.request_id))
            if previous is None and not configuration(db,org_id)['enabled']:
                raise HTTPException(409,'Reviewed finding consolidation is disabled for this organization')
            result=_stage_with_visibility(db,org_id,actor_id,payload)
            if not result['replayed']:
                canonical_id=db.scalar(select(FindingConsolidation.canonical_finding_id).where(FindingConsolidation.org_id==org_id,FindingConsolidation.id==uuid.UUID(result['consolidation_id'])))
                record_event(db,'finding_consolidated',org_id=org_id,actor=actor,item=result['consolidation_id'],
                    details=dict(finding_id=str(canonical_id),consolidation_id=result['consolidation_id'],version=result['version'],
                        decision_id=result['decision_id'],rationale=payload.rationale))
                db.flush()
        db.commit()
        return result
    except DBAPIError as error:
        if getattr(error.orig,'sqlstate',None) in ('55P03','23505','23503'):
            raise HTTPException(409,'Concurrent consolidation or source change; reload and review again') from error
        raise


def _undo_prepare(db,org_id,actor_id,group_id):
    actor=db.get(User,actor_id)
    member=db.scalar(select(OrgMembership).where(OrgMembership.org_id==org_id,OrgMembership.user_id==actor_id))
    org=db.get(Organization,org_id)
    if actor is None or not actor.is_active or actor.must_change_password or member is None or member.role!='admin':
        raise HTTPException(403,'An active actual organization administrator is required')
    if org is None or org.archived_at is not None or org.purge_requested_at is not None:
        raise HTTPException(409,'Organization is read-only or unavailable')
    root=db.scalar(select(FindingConsolidation).where(FindingConsolidation.org_id==org_id,FindingConsolidation.id==group_id)
        .execution_options(populate_existing=True))
    if root is None:raise HTTPException(404,'Consolidation not found')
    if root.state!='active':raise HTTPException(409,'This consolidation is not active')
    rows=db.execute(select(Finding.id,Finding.consolidation_id,Finding.consolidation_alias_id,
        Finding.archived_at,Finding.workflow_version,Finding.risk_verification_version,Finding.risk_verification_state,
        Finding.scan_id,Finding.asset_id).where(Finding.org_id==org_id,
            Finding.id.in_((root.finding_a_id,root.finding_b_id))).order_by(Finding.id)).all()
    if len(rows)!=2 or any(r.consolidation_id!=root.id for r in rows):
        raise HTTPException(409,'Both retained published members are required; purged data cannot be recreated')
    if any((r.consolidation_alias_id is not None) != (r.id!=root.canonical_finding_id) for r in rows):
        raise HTTPException(409,'Published visibility links changed; review current membership')
    if any(r.risk_verification_state=='approved' for r in rows):
        raise HTTPException(409,'Explicitly revoke approved scoring evidence before undo')
    members=db.execute(select(FindingConsolidationMember.finding_id,FindingConsolidationMember.role,
        FindingConsolidationMember.generation).where(FindingConsolidationMember.org_id==org_id,
            FindingConsolidationMember.consolidation_id==root.id).order_by(FindingConsolidationMember.finding_id)).all()
    expected={root.canonical_finding_id:'canonical',next(value for value in (root.finding_a_id,root.finding_b_id) if value!=root.canonical_finding_id):'alias'}
    if len(members)!=2 or {r.finding_id:r.role for r in members}!=expected or any(r.generation!=root.version for r in members):
        raise HTTPException(409,'Current membership generation is unavailable')
    # Job admission prevents new lifecycle jobs while undo commits. Failed
    # archive batches do not block recovery; only actual queued/running jobs do.
    from app.models.finding_consolidation import FindingConsolidationDependency as Dependency
    affected=select(Dependency.resource_id).where(Dependency.org_id==org_id,Dependency.consolidation_id==group_id,
        Dependency.generation==root.version,Dependency.resource_kind.in_(('finding','asset','scan')))
    from app.models.finding_observation import FindingObservation as Observation
    pair=(root.finding_a_id,root.finding_b_id)
    observed_scan=select(Observation.id).where(Observation.org_id==org_id,
        Observation.finding_id.in_(pair),Observation.scan_id==ArchiveBatch.item_id).exists()
    observed_asset=select(Observation.id).where(Observation.org_id==org_id,
        Observation.finding_id.in_(pair),Observation.asset_identity['asset_id'].astext==cast(ArchiveBatch.item_id,String)).exists()
    affected_job=or_(ArchiveBatch.item_id.in_(affected),
        and_(ArchiveBatch.item_type=='upload',observed_scan),and_(ArchiveBatch.item_type=='asset',observed_asset))
    if db.scalar(select(ArchiveJob.id).join(ArchiveBatch,ArchiveBatch.id==ArchiveJob.batch_id).where(
            ArchiveJob.org_id==org_id,ArchiveBatch.org_id==org_id,affected_job,
            ArchiveJob.status.in_(('pending','running'))).limit(1)) or db.scalar(select(Scan.id).where(
                Scan.org_id==org_id,Scan.status.in_(('pending','running'))).limit(1)):
        raise HTTPException(409,'An import or affected source operation is pending or running')
    context=dict(contract='consolidation-undo-v1',org_id=str(org_id),actor_id=str(actor_id),
        group_id=str(root.id),version=root.version,canonical_finding_id=str(root.canonical_finding_id),
        feature_version=configuration(db,org_id)['version'],members=[dict(r._mapping) for r in rows])
    # JSON-safe UUID/timestamp representation is identical for preview and write.
    import json
    context=json.loads(json.dumps(context,default=str))
    return dict(review_token=_digest(context),expected_version=root.version,context=context)


def undo_preview(db,org_id,actor_id,group_id):
    with db.get_bind().engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text('SET TRANSACTION READ ONLY'))
            return _undo_prepare(snapshot,org_id,actor_id,group_id)


def undo(db,org_id,actor_id,group_id,payload):
    _clean(db)
    if not payload.confirm:raise HTTPException(422,'Explicit review acknowledgment is required')
    request_hash=_digest(dict(operation='undo',org_id=str(org_id),actor_id=str(actor_id),
        group_id=str(group_id),request=payload.model_dump(mode='json')))
    try:
        with db.begin_nested(),_bounded_lock_wait(db):
            actor=_admit(db,org_id,actor_id)
            prior=db.scalar(select(FindingConsolidationDecision).where(FindingConsolidationDecision.org_id==org_id,
                FindingConsolidationDecision.request_id==payload.request_id))
            if prior:
                if prior.request_hash!=request_hash:raise HTTPException(409,'Request identifier was used for a different operation')
                return _receipt(prior,True)
            db.expire_all()
            db.scalar(select(FindingConsolidation.id).where(FindingConsolidation.org_id==org_id,
                FindingConsolidation.id==group_id).with_for_update(nowait=True))
            prepared=_undo_prepare(db,org_id,actor_id,group_id)
            root=db.get(FindingConsolidation,group_id)
            db.scalars(select(Finding.id).where(Finding.org_id==org_id,
                Finding.id.in_((root.finding_a_id,root.finding_b_id))).order_by(Finding.id)
                .with_for_update(key_share=True,nowait=True)).all()
            checked=_undo_prepare(db,org_id,actor_id,group_id)
            if prepared!=checked or checked['review_token']!=payload.review_token or root.version!=payload.expected_version:
                raise HTTPException(409,'Undo context changed; reload and review again')
            root.version+=1;root.state='undone';root.updated_at=datetime.now(timezone.utc)
            receipt=FindingConsolidationDecision(org_id=org_id,consolidation_id=root.id,request_id=payload.request_id,
                request_hash=request_hash,version=root.version,state='undone',rationale=payload.rationale,
                context=checked['context'],actor_id=actor_id,actor_label=actor_label(actor))
            db.add(receipt)
            db.execute(delete(FindingConsolidationMember).where(FindingConsolidationMember.org_id==org_id,
                FindingConsolidationMember.consolidation_id==root.id))
            db.flush()
            _clear_after_undo(db,org_id,root.id,root.version)
            record_event(db,'finding_consolidation_undone',org_id=org_id,actor=actor,item=str(root.id),
                details=dict(finding_id=str(root.canonical_finding_id),consolidation_id=str(root.id),version=root.version,decision_id=str(receipt.id),rationale=payload.rationale))
            db.flush()
            result=_receipt(receipt,False)
        db.commit()
        return result
    except DBAPIError as error:
        if getattr(error.orig,'sqlstate',None) in ('55P03','23505','23503'):
            raise HTTPException(409,'Concurrent undo or source change; reload before retrying') from error
        raise


def _for_finding(db,org_id,finding_id,*,limit=20,offset=0):
    rows=db.scalars(select(FindingConsolidation).where(FindingConsolidation.org_id==org_id,
        or_(FindingConsolidation.finding_a_id==finding_id,FindingConsolidation.finding_b_id==finding_id))
        .order_by(FindingConsolidation.updated_at.desc(),FindingConsolidation.id).offset(offset).limit(limit+1)).all()
    current=db.scalar(select(Finding.consolidation_id).where(Finding.org_id==org_id,Finding.id==finding_id))
    return dict(settings=configuration(db,org_id),current_group_id=str(current) if current else None,has_more=len(rows)>limit,limit=limit,offset=offset,items=[dict(id=str(r.id),version=r.version,state=r.state,
        published=current==r.id,canonical_finding_id=str(r.canonical_finding_id),canonical_decision_id=str(r.canonical_decision_id),
        member_ids=[str(r.finding_a_id),str(r.finding_b_id)]) for r in rows[:limit]])


def for_finding(db,org_id,finding_id,*,limit=20,offset=0):
    # Caller releases its authentication read transaction before this snapshot,
    # preventing double pool checkout and mixed group/visibility generations.
    with db.get_bind().engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text('SET TRANSACTION READ ONLY'))
            return _for_finding(snapshot,org_id,finding_id,limit=limit,offset=offset)
