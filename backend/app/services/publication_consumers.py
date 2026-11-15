"""Private consumer integration; no HTTP writer, commit, or core-receipt upgrade."""
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.models.observation_publication import OrganizationPublicationRevision, ObservationPublicationState
from app.services import publication_transactions as core
from app.services.consolidation_visibility import _invalidate

CONTRACT = 'observation-publication-consumers-v1'


def revision(db, org_id):
    return db.scalar(select(OrganizationPublicationRevision.revision).where(
        OrganizationPublicationRevision.org_id == org_id)) or 0


def context(db, org_id, finding_id):
    # Retain the generation after Undo: field equality cannot revive old proof.
    row = db.get(ObservationPublicationState, (org_id, finding_id), populate_existing=True)
    if row is None:
        from app.models.observation_publication import ObservationPublicationDecision
        if db.scalar(select(ObservationPublicationDecision.id).where(
                ObservationPublicationDecision.org_id == org_id,
                ObservationPublicationDecision.finding_id == finding_id).limit(1)):
            raise HTTPException(409, 'Retained publication history requires generation recovery')
        return None
    from app.models.observation_publication import ObservationPublicationDecision
    receipt = db.get(ObservationPublicationDecision, row.decision_id, populate_existing=True)
    if (receipt is None or receipt.org_id != org_id or receipt.finding_id != finding_id
            or receipt.version != row.version or receipt.source_context_hash is None
            or receipt.mapping_version != core.payload_contract.MAPPING_VERSION
            or receipt.admission_contract not in (CONTRACT, core.CONTRACT)
            or receipt.operation != ('publish' if row.state == 'active' else 'undo')):
        raise HTTPException(409, 'Retained publication context requires recovery')
    return dict(version=row.version, decision_id=str(row.decision_id), state=row.state)


def _preview(db, org_id, actor_id, finding_id, observation_id=None):
    return core._preview(db, org_id, actor_id, finding_id, observation_id, admission_contract=CONTRACT)


def _stage(db, org_id, actor_id, finding_id, request, observation_id=None):
    core._clean(db)
    try:
        with db.begin_nested(), core._bounded_lock_wait(db):
            result = core._stage(db, org_id, actor_id, finding_id, request, observation_id,
                admission_contract=CONTRACT)
            if not result['replayed'] and not result['no_op']:
                _invalidate(db, org_id, revision_model=OrganizationPublicationRevision)
            return result
    except DBAPIError as error:
        if getattr(error.orig, 'sqlstate', None) in ('55P03','23505','23503','23514','40001','40P01'):
            raise HTTPException(409, 'Consumer publication is busy; reload before retrying') from error
        raise
