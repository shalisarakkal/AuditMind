"""Real native imports, tenant isolation and read-only publication admission."""
import copy
import json
import uuid
from datetime import datetime,timezone
import pytest
from sqlalchemy import func,select,text,delete,update
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_history import FindingHistory
from app.models.finding_verification import FindingVerification
from app.models.event import Event
from app.models.scan import Scan
from app.models.asset import Asset
from app.models.membership import OrgMembership
from app.models.enums import ScanStatus
from app.services import observation_payload as contract
from tests.conftest import requires_db
from tests.helpers import register,first_org_id,upload,member
from tests.integration.test_scan_snapshots import _nessus,_bind_observation
from tests.integration.test_finding_consolidation_foundation import native

pytestmark=requires_db


@pytest.fixture
def native_preview(client,db_session):
    headers=register(client,'publication-admin@example.io');org=first_org_id(client,headers);base=f'/api/v1/orgs/{org}'
    first=upload(client,base+'/findings/import',headers,'original.nessus',_nessus('1001'))
    assert first.status_code==201,first.text
    finding=db_session.scalar(select(Finding));finding_id=finding.id;asset_id=finding.asset_id
    original=db_session.scalar(select(FindingObservation))
    changed=_nessus('1001').replace(b'severity="2"',b'severity="4"').replace(b'Synthetic test finding.',b'New native retest description.')
    second=upload(client,base+'/findings/import',headers,'newer.nessus',changed)
    assert second.status_code==201,second.text
    tool=client.post(base+'/identity-tools',headers=headers,json=dict(name='Publication test scanner',rationale='Synthetic independent review'))
    assert tool.status_code==201,tool.text
    observed,candidate=_bind_observation(client,(headers,org),db_session,second.json()['scan_id'],tool.json()['id'],asset_id)
    return dict(headers=headers,org=uuid.UUID(org),base=base,finding_id=finding_id,asset_id=asset_id,
        observation_id=observed.id,original_id=original.id,original_scan_id=uuid.UUID(first.json()['scan_id']),
        scan_id=uuid.UUID(second.json()['scan_id']),candidate=candidate,path=base+f'/findings/{finding_id}/observations/{observed.id}/publication-preview')


def test_changed_preview_preserves_everything_and_distinguishes_ownership(client,db_session,native_preview):
    n=native_preview;events=db_session.scalar(select(func.count()).select_from(Event))
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    data=response.json();changes={row['field']:row for row in data['changes']}
    assert changes['severity']['before']['value']=='medium' and changes['severity']['after']['value']=='critical'
    assert data['publish_available'] is False and data['apply_available'] is False and not data['no_op']
    assert data['provenance']['original_scan_id']==str(n['original_scan_id'])
    assert data['provenance']['observation_scan_id']==str(n['scan_id'])
    assert len(data['review_token'])==64 and data['workflow']['preserved']
    db_session.expire_all();finding=db_session.get(Finding,n['finding_id'])
    assert finding.severity.value=='medium' and finding.workflow_version==0 and finding.scan_id==n['original_scan_id']
    assert db_session.scalar(select(func.count()).select_from(Event))==events
    assert db_session.scalar(select(func.count()).select_from(FindingHistory))==0
    assert db_session.scalar(select(func.count()).select_from(FindingVerification))==0
    again=client.post(n['path'],headers=n['headers'],json={})
    assert again.json()['review_token']==data['review_token']
    for suffix in ('publish','apply','undo'):
        assert client.post(n['path'].replace('publication-preview',suffix),headers=n['headers'],json={}).status_code==404
    assert client.post(n['path'],headers=n['headers'],json={'severity':'low','workflow_status':'resolved'}).status_code==422


@pytest.mark.parametrize('role',['viewer','auditor'])
def test_only_actual_org_admin_can_preview(client,native_preview,role):
    n=native_preview;headers=member(client,n['headers'],str(n['org']),role)
    assert client.post(n['path'],headers=headers,json={}).status_code==403


def test_cross_tenant_and_wrong_finding_observation_are_unavailable(client,db_session,native_preview):
    n=native_preview;other=register(client,'publication-other@example.io')
    assert client.post(n['path'],headers=other,json={}).status_code==403
    bad=n['path'].replace(str(n['observation_id']),str(uuid.uuid4()))
    assert client.post(bad,headers=n['headers'],json={}).status_code==404


@pytest.mark.parametrize('mutation',['unversioned','future_version','extra_workflow','native_mismatch','domain','category','unreviewed','lost_scan','archived_asset','approved','pending_import','older','tied','original_lost','source_scan_type','creator_archived','archive','baseline_size','source_size'])
def test_source_and_identity_admission_fails_closed(client,db_session,native_preview,mutation):
    n=native_preview;observation=db_session.get(FindingObservation,n['observation_id'])
    finding=db_session.get(Finding,n['finding_id']);payload=copy.deepcopy(observation.payload)
    if mutation=='unversioned':payload.pop(contract.MAPPING_KEY)
    elif mutation=='future_version':payload[contract.MAPPING_KEY]='future'
    elif mutation=='extra_workflow':payload['workflow_status']='resolved'
    elif mutation=='native_mismatch':payload['raw_data']['port']='80'
    elif mutation=='domain':payload['domain']='identity_access'
    elif mutation=='category':payload['category']='another'
    elif mutation=='unreviewed':
        from app.models.finding_identity_binding import ObservationIdentityBinding
        db_session.scalar(select(ObservationIdentityBinding).where(ObservationIdentityBinding.observation_id==observation.id)).state='revoked'
    elif mutation=='lost_scan':observation.scan_id=None
    elif mutation=='archived_asset':db_session.get(Asset,n['asset_id']).archived_at=datetime.now(timezone.utc)
    elif mutation=='approved':finding.risk_verification_state='approved'
    elif mutation=='pending_import':db_session.add(Scan(org_id=n['org'],scan_type='nessus',status=ScanStatus.pending))
    elif mutation=='older':
        response=client.post(n['path'].replace(str(n['observation_id']),str(n['original_id'])),headers=n['headers'],json={})
        assert response.status_code==409 and 'latest' in response.text;return
    elif mutation=='tied':db_session.get(FindingObservation,n['original_id']).recorded_at=observation.recorded_at
    elif mutation=='original_lost':finding.scan_id=None
    elif mutation=='source_scan_type':db_session.get(Scan,n['scan_id']).scan_type='json'
    elif mutation=='creator_archived':
        from app.models.archive import AssetScan
        creator=Scan(org_id=n['org'],scan_type='assets',status=ScanStatus.completed,archived_at=datetime.now(timezone.utc))
        db_session.add(creator);db_session.flush();db_session.add(AssetScan(scan_id=creator.id,asset_id=n['asset_id'],created=True))
    elif mutation=='archive':
        from app.models.archive import ArchiveBatch
        db_session.add(ArchiveBatch(org_id=n['org'],item_type='upload',item_id=n['original_scan_id'],label='Pending source',state='archiving'))
    elif mutation=='baseline_size':finding.description='x'*(contract.MAX_BYTES+1)
    elif mutation=='source_size':payload['raw_data']['synopsis']='x'*(contract.MAX_BYTES+1)
    observation.payload=payload;db_session.commit()
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==409,response.text


def test_identical_payload_is_a_read_only_no_op_and_null_removal_is_explicit(client,db_session,native_preview):
    n=native_preview;finding=db_session.get(Finding,n['finding_id']);observation=db_session.get(FindingObservation,n['observation_id'])
    values,_=contract.validate(observation.payload,org_id=n['org'],source_identity=observation.source_identity)
    for field,value in values.items():setattr(finding,field,value)
    db_session.commit()
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==200,response.text
    assert response.json()['no_op'] and response.json()['changes']==[]
    finding=db_session.get(Finding,n['finding_id']);finding.details={'old':'source field'};finding.first_seen=datetime.now(timezone.utc);db_session.commit()
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==200,response.text
    changes={r['field']:r for r in response.json()['changes']}
    assert changes['details']['removal'] and changes['first_seen']['removal']
    assert changes['details']['after']['value'] is None


def test_large_values_are_hashed_fully_but_response_is_bounded(client,db_session,native_preview):
    n=native_preview;observation=db_session.get(FindingObservation,n['observation_id']);payload=copy.deepcopy(observation.payload)
    payload['raw_data']['synopsis']='x'*50000+'SECRET-TAIL-NOT-IN-PREVIEW'
    payload['description']=payload['raw_data']['plugin_name']+': '+payload['raw_data']['synopsis']
    observation.payload=payload;db_session.commit()
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==200,response.text
    assert len(response.content)<16000 and 'SECRET-TAIL-NOT-IN-PREVIEW' not in response.text
    changes={r['field']:r for r in response.json()['changes']}
    assert changes['description']['after']['truncated']
    assert changes['description']['after']['sha256']==contract.digest(payload['description'])


def test_workflow_and_source_edits_change_the_actor_bound_snapshot_token(client,db_session,native_preview):
    n=native_preview
    before=client.post(n['path'],headers=n['headers'],json={}).json()['review_token']
    response=client.patch(n['base']+f"/findings/{n['finding_id']}/workflow",headers=n['headers'],json=dict(expected_version=0,rationale='Concurrent workflow note'))
    assert response.status_code==200,response.text
    after=client.post(n['path'],headers=n['headers'],json={}).json()['review_token']
    assert after!=before
    finding=db_session.get(Finding,n['finding_id']);finding.details={'changed':'source baseline'};db_session.commit()
    again=client.post(n['path'],headers=n['headers'],json={}).json()['review_token']
    assert again!=after
    db_session.get(Scan,n['scan_id']).content_hash='a'*64;db_session.commit()
    latest=client.post(n['path'],headers=n['headers'],json={})
    assert latest.status_code==200,latest.text
    assert latest.json()['review_token']!=again
    assert latest.json()['provenance']['observation_file_sha256']=='a'*64


def test_foreign_observation_on_another_finding_is_not_disclosed(client,db_session,native_preview):
    n=native_preview
    imported=upload(client,n['base']+'/findings/import',n['headers'],'different.nessus',_nessus('2002'))
    assert imported.status_code==201,imported.text
    other=db_session.scalar(select(FindingObservation).where(FindingObservation.scan_id==uuid.UUID(imported.json()['scan_id'])))
    assert client.post(n['path'].replace(str(n['observation_id']),str(other.id)),headers=n['headers'],json={}).status_code==404


def test_preview_uses_read_only_snapshot_and_latest_index_with_large_unrelated_history(client,db_session,native_preview):
    from app.services.observation_publication import preview
    from sqlalchemy import event
    n=native_preview
    other=Finding(org_id=n['org'],domain='vulnerability_management',severity='low',source='nessus')
    db_session.add(other);db_session.flush()
    db_session.execute(text("""INSERT INTO finding_observations
        (id,org_id,finding_id,import_id,scan_id,occurrence,source_row,source,scan_type,recorded_at,asset_identity,source_identity,reconciliation_eligible,ineligibility_reasons,payload)
        SELECT gen_random_uuid(),:org,:finding,:scan,:scan,x+100,1,'nessus','nessus',now(),'{}','{}',false,'[]','{}'
        FROM generate_series(1,100000) x"""),dict(org=n['org'],finding=other.id,scan=n['original_scan_id']))
    db_session.execute(text("""INSERT INTO finding_observations
        (id,org_id,finding_id,import_id,scan_id,occurrence,source_row,source,scan_type,recorded_at,asset_identity,source_identity,reconciliation_eligible,ineligibility_reasons,payload)
        SELECT gen_random_uuid(),:org,:finding,:scan,:scan,x+200100,1,'nessus','nessus','2000-01-01'::timestamptz,'{}','{}',false,'[]','{}'
        FROM generate_series(1,100000) x"""),dict(org=n['org'],finding=n['finding_id'],scan=n['original_scan_id']))
    db_session.commit()
    with db_session.get_bind().connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.exec_driver_sql('ANALYZE finding_observations')
    plan=db_session.scalar(text("EXPLAIN (ANALYZE,FORMAT JSON) SELECT id,recorded_at FROM finding_observations WHERE org_id=:org AND finding_id=:finding ORDER BY recorded_at DESC,id DESC LIMIT 2"),dict(org=n['org'],finding=n['finding_id']))[0]
    def walk(node):
        yield node
        for child in node.get('Plans',[]):yield from walk(child)
    assert any(row.get('Index Name')=='ix_finding_observations_page' for row in walk(plan['Plan']))
    assert not any(row.get('Node Type')=='Seq Scan' for row in walk(plan['Plan']))
    assert not any(row.get('Node Type')=='Sort' for row in walk(plan['Plan']))
    print('PUBLICATION_QUERY_PLAN='+json.dumps(dict(unrelated=100000,target_history=100000,
        execution_ms=plan['Execution Time'],indexes=[row['Index Name'] for row in walk(plan['Plan']) if 'Index Name' in row])))
    db_session.commit();statements=[]
    def inspect(connection,cursor,statement,parameters,context,executemany):statements.append(statement)
    engine=db_session.get_bind();event.listen(engine,'before_cursor_execute',inspect)
    try:
        user_id=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org']))
        db_session.commit()
        result=preview(db_session,n['org'],user_id,n['finding_id'],n['observation_id'])
    finally:event.remove(engine,'before_cursor_execute',inspect)
    assert not result['apply_available']
    assert 'SET TRANSACTION READ ONLY' in statements
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)


def test_preview_token_is_actor_bound_and_platform_read_only_is_not_org_admin(client,db_session,native_preview):
    from app.models.user import User
    n=native_preview;first=client.post(n['path'],headers=n['headers'],json={}).json()
    admin=member(client,n['headers'],str(n['org']),'admin')
    second=client.post(n['path'],headers=admin,json={})
    assert second.status_code==200,second.text
    assert second.json()['review_token']!=first['review_token']
    platform=register(client,'publication-platform@example.io')
    user=db_session.scalar(select(User).where(User.email=='publication-platform@example.io'))
    user.is_sysadmin=True;db_session.execute(delete(OrgMembership).where(OrgMembership.user_id==user.id));db_session.commit()
    assert client.post(n['path'],headers=platform,json={}).status_code==403


def test_standing_suppression_blocks_publication_without_hiding_a_new_finding(client,db_session,native_preview):
    from app.models.finding_suppression import FindingSuppression
    from app.services.finding_identity import IDENTITY_VERSION
    n=native_preview
    db_session.add(FindingSuppression(org_id=n['org'],identity_version=IDENTITY_VERSION,candidate_key=n['candidate'],
        label='Standing identity rule',identity={},finding_id=n['finding_id'],version=1,state='suppressed'))
    db_session.commit()
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==409 and 'standing' in response.text
    assert db_session.get(Finding,n['finding_id']).suppression_id is None


def test_consolidated_members_are_not_payload_publication_targets(client,db_session,native):
    from tests.integration.test_consolidation_visibility import apply
    apply(db_session,native);db_session.commit()
    for observation in (native['source'],native['target']):
        path=native['base']+f'/findings/{observation.finding_id}/observations/{observation.id}/publication-preview'
        response=client.post(path,headers=native['headers'],json={})
        assert response.status_code==409 and 'non-consolidated' in response.text


def test_database_read_only_mode_prevents_accidental_preview_writes(client,db_session,native_preview,monkeypatch):
    from sqlalchemy.exc import DBAPIError
    from app.services import observation_publication
    n=native_preview;user_id=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org']))
    db_session.commit()
    def attempted_write(snapshot,*args):
        snapshot.execute(update(Finding).where(Finding.id==n['finding_id']).values(description='Must not persist'))
    monkeypatch.setattr(observation_publication,'_prepare',attempted_write)
    with pytest.raises(DBAPIError) as caught:
        observation_publication.preview(db_session,n['org'],user_id,n['finding_id'],n['observation_id'])
    assert getattr(caught.value.orig,'sqlstate',None)=='25006'
    assert db_session.get(Finding,n['finding_id'],populate_existing=True).description!='Must not persist'


@pytest.mark.parametrize('field',['filename','asset_identity','creator_link'])
def test_retained_metadata_drift_changes_preview_fingerprint(client,db_session,native_preview,field):
    n=native_preview;before=client.post(n['path'],headers=n['headers'],json={}).json()['review_token']
    observation=db_session.get(FindingObservation,n['observation_id'])
    if field=='filename':observation.filename='Renamed retained source.nessus'
    elif field=='asset_identity':observation.asset_identity={**observation.asset_identity,'hostname':'Changed captured label'}
    else:
        from app.models.archive import AssetScan
        link=db_session.scalar(select(AssetScan).where(AssetScan.scan_id==n['original_scan_id'],AssetScan.asset_id==n['asset_id']))
        assert link.created
        link.created=False
    db_session.commit()
    response=client.post(n['path'],headers=n['headers'],json={})
    assert response.status_code==200,response.text
    assert response.json()['review_token']!=before
