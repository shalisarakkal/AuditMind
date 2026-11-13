"""Real native sources and PostgreSQL; foundation reads never consolidate."""
import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, event, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_consolidation import FindingConsolidation, FindingConsolidationDecision
from app.models.finding_history import FindingHistory
from app.models.finding_observation import FindingObservation
from app.models.finding_suppression import FindingSuppression
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services import finding_canonical
from app.services.finding_identity import IDENTITY_VERSION
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register, upload
from tests.integration.test_scan_snapshots import _bind_observation, _nessus

pytestmark = requires_db


def select_pair(client, n):
    body = dict(source_observation_id=str(n['source'].id))
    prepared = client.post(n['canonical_path']+'/canonical/preview', headers=n['headers'], json=body)
    assert prepared.status_code == 200, prepared.text
    if prepared.json()['saved'] and prepared.json()['saved']['current']:
        n['decision'] = prepared.json()['saved']['id']
        return n['decision']
    result = client.post(n['canonical_path']+'/canonical', headers=n['headers'], json={**body,
        'expected_version':prepared.json()['expected_version'], 'review_token':prepared.json()['review_token'],
        'canonical_finding_id':str(n['source'].finding_id), 'confirm_histories':True, 'rationale':'Review both native records'})
    assert result.status_code == 200, result.text
    n['decision'] = result.json()['id']
    return n['decision']


@pytest.fixture
def native(client, db_session):
    headers = register(client, 'consolidation-admin@example.io')
    org = first_org_id(client, headers); base = f'/api/v1/orgs/{org}'
    first = upload(client, base+'/findings/import', headers, 'original.nessus', _nessus('1001'))
    assert first.status_code == 201, first.text
    source = db_session.scalar(select(FindingObservation).where(FindingObservation.scan_id == uuid.UUID(first.json()['scan_id'])))
    asset = source.asset_identity['asset_id']
    tool = client.post(base+'/identity-tools', headers=headers, json=dict(name='Reviewed scanner', rationale='Synthetic test')).json()['id']
    _bind_observation(client, (headers,org), db_session, first.json()['scan_id'], tool, asset)
    renamed = _nessus('1001').replace(b'pilot-host',b'pilot-alias').replace(b'10.0.0.10',b'10.0.0.44')
    second = upload(client, base+'/findings/import', headers, 'alias.nessus', renamed)
    assert second.status_code == 201, second.text
    target,_ = _bind_observation(client, (headers,org), db_session, second.json()['scan_id'], tool, asset)
    n = dict(headers=headers,org=org,base=base,source=source,target=target,asset=asset,tool=tool,
        root=base+'/finding-consolidations',canonical_path=base+f'/findings/{target.finding_id}/observations/{target.id}/identity-binding')
    select_pair(client,n)
    return n


def preview(client, n, **overrides):
    return client.post(n['root']+'/preview',headers=n['headers'],json=dict(canonical_decision_id=n['decision'],**overrides))


def group(db,n,**changes):
    decision=db.get(FindingCanonicalDecision,uuid.UUID(n['decision']))
    values=dict(org_id=uuid.UUID(n['org']), pair_key=decision.pair_key,
        finding_a_id=decision.finding_a_id,finding_b_id=decision.finding_b_id,
        canonical_finding_id=decision.canonical_finding_id,canonical_decision_id=decision.id,
        identity_version=IDENTITY_VERSION,candidate_key=decision.context['candidate_key'],
        tool_id=uuid.UUID(n['tool']),canonical_asset_id=uuid.UUID(n['asset']),version=1,state='active')
    row=FindingConsolidation(**{**values,**changes});db.add(row);db.flush();return row


def receipt(db,n,row,**changes):
    actor=db_session_actor(db,n)
    values=dict(org_id=uuid.UUID(n['org']),consolidation_id=row.id,request_id=uuid.uuid4(),request_hash='a'*64,
        version=1,state='active',rationale='Retained synthetic decision',context={'private':'not returned'},
        actor_id=actor,actor_label='Synthetic admin')
    result=FindingConsolidationDecision(**{**values,**changes});db.add(result);db.flush();return result


def db_session_actor(db,n):
    from app.models.membership import OrgMembership
    return db.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(n['org'])))


def test_valid_preview_is_read_only_and_cannot_authorize_a_write(client,db_session,native):
    n=native
    before=db_session.query(Event).count()
    states={f.id:(f.workflow_version,f.risk_verification_version,f.suppression_id) for f in db_session.scalars(select(Finding))}
    response=preview(client,n);assert response.status_code==200,response.text
    data=response.json();assert data['prerequisites_met'] is True and data['blockers']==[]
    assert data['apply_available'] is False and data['pending_components']
    assert data['observation_count']==2 and data['observation_count_truncated'] is False
    assert data['canonical_finding_id']==str(n['source'].finding_id)
    assert data['alias_finding_id']==str(n['target'].finding_id)
    assert response.headers['cache-control']=='no-store'
    assert preview(client,n).json()['snapshot_fingerprint']==data['snapshot_fingerprint']
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2
    db_session.expire_all()
    assert {f.id:(f.workflow_version,f.risk_verification_version,f.suppression_id) for f in db_session.scalars(select(Finding))}==states
    assert db_session.query(Event).count()==before
    assert db_session.query(FindingConsolidation).count()==0
    assert db_session.query(FindingConsolidationDecision).count()==0
    assert client.post(n['root']+'/apply',headers=n['headers'],json={}).status_code==422
    for suffix in ('','/undo','/publish'):
        assert client.post(n['root']+suffix,headers=n['headers'],json={}).status_code in (404,405)
    assert preview(client,n,confirm=True).status_code==422


@pytest.mark.parametrize('role',['viewer','auditor'])
def test_member_reads_but_preview_requires_actual_admin(client,native,role):
    n=native;other=member(client,n['headers'],n['org'],role)
    assert client.get(n['root'],headers=other).json()['apply_available'] is False
    assert client.post(n['root']+'/preview',headers=other,json={'canonical_decision_id':n['decision']}).status_code==403


def test_cross_org_unknown_targets_and_revocation_are_not_eligible(client,native):
    n=native;outsider=register(client,'consolidation-outsider@example.io')
    assert client.post(n['root']+'/preview',headers=outsider,json={'canonical_decision_id':n['decision']}).status_code==403
    assert client.post(n['root']+'/preview',headers=n['headers'],json={'canonical_decision_id':str(uuid.uuid4())}).status_code==404
    revoked=client.post(n['base']+f"/canonical-decisions/{n['decision']}/revoke",headers=n['headers'],json=dict(expected_version=1,rationale='Revoke selection'))
    assert revoked.status_code==200,revoked.text
    assert preview(client,n).status_code==409


@pytest.mark.parametrize('change,reason',[
    ('alias_assignment','alias_not_pristine'),('alias_history','alias_not_pristine'),
    ('canonical_resolved','canonical_workflow'),('severity','classification_conflict'),
    ('proof','approved_proof'),('latest_source','unpublished_classification'),('suppression','standing_suppression')])
def test_preview_reports_supported_admission_blockers(client,db_session,native,change,reason):
    n=native;alias=db_session.get(Finding,n['target'].finding_id);canonical=db_session.get(Finding,n['source'].finding_id)
    if change=='alias_assignment':alias.assignee_id=db_session_actor(db_session,n)
    elif change=='alias_history':
        db_session.add(FindingHistory(org_id=uuid.UUID(n['org']),finding_id=alias.id,actor_label='Admin',
            version=1,before={},after={},rationale='Recorded work'))
    elif change=='canonical_resolved':canonical.workflow_status='resolved'
    elif change=='severity':
        from app.models.enums import Severity
        alias.severity=Severity.critical if alias.severity!=Severity.critical else Severity.low
    elif change=='proof':canonical.risk_verification_state='approved'
    elif change=='latest_source':
        n['target'].payload={**n['target'].payload,'severity':'critical' if alias.severity.value!='critical' else 'low'}
    else:
        decision=db_session.get(FindingCanonicalDecision,uuid.UUID(n['decision']))
        db_session.add(FindingSuppression(org_id=uuid.UUID(n['org']),identity_version=IDENTITY_VERSION,
            candidate_key=decision.context['candidate_key'],identity={},finding_id=uuid.uuid4(),version=1,state='suppressed'))
    db_session.commit();select_pair(client,n)
    response=preview(client,n);assert response.status_code==200,response.text
    assert reason in {b['code'] for b in response.json()['blockers']}
    assert response.json()['prerequisites_met'] is False and response.json()['apply_available'] is False


def test_extra_unreviewed_observation_cannot_inherit_pair_identity(client,db_session,native):
    n=native;original=n['target']
    extra=FindingObservation(id=uuid.uuid4(),org_id=original.org_id,finding_id=original.finding_id,
        import_id=original.import_id,scan_id=original.scan_id,occurrence=100,source_row=100,
        source=original.source,scan_type=original.scan_type,profile=original.profile,filename=original.filename,
        recorded_at=original.recorded_at-timedelta(seconds=1),asset_identity=original.asset_identity,
        source_identity=original.source_identity,reconciliation_eligible=False,ineligibility_reasons=[],payload=original.payload)
    db_session.add(extra);db_session.commit()
    response=preview(client,n);assert response.status_code==200,response.text
    assert 'identity_reviews_required' in {b['code'] for b in response.json()['blockers']}
    assert response.json()['observation_count']==3


def test_payloads_are_deferred_and_bounded_preview_matches_existing_context(client,db_session,native):
    n=native;large='Synthetic \u03b1'*4000
    for f in db_session.scalars(select(Finding)):f.description=large
    db_session.commit();select_pair(client,n)
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):statements.append(statement)
    event.listen(db_session.get_bind(),'before_cursor_execute',capture)
    try:
        response=preview(client,n)
    finally:event.remove(db_session.get_bind(),'before_cursor_execute',capture)
    assert response.status_code==200,response.text
    data=response.json();assert data['prerequisites_met']
    for row in data['findings']:
        assert row['description']==large[:2000]
        assert row['description_sha256']==hashlib.sha256(large.encode()).hexdigest()
    import re
    for statement in statements:
        columns=statement.split('FROM',1)[0]
        assert not re.search(r'(?:SELECT |, )finding_observations\.payload(?:,| AS|\s*$)',columns)
        assert not re.search(r'(?:SELECT |, )findings\.(?:raw_data|details|description)(?:,| AS|\s*$)',columns)
    normal=finding_canonical.preview(db_session,uuid.UUID(n['org']),n['target'],n['source'].id)
    bounded=finding_canonical.preview(db_session,uuid.UUID(n['org']),n['target'],n['source'].id,bounded=True)
    assert normal['review_token']==bounded['review_token'] and normal['context']==bounded['context']


def test_stale_workflow_and_source_changes_require_re_review(client,db_session,native):
    n=native;canonical=db_session.get(Finding,n['source'].finding_id)
    canonical.description='Changed outside the selected review';db_session.commit()
    assert preview(client,n).status_code==409
    select_pair(client,n)
    assert preview(client,n).status_code==200
    db_session.execute(delete(Scan).where(Scan.id==n['source'].scan_id));db_session.commit()
    assert preview(client,n).status_code==409


def test_recorded_ledger_does_not_change_visibility_and_history_survives_sources(client,db_session,native):
    n=native;row=group(db_session,n);entry=receipt(db_session,n,row);db_session.commit()
    result=client.get(n['root'],headers=n['headers']);assert result.status_code==200
    assert result.json()['apply_available'] is False and len(result.json()['items'])==1
    assert 'candidate_key' not in result.json()['items'][0]
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2
    assert 'group_conflict' in {b['code'] for b in preview(client,n).json()['blockers']}
    db_session.execute(delete(Scan).where(Scan.id==n['source'].scan_id));db_session.commit()
    history=client.get(n['root']+f'/{row.id}/history',headers=n['headers'])
    assert history.status_code==200 and history.json()['items'][0]['id']==str(entry.id)
    assert 'context' not in history.json()['items'][0]
    db_session.execute(delete(User).where(User.id==entry.actor_id));db_session.commit();db_session.refresh(entry)
    assert entry.actor_id is None and entry.actor_label=='Synthetic admin'
    db_session.execute(delete(Organization).where(Organization.id==uuid.UUID(n['org'])));db_session.commit()
    assert db_session.query(FindingConsolidation).count()==db_session.query(FindingConsolidationDecision).count()==0


@pytest.mark.parametrize('query',['?limit=0','?limit=101','?offset=-1','?offset=9223372036854775808'])
def test_page_bounds(client,native,query):
    assert client.get(native['root']+query,headers=native['headers']).status_code==422


def test_ledger_constraints_and_tenant_owner_fk(client,db_session,native):
    n=native;row=group(db_session,n);entry=receipt(db_session,n,row);db_session.commit()
    other=register(client,'consolidation-other@example.io');other_org=uuid.UUID(first_org_id(client,other))
    with pytest.raises(IntegrityError),db_session.begin_nested():
        receipt(db_session,n,row,org_id=other_org)
    with pytest.raises(IntegrityError),db_session.begin_nested():
        receipt(db_session,n,row,version=2,request_id=entry.request_id)
    with pytest.raises(IntegrityError),db_session.begin_nested():
        receipt(db_session,n,row,version=2,rationale='   ')
    a,b=uuid.uuid4(),uuid.uuid4()
    with pytest.raises(IntegrityError),db_session.begin_nested():
        group(db_session,n,pair_key=':'.join(sorted((str(a),str(b)))),finding_a_id=a,finding_b_id=b,canonical_finding_id=a)
    assert client.get(f'/api/v1/orgs/{other_org}/finding-consolidations/{row.id}/history',headers=other).status_code==404


def test_preview_uses_one_read_only_snapshot_during_source_edit(client,db_session,native,monkeypatch):
    from app.services import finding_consolidations as service
    n=native;original=service.finding_canonical.preview
    changed=False
    replacement={**n['target'].payload,'severity':'critical'}
    if db_session.get(Finding,n['target'].finding_id).severity.value=='critical':replacement['severity']='low'
    def raced(snapshot,*args,**kwargs):
        nonlocal changed
        assert snapshot.scalar(text('SHOW transaction_read_only'))=='on'
        assert snapshot.scalar(text('SHOW transaction_isolation'))=='repeatable read'
        result=original(snapshot,*args,**kwargs)
        if not changed:
            with Session(db_session.get_bind()) as other:
                other.execute(text("SET LOCAL lock_timeout='3s'"))
                other.execute(update(FindingObservation).where(FindingObservation.id==n['target'].id).values(payload=replacement))
                other.commit()
            changed=True
        return result
    monkeypatch.setattr(service.finding_canonical,'preview',raced)
    first=preview(client,n);assert first.status_code==200,first.text
    assert first.json()['prerequisites_met'] is True
    second=preview(client,n);assert second.status_code==200,second.text
    assert second.json()['prerequisites_met'] is False
    assert 'unpublished_classification' in {b['code'] for b in second.json()['blockers']}
    assert first.json()['snapshot_fingerprint']!=second.json()['snapshot_fingerprint']


def test_observation_limit_is_bounded_without_exact_count_or_payload_reads(client,db_session,native):
    n=native;o=n['target']
    rows=[dict(id=uuid.uuid4(),org_id=o.org_id,finding_id=o.finding_id,import_id=o.import_id,
        scan_id=o.scan_id,occurrence=100+i,source_row=100+i,source=o.source,scan_type=o.scan_type,
        profile=o.profile,filename=o.filename,recorded_at=o.recorded_at-timedelta(seconds=i+1),
        asset_identity=o.asset_identity,source_identity=o.source_identity,reconciliation_eligible=False,
        ineligibility_reasons=[],payload=o.payload) for i in range(1000)]
    db_session.execute(insert(FindingObservation),rows);db_session.commit()
    statements=[]
    def capture(conn,cursor,statement,parameters,context,many):statements.append(statement)
    event.listen(db_session.get_bind(),'before_cursor_execute',capture)
    try:response=preview(client,n)
    finally:event.remove(db_session.get_bind(),'before_cursor_execute',capture)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['observation_count']==1001 and data['observation_count_truncated'] is True
    assert data['observation_limit']==1000 and data['prerequisites_met'] is False
    assert 'observation_limit' in {b['code'] for b in data['blockers']}
    assert all('finding_observations.payload' not in statement for statement in statements)


def test_historical_pagination_and_invalid_windows(client,db_session,native):
    n=native;row=group(db_session,n);first=receipt(db_session,n,row)
    row.version=2;row.state='undone'
    second=receipt(db_session,n,row,version=2,state='undone');db_session.commit()
    path=n['root']+f'/{row.id}/history'
    head=client.get(path+'?limit=1',headers=n['headers']).json()
    assert head['has_more'] and head['items'][0]['id']==str(second.id)
    older=client.get(path+'?limit=1&before_version=2',headers=n['headers']).json()
    assert older['has_more'] is False and older['items'][0]['id']==str(first.id)
    assert client.get(path+'?before_version=0',headers=n['headers']).status_code==422


def test_platform_only_authority_does_not_allow_admin_preview(client,db_session,native):
    n=native;headers=register(client,'consolidation-platform@example.io')
    actor=db_session.scalar(select(User).where(User.email=='consolidation-platform@example.io'))
    actor.is_sysadmin=True;db_session.commit()
    assert client.get(n['root'],headers=headers).status_code==200
    assert client.post(n['root']+'/preview',headers=headers,json={'canonical_decision_id':n['decision']}).status_code==403
