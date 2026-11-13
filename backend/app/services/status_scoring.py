"""Verified workflow status affects current risk, never source severity/history."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import uuid
from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, exists, func, or_, select
from sqlalchemy.orm import defer
from app.models.archive import ArchiveBatch, ArchiveJob
from app.models.enums import ArchiveState, UserRole
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_history import FindingHistory
from app.models.finding_verification import FindingVerification, OrganizationRiskPolicy
from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
from app.models.membership import OrgMembership
from app.models.session import PlatformSetting
from app.models.user import User
from app.schemas.status_scoring import RiskPolicyRead
from app.services.events import actor_label, record_event
from app.services.knowledge_service import KnowledgeError, require_active_org
from app.services.org_lock import lock_org_jobs

KEY = 'status_aware_scoring'
POLICY_VERSION = 'verified-status-v1'
MAX_VALIDITY = timedelta(days=90)
REVIEW_ROLES = (UserRole.admin,)


def now():
    return datetime.now(timezone.utc)


def platform_policy(db):
    row=db.get(PlatformSetting,KEY,populate_existing=True)
    value=row.value if row else {}
    return dict(enabled=value.get('enabled',True),version=value.get('version',0))


def configuration(db,org_id):
    platform=platform_policy(db)
    row=db.get(OrganizationRiskPolicy,org_id,populate_existing=True)
    override=row.enabled_override if row else None
    return RiskPolicyRead(enabled=platform['enabled'] if override is None else override,
        platform_enabled=platform['enabled'],enabled_override=override,
        version=row.version if row else 0,platform_version=platform['version'])


def observation_count():
    return select(func.count()).select_from(FindingObservation).where(
        FindingObservation.org_id==Finding.org_id,FindingObservation.finding_id==Finding.id).correlate(Finding).scalar_subquery()


def eligible_exclusion(instant=None):
    instant=instant or now()
    document=exists(select(KnowledgeVersion.id).join(KnowledgeDocument,KnowledgeDocument.id==KnowledgeVersion.document_id)
        .where(KnowledgeVersion.id==Finding.risk_verification_document_id,KnowledgeDocument.org_id==Finding.org_id,
            KnowledgeVersion.current.is_(True),KnowledgeVersion.retired_at.is_(None),KnowledgeVersion.purged_at.is_(None),
            KnowledgeVersion.content_hash==Finding.risk_verification_source_hash)).correlate(Finding)
    status_changed=exists(select(FindingHistory.id).where(FindingHistory.org_id==Finding.org_id,
        FindingHistory.finding_id==Finding.id,FindingHistory.version>Finding.risk_verified_workflow_version,
        FindingHistory.before['status'].astext.is_distinct_from(FindingHistory.after['status'].astext))).correlate(Finding)
    group_record=exists(select(FindingVerification.id).where(FindingVerification.org_id==Finding.org_id,
        FindingVerification.finding_id==Finding.id,FindingVerification.version==Finding.risk_verification_version,
        FindingVerification.state=='approved',
        FindingVerification.attestation['group_context']['contract'].astext=='consolidated-proof-v1',
        FindingVerification.attestation['group_context']['group_id'].astext==cast(Finding.consolidation_id,String),
        FindingVerification.attestation['group_context']['canonical_finding_id'].astext==cast(Finding.id,String),
        FindingVerification.attestation['group_context']['digest'].astext==func.am_consolidation_proof_v1(Finding.org_id,Finding.consolidation_id))).correlate(Finding)
    old_group_record=exists(select(FindingVerification.id).where(FindingVerification.org_id==Finding.org_id,
        FindingVerification.finding_id==Finding.id,FindingVerification.version==Finding.risk_verification_version,
        FindingVerification.attestation['group_context'].is_not(None))).correlate(Finding)
    scope=case((Finding.consolidation_id.is_(None),~old_group_record),else_=group_record)
    return and_(scope, Finding.risk_verification_state=='approved',Finding.workflow_status.in_(('resolved','false_positive')),
        Finding.risk_verified_workflow_version<=Finding.workflow_version,~status_changed,
        Finding.risk_verified_at<=instant,Finding.risk_verification_expires_at>instant,
        Finding.risk_verified_observation_count==observation_count(),
        or_(Finding.risk_verification_source_kind=='reference',
            and_(Finding.risk_verification_source_kind=='document',document)))


def apply_policy(db,org_id,counts,*,filters=(),source_current=True,capture_basis=False):
    instant = now()
    config=configuration(db,org_id)
    adjusted={domain:dict(values) for domain,values in counts.items()}
    excluded={}
    if config.enabled and source_current:
        # The approved-only partial index keeps legacy/million-row inventory
        # counts on their existing covering indexes. Do not scan every finding
        # through proof joins merely to count the small verified subset.
        for domain,severity,count in db.execute(select(Finding.domain,Finding.severity,func.count()).where(
            Finding.org_id==org_id,Finding.active(),eligible_exclusion(instant),*filters)
                .group_by(Finding.domain,Finding.severity)):
            count=min(count,adjusted.get(domain,{}).get(severity,0))
            adjusted.setdefault(domain,{})[severity]=adjusted.get(domain,{}).get(severity,0)-count
            excluded[severity.value]=excluded.get(severity.value,0)+count
    suppressed = db.scalar(select(func.count()).select_from(Finding).where(Finding.org_id == org_id,
        Finding.archived_at.is_(None), Finding.suppression_id.is_not(None), *filters)) or 0
    aliases = db.scalar(select(func.count()).select_from(Finding).where(Finding.org_id == org_id,
        Finding.archived_at.is_(None), Finding.suppression_id.is_(None), Finding.consolidation_alias_id.is_not(None), *filters)) or 0
    total=sum(sum(values.values()) for values in counts.values())
    risk=sum(sum(values.values()) for values in adjusted.values())
    metadata={**config.model_dump(), 'recorded_findings':total+suppressed+aliases,'consolidated_alias_findings':aliases,'active_findings':total,'suppressed_findings':suppressed,'current_risk_findings':risk,
        'excluded_findings':total-risk,'excluded_by_severity':excluded,
        'exclusions_deferred':config.enabled and not source_current,
        'not_assessed':(config.enabled and total>0 and risk==0 and total-risk>0) or (suppressed>0 and total==0) or (aliases>0 and total==0),
        'all_suppressed':suppressed>0 and total==0,
        'all_consolidated_aliases':aliases>0 and total==0,
        'mitigated_treatment':'full_risk_until_residual_policy_approved'}
    if capture_basis:
        # Keep saved context bounded even when many findings are verified.
        # Full decisions remain in the finding's retained evidence ledger.
        rows = db.execute(select(Finding.id, FindingVerification.id, FindingVerification.version,
            FindingVerification.source_reference, FindingVerification.observed_at,
            FindingVerification.created_at, FindingVerification.expires_at, FindingVerification.attestation['group_context'])
            .join(FindingVerification, and_(FindingVerification.finding_id==Finding.id,
                FindingVerification.org_id==Finding.org_id,
                FindingVerification.version==Finding.risk_verification_version))
            .where(Finding.org_id==org_id, Finding.active(), eligible_exclusion(instant), *filters)
            .order_by(Finding.id).limit(100)).all() if config.enabled and source_current and total>risk else []
        metadata['verification_basis'] = [dict(finding_id=str(row[0]), decision_id=str(row[1]), version=row[2],
            source_reference=row[3], observed_at=row[4].isoformat(), reviewed_at=row[5].isoformat(),
            expires_at=row[6].isoformat(), **({'group_context':row[7]} if row[7] else {})) for row in rows]
        metadata['verification_basis_truncated'] = total-risk>len(rows)
        metadata['verification_basis_limit'] = 100
        from app.models.finding_suppression import FindingSuppression
        hidden = db.execute(select(Finding.id, FindingSuppression.id, FindingSuppression.version)
            .join(FindingSuppression, and_(FindingSuppression.id == Finding.suppression_id,
                FindingSuppression.org_id == Finding.org_id)).where(Finding.org_id == org_id,
                Finding.archived_at.is_(None), *filters).order_by(Finding.id).limit(100)).all() if suppressed else []
        from app.models.finding_consolidation import FindingConsolidation
        groups = db.execute(select(FindingConsolidation.id,FindingConsolidation.version,
            FindingConsolidation.canonical_finding_id,Finding.id).join(Finding,
                and_(Finding.consolidation_alias_id==FindingConsolidation.id,Finding.org_id==FindingConsolidation.org_id))
            .where(Finding.org_id==org_id,Finding.archived_at.is_(None),*filters).order_by(Finding.id).limit(100)).all() if aliases else []
        metadata['consolidation_policy_version']='reviewed-pair-visibility-v1'
        metadata['consolidation_basis']=[dict(group_id=str(r[0]),version=r[1],canonical_finding_id=str(r[2]),alias_finding_id=str(r[3])) for r in groups]
        metadata['consolidation_basis_truncated']=aliases>len(groups)
        metadata['suppression_policy_version'] = 'reviewed-suppression-v1'
        metadata['suppression_basis'] = [dict(finding_id=str(r[0]), suppression_id=str(r[1]), version=r[2]) for r in hidden]
        metadata['suppression_basis_truncated'] = suppressed > len(hidden)
    return adjusted,metadata


def _reference(db,org_id,reference,*,lock=False):
    if reference.startswith('document:'):
        try:identifier=uuid.UUID(reference.removeprefix('document:'))
        except ValueError:raise HTTPException(422,'Use document:<version UUID> or an HTTPS evidence reference') from None
        query=select(KnowledgeVersion).join(KnowledgeDocument).where(KnowledgeVersion.id==identifier,
            KnowledgeDocument.org_id==org_id,KnowledgeVersion.current.is_(True),
            KnowledgeVersion.retired_at.is_(None),KnowledgeVersion.purged_at.is_(None))
        if lock:query=query.with_for_update(read=True,of=KnowledgeVersion)
        version=db.scalar(query.execution_options(populate_existing=True))
        if version is None:raise HTTPException(422,'Evidence document version must be current and available in this organization')
        return 'document',version.id,version.content_hash
    try:
        parsed=urlsplit(reference)
        valid=parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password
    except ValueError:valid=False
    if not valid:raise HTTPException(422,'Use an HTTPS reference without credentials, or document:<version UUID>')
    # Never fetch user-provided URLs. The authorized reviewer attests access.
    return 'reference',None,None


def _finding(db,org_id,finding_id,*,lock=False):
    query=select(Finding).options(defer(Finding.raw_data),defer(Finding.description),defer(Finding.details)).where(
        Finding.org_id==org_id,Finding.id==finding_id,Finding.active())
    if lock:query=query.with_for_update(key_share=True)
    finding=db.scalar(query.execution_options(populate_existing=True))
    if finding is None:raise HTTPException(404,'Finding not found')
    return finding


def read_verification(db,org_id,finding_id,member,*,before=None,limit=20):
    finding=_finding(db,org_id,finding_id)
    query=select(FindingVerification).where(FindingVerification.org_id==org_id,FindingVerification.finding_id==finding_id)
    if before is not None:query=query.where(FindingVerification.version<before)
    records=db.scalars(query.order_by(FindingVerification.version.desc()).limit(limit)).all()
    eligible=bool(db.scalar(select(eligible_exclusion()).where(Finding.id==finding_id,Finding.org_id==org_id)))
    latest=db.scalar(select(FindingVerification).where(FindingVerification.finding_id==finding_id,
        FindingVerification.org_id==org_id).order_by(FindingVerification.version.desc()).limit(1))
    group_scope=None
    if finding.consolidation_id:
        from app.models.finding_consolidation import FindingConsolidation
        root=db.scalar(select(FindingConsolidation).where(FindingConsolidation.org_id==org_id,FindingConsolidation.id==finding.consolidation_id))
        if root:
            ids=(root.finding_a_id,root.finding_b_id)
            observed=db.scalars(select(FindingObservation.id).where(FindingObservation.org_id==org_id,
                FindingObservation.finding_id.in_(ids)).limit(1001)).all()
            group_scope=dict(group_id=str(root.id),version=root.version,member_ids=[str(v) for v in ids],
                observation_count=len(observed),bounded=len(observed)<=1000)
    return dict(group_scope=group_scope,version=finding.risk_verification_version,workflow_version=finding.workflow_version,
        workflow_status=finding.workflow_status,state=finding.risk_verification_state,
        eligible_for_exclusion=eligible,policy=configuration(db,org_id).model_dump(),
        can_review=member.role in REVIEW_ROLES,
        self_review_required=bool(latest and latest.submitter_id==member.user_id),
        records=[{key:getattr(row,key) for key in ('id','version','workflow_version','workflow_status','state',
            'source_reference','source_sha256','observed_at','source_observation_count','submitter_label','actor_label',
            'note','created_at','expires_at','attestation')} for row in records])


def _write_verification(db,org_id,finding_id,member,payload,*,review=False):
    lock_org_jobs(db,org_id)
    group_id=db.scalar(select(Finding.consolidation_id).where(Finding.org_id==org_id,Finding.id==finding_id))
    if group_id:
        from app.services.org_lock import lock_org
        def busy():
            raise HTTPException(409,'Inventory publication is busy; retry scoring review after the current batch')
        lock_org(db,org_id,on_wait=busy)
    try:require_active_org(db,org_id,lock=True)
    except KnowledgeError as error:raise HTTPException(409,str(error)) from error
    current=db.scalar(select(OrgMembership).where(OrgMembership.org_id==org_id,OrgMembership.user_id==member.user_id)
        .with_for_update().execution_options(populate_existing=True))
    roles=REVIEW_ROLES if review else (UserRole.admin,UserRole.auditor)
    if current is None or current.role not in roles:raise HTTPException(403,'Insufficient verification permissions')
    finding=_finding(db,org_id,finding_id,lock=True)
    if payload.expected_version!=finding.risk_verification_version or payload.expected_workflow_version!=finding.workflow_version:
        raise HTTPException(409,'Finding or verification changed; reload before retrying')
    affected=[value for value in (finding.id,finding.asset_id,finding.scan_id) if value]
    affected_batches=select(ArchiveBatch.id).where(ArchiveBatch.org_id==org_id,ArchiveBatch.item_id.in_(affected),
        ArchiveBatch.state.in_((ArchiveState.archiving,ArchiveState.restoring,ArchiveState.purging)))
    if review and payload.decision=='revoked':
        # Failed batches retain their recovery state. Explicit revocation only
        # removes scoring authority and must remain possible before group undo.
        # A genuinely queued/running job still blocks this operation.
        affected_batches=affected_batches.where(exists(select(ArchiveJob.id).where(
            ArchiveJob.org_id==org_id,ArchiveJob.batch_id==ArchiveBatch.id,
            ArchiveJob.status.in_(('pending','running')))))
    if db.scalar(affected_batches.limit(1)):
        raise HTTPException(409,'An affected item is being archived, restored or purged')
    instant=now()
    actor=db.scalar(select(User).where(User.id==current.user_id).with_for_update(read=True,nowait=True).execution_options(populate_existing=True))
    if actor is None or not actor.is_active or actor.must_change_password:
        raise HTTPException(403,'An active organization reviewer account is required')
    count=db.scalar(select(observation_count()).select_from(Finding).where(Finding.id==finding.id,Finding.org_id==org_id))
    latest=db.scalar(select(FindingVerification).where(FindingVerification.org_id==org_id,
        FindingVerification.finding_id==finding_id).order_by(FindingVerification.version.desc()).limit(1))
    from app.services.consolidation_proof import capture as group_proof
    group_context=group_proof(db,org_id,finding) if not review or payload.decision=='approved' else None
    if review:
        if latest is None:raise HTTPException(409,'Submit evidence before reviewing it')
        if payload.decision=='revoked':
            if latest.state!='approved':raise HTTPException(409,'Only an approved decision can be revoked')
        elif latest.state!='pending':raise HTTPException(409,'Submit new evidence before a new review')
        if payload.decision=='approved':
            if latest.attestation.get('group_context')!=group_context:
                raise HTTPException(409,'Consolidated evidence context changed; submit current evidence again')
            changed=db.scalar(select(FindingHistory.id).where(FindingHistory.org_id==org_id,
                FindingHistory.finding_id==finding_id,FindingHistory.version>latest.workflow_version,
                FindingHistory.before['status'].astext.is_distinct_from(FindingHistory.after['status'].astext)).limit(1))
            if changed or latest.workflow_status!=finding.workflow_status or count!=latest.source_observation_count:
                raise HTTPException(409,'Workflow or source observations changed; submit current evidence again')
            if not payload.evidence_reviewed:raise HTTPException(422,'Confirm that you reviewed the evidence')
            if latest.submitter_id==current.user_id and not payload.self_review_acknowledged:
                raise HTTPException(422,'Explicitly acknowledge review of your own submitted evidence')
            if not payload.expires_at or not instant<payload.expires_at<=min(instant+MAX_VALIDITY,latest.observed_at+MAX_VALIDITY):
                raise HTTPException(422,'Approval needs a future expiry within 90 days of observation and review')
        reference,observed,source_hash=latest.source_reference,latest.observed_at,latest.source_sha256
        submitter_id,submitter_label=latest.submitter_id,latest.submitter_label
        state=payload.decision
        kind,document_id,checked_hash=_reference(db,org_id,reference,lock=True) if state=='approved' else (None,None,None)
        if state=='approved' and source_hash!=checked_hash:raise HTTPException(409,'Evidence source changed; submit it again')
        attestation=dict(evidence_reviewed=payload.evidence_reviewed,self_review=submitter_id==current.user_id,
            self_review_acknowledged=payload.self_review_acknowledged)
        expires=payload.expires_at if state=='approved' else None
    else:
        if finding.consolidation_id and finding.risk_verification_state=='approved':
            raise HTTPException(409,'Explicitly revoke the current group approval before submitting replacement evidence')
        if finding.workflow_status not in ('resolved','false_positive','mitigated'):
            raise HTTPException(422,'Evidence review applies to Resolved, False positive or Mitigated findings')
        if not instant-MAX_VALIDITY<=payload.observed_at<=instant:raise HTTPException(422,'Evidence observation must be within the last 90 days and not in the future')
        reference,observed=payload.source_reference,payload.observed_at
        kind,document_id,source_hash=_reference(db,org_id,reference,lock=True)
        submitter_id,submitter_label=current.user_id,actor_label(actor)
        state,attestation,expires='pending',{},None
    scope=group_context if not review else latest.attestation.get('group_context')
    if scope is not None:
        attestation['group_context']=scope
    finding.risk_verification_version+=1
    finding.risk_verification_state=state
    finding.risk_verified_workflow_version=finding.workflow_version if state=='approved' else None
    finding.risk_verified_at=instant if state=='approved' else None
    finding.risk_verification_expires_at=expires
    finding.risk_verified_observation_count=count if state=='approved' else None
    finding.risk_verification_source_kind=kind if state=='approved' else None
    finding.risk_verification_document_id=document_id if state=='approved' else None
    finding.risk_verification_source_hash=source_hash if state=='approved' else None
    row=FindingVerification(org_id=org_id,finding_id=finding.id,version=finding.risk_verification_version,
        workflow_version=finding.workflow_version,workflow_status=finding.workflow_status,state=state,
        source_reference=reference,source_sha256=source_hash,observed_at=observed,source_observation_count=count,
        submitter_id=submitter_id,submitter_label=submitter_label[:255],actor_id=current.user_id,
        actor_label=actor_label(actor)[:255],note=payload.note,created_at=instant,expires_at=expires,attestation=attestation)
    db.add(row)
    record_event(db,'finding_verification_changed',org_id=org_id,actor=actor,item=str(finding.id),
        details=dict(finding_id=str(finding.id),state=state,version=finding.risk_verification_version))
    db.commit()
    return read_verification(db,org_id,finding_id,current)


def write_verification(db,org_id,finding_id,member,payload,*,review=False):
    from sqlalchemy.exc import DBAPIError
    try:
        return _write_verification(db,org_id,finding_id,member,payload,review=review)
    except DBAPIError as error:
        if getattr(error.orig,'sqlstate',None) in ('55P03','23505','23503'):
            db.rollback()
            raise HTTPException(409,'Scoring evidence or reviewer context is busy or changed; reload before retrying') from error
        raise
