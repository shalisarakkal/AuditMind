"""Private visibility integration. Production publication remains closed.

Aliases retain their own UUID, source ownership, observations and workflow.
Materialized links keep hot partial-index queries free of per-row joins.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert

from app.models.finding import Finding
from app.models.finding_consolidation import (FindingConsolidation, FindingConsolidationDecision,
    FindingConsolidationMember, OrganizationConsolidationRevision)
from app.models.evidence_evaluation import OrganizationEvidenceRevision
from app.models.dashboard_snapshot import DashboardSnapshot
from app.services.consolidation_transactions import _stage_metadata, _bounded_lock_wait


def revision(db, org_id):
    return db.scalar(select(OrganizationConsolidationRevision.revision).where(
        OrganizationConsolidationRevision.org_id == org_id)) or 0


def _invalidate(db, org_id):
    # Finding UPDATE statement triggers invalidate list counts and seek cursors.
    # Explicit publication/evidence epochs also prevent old approvals returning
    # merely because undo restores the original physical inventory population.
    for model in (OrganizationConsolidationRevision, OrganizationEvidenceRevision):
        db.execute(insert(model).values(org_id=org_id, revision=1).on_conflict_do_update(
            index_elements=[model.org_id], set_={'revision': model.revision + 1}))
    from app.services.dashboard_snapshots import configuration
    if configuration(db).enabled:
        db.execute(insert(DashboardSnapshot).values(id=uuid.uuid4(), org_id=org_id,
            status='pending', requested_at=datetime.now(timezone.utc), retry_count=0)
            .on_conflict_do_update(index_elements=[DashboardSnapshot.org_id], set_={
                'payload':None, 'status':case((DashboardSnapshot.status == 'running','running'),else_='pending'),
                'requested_at':datetime.now(timezone.utc), 'error_message':None}))
    else:
        row = db.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id == org_id).with_for_update(nowait=True))
        if row:
            row.payload = None
    db.flush()


def _apply(db, org_id, result):
    """Caller already admitted/locked metadata in the same outer savepoint."""
    root = db.scalar(select(FindingConsolidation).where(FindingConsolidation.org_id == org_id,
        FindingConsolidation.id == uuid.UUID(result['consolidation_id'])).with_for_update(nowait=True))
    decision = db.scalar(select(FindingConsolidationDecision).where(FindingConsolidationDecision.org_id == org_id,
        FindingConsolidationDecision.id == uuid.UUID(result['decision_id'])))
    if root is None or decision is None or root.state != 'active' or decision.state != 'active' or (
            decision.consolidation_id != root.id or root.version != decision.version or root.version != result['version']):
        raise HTTPException(409, 'Current metadata generation is required for visibility')
    members = db.scalars(select(FindingConsolidationMember).where(FindingConsolidationMember.org_id == org_id,
        FindingConsolidationMember.consolidation_id == root.id)).all()
    expected = {root.canonical_finding_id:'canonical',
        next(value for value in (root.finding_a_id,root.finding_b_id) if value != root.canonical_finding_id):'alias'}
    if len(members) != 2 or {m.finding_id:m.role for m in members} != expected or any(m.generation != root.version for m in members):
        raise HTTPException(409, 'Exact current pair membership is required')
    findings = db.scalars(select(Finding).where(Finding.org_id == org_id, Finding.id.in_(expected))
        .order_by(Finding.id).with_for_update(key_share=True,nowait=True).execution_options(populate_existing=True)).all()
    if len(findings) != 2 or any(f.archived_at or f.suppression_id or f.consolidation_id or
            f.consolidation_alias_id or f.risk_verification_state == 'approved' for f in findings):
        raise HTTPException(409, 'Findings changed before visibility publication')
    for finding in findings:
        finding.consolidation_id = finding.consolidation_history_id = root.id
        finding.consolidation_alias_id = root.id if expected[finding.id] == 'alias' else None
    decision.context = {**decision.context, "visibility_contract":"reviewed-pair-visibility-v1"}
    db.flush()
    _invalidate(db,org_id)


def _stage_with_visibility(db, org_id, actor_id, payload):
    """Private integration harness: no commit and no production entry point.

    Proof, lifecycle, policy and UI gates must still join before publish() opens.
    A metadata-only request cannot later be silently upgraded by replaying it.
    """
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, 'Complete pending ORM changes first')
    with db.begin_nested(), _bounded_lock_wait(db):
        result = _stage_metadata(db,org_id,actor_id,payload)
        if result['replayed']:
            # The original receipt is returned without repeating effects. This
            # includes after a later undo; a retry must not re-hide the alias.
            original = db.scalar(select(FindingConsolidationDecision).where(
                FindingConsolidationDecision.org_id == org_id,
                FindingConsolidationDecision.id == uuid.UUID(result['decision_id'])))
            if original.context.get('visibility_contract') != 'reviewed-pair-visibility-v1':
                raise HTTPException(409, 'A metadata-only receipt cannot be upgraded by replay')
            return result
        _apply(db,org_id,result)
        return result


def _clear_after_undo(db, org_id, group_id, version):
    """Private undo integration, only after a caller stages a valid undo receipt.

    This is not authorized undo admission. No route or production caller exists.
    The caller must flush its undo metadata inside its own outer savepoint first.
    """
    if db.new or db.dirty or db.deleted:
        raise HTTPException(409, "Flush staged undo metadata inside the outer transaction first")
    with db.begin_nested(), _bounded_lock_wait(db):
        root = db.scalar(select(FindingConsolidation).where(FindingConsolidation.org_id == org_id,
            FindingConsolidation.id == group_id).with_for_update(nowait=True))
        receipt = db.scalar(select(FindingConsolidationDecision).where(FindingConsolidationDecision.org_id == org_id,
            FindingConsolidationDecision.consolidation_id == group_id, FindingConsolidationDecision.version == version,
            FindingConsolidationDecision.state == 'undone'))
        if root is None or root.state != 'undone' or root.version != version or receipt is None:
            raise HTTPException(409, 'An exact staged undo generation is required')
        if db.scalar(select(FindingConsolidationMember.id).where(FindingConsolidationMember.org_id == org_id,
                FindingConsolidationMember.consolidation_id == group_id).limit(1)):
            raise HTTPException(409, 'Undo must remove current membership first')
        findings = db.scalars(select(Finding).where(Finding.org_id == org_id,
            Finding.id.in_((root.finding_a_id,root.finding_b_id))).order_by(Finding.id)
            .with_for_update(key_share=True,nowait=True).execution_options(populate_existing=True)).all()
        if len(findings) != 2 or any(f.consolidation_id != group_id or f.risk_verification_state == 'approved' for f in findings):
            raise HTTPException(409, 'Retained pair and explicit proof revocation are required before undo')
        for finding in findings:
            finding.consolidation_id = finding.consolidation_alias_id = None
        db.flush()
        _invalidate(db,org_id)
