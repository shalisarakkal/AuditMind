"""Exercise private metadata staging only; production publication stays disabled."""
import time
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.orm import Session

from app.models.archive import ArchiveBatch, ArchiveJob
from app.models.event import Event
from app.models.finding import Finding
from app.models.finding_consolidation import (FindingConsolidation, FindingConsolidationDecision,
    FindingConsolidationMember, FindingConsolidationDependency)
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services import consolidation_transactions as transactions
from app.services.org_lock import _key
from tests.conftest import requires_db
from tests.helpers import upload, member, register, first_org_id
from tests.integration.test_finding_consolidation_foundation import native, group
from tests.integration.test_scan_snapshots import _bind_observation, _nessus

pytestmark = requires_db
MODELS = (FindingConsolidation, FindingConsolidationDecision, FindingConsolidationMember, FindingConsolidationDependency)


def actor(db, n):
    return db.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == uuid.UUID(n['org'])))


def request(db, n):
    actor_id = actor(db, n)
    plan = transactions.metadata_preview(db, uuid.UUID(n['org']), actor_id, uuid.UUID(n['decision']))
    payload = transactions.MetadataRequest(canonical_decision_id=n['decision'], request_id=uuid.uuid4(),
        expected_version=plan['expected_version'], review_token=plan['review_token'],
        rationale='Explicit synthetic metadata review', confirm=True)
    db.commit()
    return actor_id, payload


def stage(db, n, who, payload):
    return transactions._stage_metadata(db, uuid.UUID(n['org']), who, payload)


def counts(db):
    return [db.scalar(select(func.count()).select_from(model)) for model in MODELS]


def test_stage_is_atomic_caller_owned_and_does_not_publish_visibility(db_session, native):
    n = native
    who, payload = request(db_session, n)
    events = db_session.scalar(select(func.count()).select_from(Event))
    result = stage(db_session, n, who, payload)
    assert result['version'] == 1 and not result['replayed'] and not result['apply_available']
    assert counts(db_session) == [1, 1, 2, 12]
    with Session(db_session.get_bind()) as outsider:
        assert counts(outsider) == [0, 0, 0, 0]  # No implicit commit.
    assert db_session.scalar(select(func.count()).select_from(Finding).where(Finding.active())) == 2
    assert db_session.scalar(select(func.count()).select_from(Event)) == events
    assert all(row.workflow_version == 0 and row.workflow_status == 'open'
        for row in db_session.scalars(select(Finding)))
    db_session.rollback()
    assert counts(db_session) == [0, 0, 0, 0]


def test_failure_mid_append_rolls_back_every_table_and_leaves_session_usable(db_session, native):
    who, payload = request(db_session, native)
    def interrupt(conn, cursor, statement, parameters, context, many):
        if statement.startswith('INSERT INTO finding_consolidation_dependencies'):
            raise RuntimeError('Synthetic interruption after receipt/member writes')
    event.listen(db_session.get_bind(), 'before_cursor_execute', interrupt)
    try:
        with pytest.raises(RuntimeError, match='Synthetic interruption'):
            stage(db_session, native, who, payload)
    finally:
        event.remove(db_session.get_bind(), 'before_cursor_execute', interrupt)
    assert counts(db_session) == [0, 0, 0, 0]
    assert db_session.scalar(text('SELECT 1')) == 1
    assert stage(db_session, native, who, payload)['version'] == 1


def test_identical_retry_returns_receipt_but_changed_reuse_conflicts(db_session, native):
    who, payload = request(db_session, native)
    first = stage(db_session, native, who, payload)
    db_session.commit()
    # Exact authorized retries do not re-run now-stale admission against the
    # already-active group or append a second generation.
    replay = stage(db_session, native, who, payload)
    assert replay == {**first, 'replayed': True}
    db_session.commit()
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, who, payload.model_copy(update={'rationale':'Different operation'}))
    assert caught.value.status_code == 409
    assert counts(db_session) == [1, 1, 2, 12]


def test_staged_winner_fences_second_connection_then_replays_after_commit(db_session, native):
    who, payload = request(db_session, native)
    with Session(db_session.get_bind()) as winner:
        original = stage(winner, native, who, payload)
        with pytest.raises(HTTPException) as caught:
            stage(db_session, native, who, payload)
        assert caught.value.status_code == 409
        winner.commit()
    replay = stage(db_session, native, who, payload)
    assert replay == {**original, 'replayed':True}
    assert counts(db_session) == [1, 1, 2, 12]


def test_new_generation_retains_old_dependency_history_after_simulated_undo(db_session, native):
    who, payload = request(db_session, native)
    first = stage(db_session, native, who, payload)
    db_session.commit()
    # Undo publication is a later integration step. Seed its proper ledger shape
    # here to exercise re-admission without exposing an undo production action.
    root = db_session.get(FindingConsolidation, uuid.UUID(first['consolidation_id']))
    root.state, root.version = 'undone', 2
    db_session.execute(delete(FindingConsolidationMember).where(FindingConsolidationMember.consolidation_id == root.id))
    db_session.add(FindingConsolidationDecision(org_id=root.org_id, consolidation_id=root.id,
        request_id=uuid.uuid4(), request_hash='a'*64, version=2, state='undone', rationale='Synthetic undo fixture',
        context={}, actor_id=who, actor_label='Synthetic admin'))
    db_session.commit()
    who, again = request(db_session, native)
    assert again.expected_version == 2
    assert stage(db_session, native, who, again)['version'] == 3
    assert counts(db_session) == [1, 3, 2, 24]
    assert {row.generation for row in db_session.scalars(select(FindingConsolidationDependency))} == {1, 3}
    assert {row.generation for row in db_session.scalars(select(FindingConsolidationMember))} == {3}


@pytest.mark.parametrize('kind', ['viewer', 'platform_only'])
def test_actual_org_admin_is_required_even_for_exact_retry(client, db_session, native, kind):
    who, payload = request(db_session, native)
    stage(db_session, native, who, payload); db_session.commit()
    if kind == 'viewer':
        db_session.execute(update(OrgMembership).where(OrgMembership.org_id == uuid.UUID(native['org']),
            OrgMembership.user_id == who).values(role='viewer'))
    else:
        db_session.execute(delete(OrgMembership).where(OrgMembership.org_id == uuid.UUID(native['org']),
            OrgMembership.user_id == who))
        db_session.execute(update(User).where(User.id == who).values(is_sysadmin=True))
    db_session.commit()
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, who, payload)
    assert caught.value.status_code == 403
    assert counts(db_session) == [1, 1, 2, 12]


def test_foreign_tenant_and_diagnostic_token_cannot_stage(client, db_session, native):
    who, payload = request(db_session, native)
    diagnostic = client.post(native['root']+'/preview', headers=native['headers'],
        json={'canonical_decision_id':native['decision']}).json()['snapshot_fingerprint']
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, who, payload.model_copy(update={'review_token':diagnostic}))
    assert caught.value.status_code == 409
    db_session.rollback()
    outsider = register(client, 'metadata-outsider@example.io')
    foreign_org = uuid.UUID(first_org_id(client, outsider))
    foreign_actor = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == foreign_org))
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, foreign_actor, payload)
    assert caught.value.status_code == 403
    with pytest.raises(HTTPException) as caught:
        transactions._stage_metadata(db_session, foreign_org, foreign_actor, payload)
    assert caught.value.status_code == 404
    assert counts(db_session) == [0, 0, 0, 0]


def test_review_token_is_not_transferable_between_two_actual_admins(client, db_session, native):
    first_actor, payload = request(db_session, native)
    member(client, native['headers'], native['org'], 'admin')
    second_actor = db_session.scalar(select(OrgMembership.user_id).where(
        OrgMembership.org_id == uuid.UUID(native['org']), OrgMembership.user_id != first_actor))
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, second_actor, payload)
    assert caught.value.status_code == 409
    assert counts(db_session) == [0, 0, 0, 0]


@pytest.mark.parametrize('change', ['role', 'inactive', 'password_reset', 'org_archive', 'workflow', 'wrong_version', 'no_confirmation'])
def test_stale_or_unauthorized_admission_never_writes(db_session, native, change):
    who, payload = request(db_session, native)
    with Session(db_session.get_bind()) as other:
        if change == 'role':
            other.execute(update(OrgMembership).where(OrgMembership.org_id == uuid.UUID(native['org']),
                OrgMembership.user_id == who).values(role='viewer'))
        elif change == 'inactive': other.execute(update(User).where(User.id == who).values(is_active=False))
        elif change == 'password_reset': other.execute(update(User).where(User.id == who).values(must_change_password=True))
        elif change == 'org_archive':
            other.execute(update(Organization).where(Organization.id == uuid.UUID(native['org'])).values(archived_at=func.now()))
        elif change == 'workflow':
            other.execute(update(Finding).where(Finding.id == native['source'].finding_id).values(workflow_version=1))
        other.commit()
    if change == 'wrong_version': payload = payload.model_copy(update={'expected_version':1})
    if change == 'no_confirmation': payload = payload.model_copy(update={'confirm':False})
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, who, payload)
    assert caught.value.status_code in (403, 409, 422)
    assert counts(db_session) == [0, 0, 0, 0]


@pytest.mark.parametrize('kind', ['job', 'publication', 'finding'])
def test_busy_admission_is_try_only_and_preserves_other_session(db_session, native, kind):
    who, payload = request(db_session, native)
    org_id = uuid.UUID(native['org'])
    with Session(db_session.get_bind()) as holder:
        if kind == 'job': holder.execute(select(func.pg_advisory_xact_lock(1, int.from_bytes(org_id.bytes[:4], 'big', signed=True))))
        elif kind == 'publication': holder.execute(select(func.pg_advisory_xact_lock(_key(org_id))))
        else: holder.execute(select(Finding.id).where(Finding.id == native['source'].finding_id).with_for_update())
        started = time.perf_counter()
        with pytest.raises(HTTPException) as caught:
            stage(db_session, native, who, payload)
        assert caught.value.status_code == 409 and time.perf_counter()-started < 2
        assert holder.scalar(text('SELECT 1')) == 1
    assert counts(db_session) == [0, 0, 0, 0]


def test_uncommitted_unique_conflict_is_bounded_and_restores_caller_timeout(db_session, native):
    who, payload = request(db_session, native)
    db_session.execute(text("SET LOCAL lock_timeout='3s'"))
    with Session(db_session.get_bind()) as holder:
        group(holder, native)  # Deliberately bypass admission to exercise the DB constraint fence.
        started = time.perf_counter()
        with pytest.raises(HTTPException) as caught:
            stage(db_session, native, who, payload)
        assert caught.value.status_code == 409 and time.perf_counter()-started < 2
    assert db_session.scalar(text("SELECT setting FROM pg_settings WHERE name='lock_timeout'")) == '3000'
    assert counts(db_session) == [0, 0, 0, 0]


def test_success_respects_and_restores_stricter_caller_timeout(db_session, native):
    who, payload = request(db_session, native)
    db_session.execute(text("SET LOCAL lock_timeout='100ms'"))
    assert stage(db_session, native, who, payload)['version'] == 1
    assert db_session.scalar(text("SELECT setting FROM pg_settings WHERE name='lock_timeout'")) == '100'


@pytest.mark.parametrize('kind', ['pending_import', 'pending_source_job'])
def test_pending_source_operations_block_before_staging(db_session, native, kind):
    who, payload = request(db_session, native)
    if kind == 'pending_import':
        # Another upload pending for this org, without altering the retained pair.
        source = db_session.get(Scan, native['source'].scan_id)
        row = Scan(org_id=source.org_id, filename='pending.csv', scan_type=source.scan_type, status='pending')
        db_session.add(row)
    else:
        batch = ArchiveBatch(org_id=uuid.UUID(native['org']), item_type='asset',
            item_id=uuid.UUID(native['asset']), label='Affected canonical asset', state='archived')
        db_session.add(batch); db_session.flush()
        db_session.add(ArchiveJob(org_id=batch.org_id, batch_id=batch.id, action='restore', status='pending'))
    db_session.commit()
    with pytest.raises(HTTPException) as caught:
        stage(db_session, native, who, payload)
    assert caught.value.status_code == 409
    assert counts(db_session) == [0, 0, 0, 0]


def test_independent_third_finding_blocks_matching_identity(client, db_session, native):
    who, payload = request(db_session, native)
    third = _nessus('1001').replace(b'pilot-host', b'third-alias').replace(b'10.0.0.10', b'10.0.0.55')
    imported = upload(client, native['base']+'/findings/import', native['headers'], 'third.nessus', third)
    assert imported.status_code == 201
    _bind_observation(client, (native['headers'], native['org']), db_session, imported.json()['scan_id'],
        native['tool'], native['asset'])
    with pytest.raises(HTTPException, match='Another independently'):
        stage(db_session, native, who, payload)
    assert counts(db_session) == [0, 0, 0, 0]


def test_revoked_third_identity_does_not_block_admission(client, db_session, native):
    who, payload = request(db_session, native)
    third = _nessus('1001').replace(b'pilot-host', b'old-alias').replace(b'10.0.0.10', b'10.0.0.66')
    imported = upload(client, native['base']+'/findings/import', native['headers'], 'old.nessus', third)
    observed, _ = _bind_observation(client, (native['headers'], native['org']), db_session,
        imported.json()['scan_id'], native['tool'], native['asset'])
    response = client.post(native['base']+f'/findings/{observed.finding_id}/observations/{observed.id}/identity-binding/revoke',
        headers=native['headers'], json=dict(expected_version=1, rationale='Explicit synthetic revocation'))
    assert response.status_code == 200, response.text
    assert stage(db_session, native, who, payload)['version'] == 1


def test_production_entry_and_routes_stay_closed(client, db_session, native):
    who, payload = request(db_session, native)
    with pytest.raises(HTTPException) as caught:
        transactions.publish(db_session, uuid.UUID(native['org']), who, payload)
    assert caught.value.status_code == 409
    for action in ('apply', 'publish', 'undo', 'decisions'):
        assert client.post(native['root']+'/'+action, headers=native['headers'], json=payload.model_dump(mode='json')).status_code == 404
    assert counts(db_session) == [0, 0, 0, 0]
