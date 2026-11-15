"""Read-only bounded provenance: no publication authority and no payload reads."""
import uuid
import pytest
from sqlalchemy import select, func, text, delete, event
from app.models.finding import Finding
from app.models.event import Event
from app.models.observation_publication import ObservationPublicationDecision as Decision, ObservationPublicationState as State
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import member, register
from tests.integration.test_publication_consumers import enabled, native_preview, stage, request
from app.services import publication_read

pytestmark = requires_db


def url(n):return n['base']+f"/findings/{n['finding_id']}/publication-status"


def test_empty_read_is_lazy_metadata_and_never_writes(client,db_session,enabled):
    n=enabled;before=db_session.scalar(select(func.count()).select_from(Event));db_session.commit()
    response=client.get(url(n),headers=n['headers']);assert response.status_code==200,response.text
    data=response.json();assert data['status']=='not_published' and data['items']==[]
    assert not data['publish_available'] and not data['undo_available']
    assert response.headers['cache-control']=='no-store'
    assert db_session.scalar(select(func.count()).select_from(Event))==before


def test_current_retained_history_has_same_org_provenance_without_tokens_or_payloads(client,db_session,enabled):
    n=enabled;stage(db_session,n);db_session.commit()
    before=db_session.scalar(select(func.count()).select_from(Event));db_session.commit();statements=[]
    def track(conn,cursor,statement,*args):statements.append(statement.lower())
    engine=db_session.get_bind();event.listen(engine,'before_cursor_execute',track)
    try:response=client.get(url(n),headers=n['headers'])
    finally:event.remove(engine,'before_cursor_execute',track)
    assert response.status_code==200,response.text
    data=response.json();assert data['status']=='published' and not data['recovery']
    assert data['current']['version']==1 and data['current']['source']['id']==str(n['scan_id'])
    assert data['original_source']['id']==str(n['original_scan_id'])
    assert data['current']['snapshots']=={'before':str(n['original_scan_id']),'after':str(n['scan_id'])}
    assert all('payload' not in sql.split('from')[0] for sql in statements if 'from observation_publication_snapshots' in sql or 'from finding_observations' in sql)
    assert 'review_token' not in response.text and 'raw_data' not in response.text
    assert db_session.scalar(select(func.count()).select_from(Event))==before


@pytest.mark.parametrize('role',['viewer','auditor'])
def test_members_can_read_but_not_use_admin_preview(client,db_session,enabled,role):
    n=enabled;headers=member(client,n['headers'],str(n['org']),role)
    assert client.get(url(n),headers=headers).status_code==200
    assert client.post(n['path'],headers=headers,json={}).status_code==403


def test_cross_tenant_and_missing_findings_do_not_leak_history(client,enabled):
    n=enabled;other=register(client,'publication-read-other@example.io')
    assert client.get(url(n),headers=other).status_code==403
    assert client.get(url(n).replace(str(n['finding_id']),str(uuid.uuid4())),headers=n['headers']).status_code==404


def test_missing_schema_has_explicit_activation_message_without_500(client,db_session,enabled):
    n=enabled;db_session.execute(text('DROP TABLE observation_publication_states'));db_session.commit()
    response=client.get(url(n),headers=n['headers']);assert response.status_code==200,response.text
    assert response.json()['availability']=='not_installed'
    assert 'database activation' in response.json()['recovery'][0]
    assert response.json()['items']==[] and not response.json()['publish_available']


def test_generation_missing_and_unsupported_receipt_fail_closed(client,db_session,enabled):
    n=enabled;stage(db_session,n);db_session.commit()
    db_session.execute(delete(State).where(State.org_id==n['org']));db_session.commit()
    response=client.get(url(n),headers=n['headers'])
    assert response.json()['status']=='recovery_required' and response.json()['items']
    assert 'no current generation' in response.json()['recovery'][0]


def test_undo_retains_history_and_pagination_is_stable(client,db_session,enabled):
    n=enabled;stage(db_session,n);db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    response=client.get(url(n),headers=n['headers'],params={'limit':1});assert response.status_code==200,response.text
    data=response.json();assert data['status']=='undone' and data['current']['version']==2
    assert [row['version'] for row in data['items']]==[2] and data['has_more'] and data['next_before_version']==2
    older=client.get(url(n),headers=n['headers'],params={'limit':1,'before_version':2}).json()
    assert [row['version'] for row in older['items']]==[1] and not older['has_more']
    assert older['current']['version']==2


def test_purged_historical_source_is_not_reconstructed_or_a_false_recovery_after_undo(client,db_session,enabled):
    n=enabled;stage(db_session,n);db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    db_session.execute(delete(Scan).where(Scan.id==n['scan_id']));db_session.commit()
    data=client.get(url(n),headers=n['headers']).json()
    assert data['status']=='undone' and not data['current']['source']['retained']
    assert data['current']['source']['filename'] is None
    assert data['current']['observation_retained'] and not data['current']['observation_owner_retained']
    assert len(data['items'])==2 and not data['undo_available']


@pytest.mark.parametrize('params',[{'limit':21},{'limit':0},{'before_version':0}])
def test_history_boundaries_are_enforced(client,enabled,params):
    n=enabled;assert client.get(url(n),headers=n['headers'],params=params).status_code==422


@pytest.mark.parametrize('mutation',['contract','mapping','snapshot'])
def test_active_retention_failures_show_recovery_without_loading_payloads(client,db_session,enabled,mutation):
    from app.models.observation_publication import ObservationPublicationSnapshot as Snapshot
    n=enabled;stage(db_session,n);db_session.commit()
    row=db_session.scalar(select(Decision))
    if mutation=='contract':row.admission_contract='reserved-storage-v1'
    elif mutation=='mapping':row.mapping_version='unsupported-map'
    else:db_session.execute(delete(Snapshot).where(Snapshot.side=='before'))
    db_session.commit();response=client.get(url(n),headers=n['headers'])
    assert response.status_code==200,response.text
    assert response.json()['status']=='recovery_required' and response.json()['recovery']
    assert not response.json()['undo_available'] and 'raw_data' not in response.text


def test_foreign_retention_reference_never_discloses_other_organizations_filename(client,db_session,enabled):
    from app.models.organization import Organization
    n=enabled;stage(db_session,n);db_session.commit()
    other=Organization(name='Private other organization');db_session.add(other);db_session.flush()
    source=Scan(org_id=other.id,scan_type='nessus',status='completed',filename='FOREIGN-PRIVATE-SOURCE.nessus');db_session.add(source);db_session.flush()
    db_session.scalar(select(Decision)).source_scan_id=source.id;db_session.commit()
    response=client.get(url(n),headers=n['headers']);assert response.status_code==200,response.text
    assert response.json()['status']=='recovery_required'
    assert 'FOREIGN-PRIVATE-SOURCE' not in response.text
    assert not response.json()['current']['source']['retained']


def test_history_snapshot_enforces_database_read_only_mode(db_session,enabled,monkeypatch):
    from sqlalchemy import update
    from sqlalchemy.exc import InternalError
    n=enabled
    def attempt_write(db,org_id,finding_id,**kwargs):
        db.execute(update(Finding).where(Finding.id==finding_id).values(workflow_version=99))
    monkeypatch.setattr(publication_read,'_read',attempt_write)
    with pytest.raises(InternalError):publication_read.read(db_session,n['org'],n['finding_id'])
    assert db_session.get(Finding,n['finding_id'],populate_existing=True).workflow_version==0


def test_history_refuses_pending_changes_without_flushing_them(db_session,enabled):
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    n=enabled;finding=db_session.get(Finding,n['finding_id']);finding.workflow_version=99
    with pytest.raises(HTTPException) as error:publication_read.read(db_session,n['org'],n['finding_id'])
    assert error.value.status_code==409 and finding.workflow_version==99
    with Session(db_session.get_bind()) as other:
        assert other.get(Finding,n['finding_id']).workflow_version==0


def test_reserved_storage_without_core_columns_is_unavailable_not_internal_error(client,db_session,enabled):
    n=enabled
    db_session.execute(text('ALTER TABLE observation_publication_decisions DROP COLUMN source_context_hash, DROP COLUMN admission_contract'))
    db_session.commit()
    response=client.get(url(n),headers=n['headers'])
    assert response.status_code==200,response.text
    assert response.json()['availability']=='not_installed'
    assert not response.json()['publish_available'] and not response.json()['undo_available']
