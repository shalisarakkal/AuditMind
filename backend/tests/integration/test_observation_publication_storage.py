"""Reserved storage retention/integrity; does not exercise an enabled writer."""
import uuid

import pytest
from sqlalchemy import delete, func, select, update, text
from sqlalchemy.exc import IntegrityError

from app.models.organization import Organization
from app.models.scan import Scan
from app.models.finding import Finding
from app.models.observation_publication import ObservationPublicationDecision as Decision, ObservationPublicationSnapshot as Snapshot, ObservationPublicationState as State
from app.models.observation_publication import ObservationPublicationDependency as Dependency
from tests.conftest import requires_db
from tests.integration.test_observation_publication import native_preview

pytestmark = requires_db


def receipt(db, n, **changes):
    data = dict(org_id=n['org'], finding_id=n['finding_id'], observation_id=n['observation_id'],
        source_scan_id=n['scan_id'], request_id=uuid.uuid4(), request_hash='a'*64,
        before_hash='b'*64, after_hash='c'*64, mapping_version='nessus-observation-payload-v1',
        version=1, operation='publish', rationale='Explicit synthetic review', actor_label='Test admin')
    row = Decision(**(data | changes)); db.add(row); db.flush(); return row


def retained(db, n):
    row = receipt(db, n)
    for side, scan in [('before',n['original_scan_id']), ('after',n['scan_id'])]:
        db.add(Snapshot(org_id=n['org'], decision_id=row.id, finding_id=n['finding_id'],
            source_scan_id=scan, side=side, payload={'severity': 'medium' if side=='before' else 'critical'}))
    db.add(State(org_id=n['org'], finding_id=n['finding_id'], decision_id=row.id, version=1, state='active'))
    db.add(Dependency(org_id=n['org'], decision_id=row.id, resource_kind='scan', resource_id=n['scan_id']))
    db.commit(); return row.id


@pytest.mark.parametrize('owner', ['scan', 'finding', 'organization'])
def test_full_payload_is_source_owned_but_minimal_receipt_survives_source_purge(db_session,native_preview,owner):
    n=native_preview; retained(db_session,n)
    target = {'scan': (Scan,n['scan_id']), 'finding': (Finding,n['finding_id']), 'organization': (Organization,n['org'])}[owner]
    db_session.execute(delete(target[0]).where(target[0].id==target[1]));db_session.commit()
    count=lambda model:db_session.scalar(select(func.count()).select_from(model))
    assert count(Snapshot)==(1 if owner=='scan' else 0)
    assert count(Decision)==(0 if owner=='organization' else 1)
    assert count(State)==(0 if owner=='organization' else 1)
    assert count(Dependency)==(0 if owner=='organization' else 1)


@pytest.mark.parametrize('violation', ['version','request','state_version','state_target','snapshot_target','side','blank_rationale','operation','payload'])
def test_storage_rejects_duplicate_and_mismatched_generations(db_session,native_preview,violation):
    n=native_preview;decision=retained(db_session,n)
    other=None
    if violation=='snapshot_target':
        # A real same-tenant finding isolates the receipt/target FK from the
        # separate live-owner guard and the ordinary finding existence FK.
        other=Finding(org_id=n['org'],domain='vulnerability_management',severity='low',source='nessus')
        db_session.add(other);db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        if violation=='version':receipt(db_session,n)
        elif violation=='request':
            request=db_session.get(Decision,decision).request_id
            receipt(db_session,n,version=2,request_id=request)
        elif violation in ('blank_rationale','operation'):
            receipt(db_session,n,version=2,**({'rationale':'   '} if violation=='blank_rationale' else {'operation':'merge'}))
        elif violation.startswith('state_'):
            db_session.execute(delete(State));db_session.flush()
            db_session.add(State(org_id=n['org'],finding_id=n['finding_id'] if violation=='state_version' else uuid.uuid4(),
                decision_id=decision,version=2 if violation=='state_version' else 1,state='active'))
        else:
            db_session.add(Snapshot(org_id=n['org'],decision_id=decision,
                finding_id=other.id if violation=='snapshot_target' else n['finding_id'],
                source_scan_id=n['scan_id'],side='wrong' if violation=='side' else 'after',
                payload=[] if violation=='payload' else {}))
        db_session.flush()


def test_downgrade_refuses_retained_receipts_even_after_undo(db_session,native_preview,monkeypatch):
    import importlib.util
    from pathlib import Path
    n=native_preview
    receipt(db_session,n,operation='undo');db_session.commit()
    path=Path(__file__).resolve().parents[2]/'alembic/versions/0056_observation_publication_storage.py'
    spec=importlib.util.spec_from_file_location('publication_storage_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    monkeypatch.setattr(migration.op,'get_bind',lambda:db_session.connection())
    with pytest.raises(RuntimeError,match='retained publication receipts'):
        migration.downgrade()
    assert db_session.scalar(select(func.count()).select_from(Decision))==1


@pytest.mark.parametrize('foreign_owner', ['scan','finding','update_scan'])
def test_snapshot_rejects_cross_tenant_live_owners(db_session,native_preview,foreign_owner):
    n=native_preview
    other=Organization(name='Separate snapshot tenant');db_session.add(other);db_session.flush()
    scan=Scan(org_id=other.id,scan_type='nessus',status='completed')
    finding=Finding(org_id=other.id,domain='vulnerability_management',severity='low',source='nessus')
    db_session.add_all([scan,finding]);db_session.flush()
    row=receipt(db_session,n,**({'finding_id':finding.id} if foreign_owner=='finding' else {}))
    snapshot=Snapshot(org_id=n['org'],decision_id=row.id,
        finding_id=finding.id if foreign_owner=='finding' else n['finding_id'],
        source_scan_id=scan.id if foreign_owner=='scan' else n['scan_id'],
        side='after',payload={})
    if foreign_owner=='update_scan':
        db_session.add(snapshot);db_session.flush()
    with pytest.raises(IntegrityError),db_session.begin_nested():
        if foreign_owner=='update_scan':
            db_session.execute(update(Snapshot).where(Snapshot.id==snapshot.id).values(source_scan_id=scan.id))
        else:
            db_session.add(snapshot);db_session.flush()


def test_actor_deletion_preserves_receipt_label(db_session,native_preview):
    from app.models.user import User
    from app.models.membership import OrgMembership
    n=native_preview
    actor=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org']))
    row=receipt(db_session,n,actor_id=actor);identifier=row.id;db_session.commit()
    db_session.execute(delete(User).where(User.id==actor));db_session.commit();db_session.expire_all()
    saved=db_session.get(Decision,identifier)
    assert saved.actor_id is None and saved.actor_label=='Test admin'


def test_dependency_probe_uses_targeted_index_with_large_retained_history(db_session,native_preview):
    n=native_preview;identifier=retained(db_session,n)
    db_session.execute(text('''INSERT INTO observation_publication_dependencies
        (id,org_id,decision_id,resource_kind,resource_id)
        SELECT gen_random_uuid(),:org,:decision,'scan',gen_random_uuid()
        FROM generate_series(1,100000)'''),dict(org=n['org'],decision=identifier))
    db_session.commit()
    db_session.execute(text('ANALYZE observation_publication_dependencies'))
    plan=db_session.scalar(text('''EXPLAIN (ANALYZE,FORMAT JSON)
        SELECT 1 FROM observation_publication_dependencies d
        JOIN observation_publication_states s ON s.org_id=d.org_id AND s.decision_id=d.decision_id
        WHERE d.org_id=:org AND d.resource_kind='scan' AND d.resource_id=:scan
        AND s.state='active' LIMIT 1'''),dict(org=n['org'],scan=n['scan_id']))[0]
    def walk(node):
        yield node
        for child in node.get('Plans',[]):yield from walk(child)
    assert any(node.get('Index Name')=='ix_publication_dependency_resource' for node in walk(plan['Plan']))
    assert not any(node.get('Node Type')=='Seq Scan' and node.get('Relation Name')=='observation_publication_dependencies'
        for node in walk(plan['Plan']))
    print('PUBLICATION_DEPENDENCY_PROBE_MS='+str(plan['Execution Time']))
