"""Public default-off admission, exact-request replay and retained-source lifecycle."""
import uuid
from datetime import datetime,timezone
import pytest
from sqlalchemy import func,select
from app.models.finding import Finding
from app.models.finding_consolidation import FindingConsolidation,FindingConsolidationDecision
from app.models.archive import ArchiveBatch,ArchiveJob
from app.models.enums import ArchiveAction,ArchiveItemType,ArchiveState,ScanStatus
from app.models.event import Event
from app.services import archive_service
from tests.conftest import requires_db
from tests.helpers import member,register
from tests.integration.test_finding_consolidation_foundation import native
from tests.integration.test_consolidation_visibility import apply as private_apply,undo_fixture

pytestmark=requires_db


def enable(client,n):
    response=client.patch(n['root']+'/settings',headers=n['headers'],json=dict(expected_version=0,enabled=True))
    assert response.status_code==200,response.text


def request(client,n):
    response=client.post(n['root']+'/publication-preview',headers=n['headers'],json=dict(canonical_decision_id=n['decision']))
    assert response.status_code==200,response.text
    plan=response.json()
    return dict(canonical_decision_id=n['decision'],request_id=str(uuid.uuid4()),expected_version=plan['expected_version'],
        review_token=plan['review_token'],rationale='Reviewed both retained source histories',confirm=True)


def publish(client,n):
    enable(client,n);payload=request(client,n)
    response=client.post(n['root']+'/apply',headers=n['headers'],json=payload)
    assert response.status_code==200,response.text
    return payload,response.json()


def undo_request(client,n,result):
    endpoint=n['root']+'/'+result['consolidation_id']
    response=client.post(endpoint+'/undo-preview',headers=n['headers'],json={})
    assert response.status_code==200,response.text
    value=response.json()
    payload=dict(request_id=str(uuid.uuid4()),expected_version=value['expected_version'],
        review_token=value['review_token'],rationale='Restore independent visibility',confirm=True)
    return endpoint,payload


def test_default_off_cannot_be_bypassed_and_own_org_admin_required(client,db_session,native):
    n=native
    assert client.get(n['root']+'/settings',headers=n['headers']).json()==dict(enabled=False,version=0)
    response=client.post(n['root']+'/publication-preview',headers=n['headers'],json=dict(canonical_decision_id=n['decision']))
    assert response.status_code==409
    from tests.integration.test_consolidation_transactions import request as internal_request
    who,payload=internal_request(db_session,n)
    assert client.post(n['root']+'/apply',headers=n['headers'],json=payload.model_dump(mode='json')).status_code==409
    for role in ('viewer','auditor'):
        headers=member(client,n['headers'],n['org'],role)
        assert client.patch(n['root']+'/settings',headers=headers,json=dict(expected_version=0,enabled=True)).status_code==403
        assert client.post(n['root']+'/apply',headers=headers,json=payload.model_dump(mode='json')).status_code==403
    assert db_session.scalar(select(func.count()).select_from(Finding).where(Finding.active()))==2


def test_apply_undo_and_unknown_response_retries_are_atomic_and_idempotent(client,db_session,native):
    n=native;payload,result=publish(client,n)
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==1
    replay=client.post(n['root']+'/apply',headers=n['headers'],json=payload)
    assert replay.status_code==200 and replay.json()['replayed']
    endpoint,undo_payload=undo_request(client,n,result)
    undone=client.post(endpoint+'/undo',headers=n['headers'],json=undo_payload)
    assert undone.status_code==200,undone.text
    assert undone.json()['version']==2
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2
    again=client.post(endpoint+'/undo',headers=n['headers'],json=undo_payload)
    assert again.status_code==200 and again.json()['replayed']
    assert client.post(n['root']+'/apply',headers=n['headers'],json=payload).json()['replayed']
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.type=='finding_consolidated'))==1
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.type=='finding_consolidation_undone'))==1
    assert db_session.scalar(select(func.count()).select_from(Finding))==2


def test_disabling_preserves_pairs_and_allows_explicit_undo(client,native):
    n=native;payload,result=publish(client,n)
    response=client.patch(n['root']+'/settings',headers=n['headers'],json=dict(expected_version=1,enabled=False))
    assert response.status_code==200,response.text
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==1
    assert client.post(n['root']+'/apply',headers=n['headers'],json=payload).json()['replayed']
    endpoint,body=undo_request(client,n,result)
    assert client.post(endpoint+'/undo',headers=n['headers'],json=body).status_code==200


def test_changed_nonce_context_and_policy_roundtrip_conflict(client,native):
    n=native;enable(client,n);payload=request(client,n)
    client.patch(n['root']+'/settings',headers=n['headers'],json=dict(expected_version=1,enabled=False))
    client.patch(n['root']+'/settings',headers=n['headers'],json=dict(expected_version=2,enabled=True))
    assert client.post(n['root']+'/apply',headers=n['headers'],json=payload).status_code==409
    payload=request(client,n)
    assert client.post(n['root']+'/apply',headers=n['headers'],json=payload).status_code==200
    assert client.post(n['root']+'/apply',headers=n['headers'],json={**payload,'rationale':'Changed request reuse'}).status_code==409


@pytest.mark.parametrize('kind',['source_scan','alias_scan','canonical_asset','alias_asset','tool','identity','designation'])
def test_group_blocks_source_and_identity_mutation_until_undo(client,db_session,native,kind):
    n=native;payload,result=publish(client,n)
    source=db_session.get(Finding,n['source'].finding_id);alias=db_session.get(Finding,n['target'].finding_id)
    if kind.endswith('scan'):
        identifier=source.scan_id if kind=='source_scan' else alias.scan_id
        response=client.post(n['base']+f'/scans/{identifier}/archive',headers=n['headers'])
    elif kind.endswith('asset'):
        identifier=n['asset'] if kind=='canonical_asset' else alias.asset_id
        response=client.post(n['base']+f'/assets/{identifier}/archive',headers=n['headers'])
    elif kind=='tool':
        response=client.post(n['base']+f"/identity-tools/{n['tool']}/retire",headers=n['headers'],json=dict(expected_version=1,rationale='Attempted tool retirement'))
    elif kind=='identity':
        response=client.post(n['canonical_path']+'/revoke',headers=n['headers'],json=dict(expected_version=1,rationale='Attempted binding revoke'))
    else:
        response=client.post(n['base']+f"/canonical-decisions/{n['decision']}/revoke",headers=n['headers'],json=dict(expected_version=1,rationale='Attempted canonical revoke'))
    assert response.status_code==409,response.text
    assert 'Undo' in response.text
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==1
    assert db_session.scalar(select(func.count()).select_from(ArchiveJob))==0


def test_queued_worker_rechecks_before_any_inventory_write(client,db_session,native):
    n=native;payload,result=publish(client,n)
    source=db_session.get(Finding,n['source'].finding_id)
    # Simulate a job retained from an older admission generation.
    batch=ArchiveBatch(org_id=uuid.UUID(n['org']),item_type=ArchiveItemType.upload,item_id=source.scan_id,
        label='Synthetic queued source archive',state=ArchiveState.archiving)
    db_session.add(batch);db_session.flush()
    job=ArchiveJob(org_id=uuid.UUID(n['org']),batch_id=batch.id,action=ArchiveAction.archive,status=ScanStatus.pending)
    db_session.add(job);db_session.commit()
    finished=archive_service.run_job(db_session,job.id)
    assert finished.status==ScanStatus.failed and 'Undo' in finished.summary['error']
    assert all(row.archived_at is None for row in db_session.scalars(select(Finding)))


def test_undo_then_archive_restore_retains_both_physical_members(client,db_session,native):
    n=native;payload,result=publish(client,n)
    endpoint,body=undo_request(client,n,result)
    assert client.post(endpoint+'/undo',headers=n['headers'],json=body).status_code==200
    alias=db_session.get(Finding,n['target'].finding_id)
    response=client.post(n['base']+f'/scans/{alias.scan_id}/archive',headers=n['headers'])
    assert response.status_code==200,response.text
    batch=response.json()['batch_id']
    restored=client.post(n['base']+f'/archive/{batch}/restore',headers=n['headers'])
    assert restored.status_code==200,restored.text
    assert db_session.scalar(select(func.count()).select_from(Finding))==2
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2


def test_activity_failure_rolls_back_publication(client,db_session,native,monkeypatch):
    from fastapi import HTTPException
    from app.services import consolidation_publication
    n=native;enable(client,n);payload=request(client,n)
    def fail(*args,**kwargs):raise HTTPException(503,'Synthetic Activity failure')
    monkeypatch.setattr(consolidation_publication,'record_event',fail)
    response=client.post(n['root']+'/apply',headers=n['headers'],json=payload)
    assert response.status_code==503,response.text
    assert db_session.scalar(select(func.count()).select_from(FindingConsolidationDecision))==0
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2


@pytest.mark.parametrize('target',['alias','canonical'])
def test_reimport_keeps_new_alias_independent_or_invalidates_canonical_proof(client,db_session,native,target):
    from tests.integration.test_scan_snapshots import _nessus
    from tests.helpers import upload
    from tests.integration.test_consolidation_proof import approved
    n=native
    # A real approved pair, independently scoped to both original observations.
    endpoint,review=approved(client,db_session,n)
    xml=_nessus('1001')
    if target=='alias':xml=xml.replace(b'pilot-host',b'pilot-alias').replace(b'10.0.0.10',b'10.0.0.44')
    response=upload(client,n['base']+'/findings/import',n['headers'],'later-'+target+'.nessus',xml+b'\n<!-- independent later scan -->')
    assert response.status_code==201,response.text
    current=client.get(n['base']+'/findings',headers=n['headers']).json()
    if target=='alias':
        assert current['total']==2
        assert db_session.scalar(select(func.count()).select_from(Finding))==3
        from app.models.finding_observation import FindingObservation
        scan_id=uuid.UUID(response.json()['scan_id'])
        observation=db_session.scalar(select(FindingObservation).where(FindingObservation.scan_id==scan_id))
        assert observation.finding_id not in (n['source'].finding_id,n['target'].finding_id)
        # Independently binding this third copy requires undo first; no silent
        # member addition or suppression occurs when the new source appears.
        binding=client.put(n['base']+f'/findings/{observation.finding_id}/observations/{observation.id}/identity-binding',
            headers=n['headers'],json=dict(expected_version=0,tool_id=n['tool'],expected_tool_version=1,
                canonical_asset_id=n['asset'],confirm_mapping=True,rationale='Review the reappearance'))
        assert binding.status_code==409,binding.text
    else:
        assert current['total']==1
        assert client.get(endpoint,headers=n['headers']).json()['eligible_for_exclusion'] is False
    from app.models.finding_consolidation import FindingConsolidationMember
    assert db_session.scalar(select(func.count()).select_from(FindingConsolidationMember))==2


def test_group_receipts_survive_source_purge_after_undo(client,db_session,native):
    n=native;target_id=n['target'].finding_id;payload,result=publish(client,n)
    endpoint,body=undo_request(client,n,result)
    assert client.post(endpoint+'/undo',headers=n['headers'],json=body).status_code==200
    alias=db_session.get(Finding,target_id)
    response=client.post(n['base']+f'/scans/{alias.scan_id}/archive',headers=n['headers'])
    assert response.status_code==200,response.text
    purge=client.post(n['base']+f"/archive/{response.json()['batch_id']}/purge",headers=n['headers'])
    assert purge.status_code==200,purge.text
    assert db_session.get(Finding,target_id,populate_existing=True) is None
    history=client.get(n['root']+'/'+result['consolidation_id']+'/history',headers=n['headers'])
    assert history.status_code==200 and len(history.json()['items'])==2
    assert db_session.get(FindingConsolidation,uuid.UUID(result['consolidation_id'])).state=='undone'
    retry=client.post(endpoint+'/undo',headers=n['headers'],json=body)
    assert retry.status_code==200 and retry.json()['replayed']
    assert db_session.get(Finding,target_id,populate_existing=True) is None


def test_setting_noop_and_stale_save_do_not_create_version_noise(client,db_session,native):
    n=native;enable(client,n)
    events=db_session.scalar(select(func.count()).select_from(Event).where(Event.type=='settings_changed'))
    response=client.patch(n['root']+'/settings',headers=n['headers'],json=dict(expected_version=1,enabled=True))
    assert response.status_code==200 and response.json()['version']==1
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.type=='settings_changed'))==events
    assert client.patch(n['root']+'/settings',headers=n['headers'],json=dict(expected_version=0,enabled=False)).status_code==409


@pytest.mark.parametrize('role',['viewer','auditor','foreign'])
def test_undo_and_opt_in_cannot_be_written_by_other_roles_or_tenants(client,native,role):
    n=native;payload,result=publish(client,n)
    headers=register(client,'foreign-group-reader@example.com') if role=='foreign' else member(client,n['headers'],n['org'],role)
    response=client.post(n['root']+'/'+result['consolidation_id']+'/undo-preview',headers=headers,json={})
    assert response.status_code==403,response.text
    assert client.get(n['root']+'/for-finding/'+str(n['source'].finding_id),headers=headers).status_code==(403 if role=='foreign' else 200)


def test_apply_and_undo_require_current_actor_bound_preview(client,db_session,native):
    from tests.integration.test_consolidation_transactions import actor
    from app.models.membership import OrgMembership
    from app.models.user import User
    n=native;enable(client,n);payload=request(client,n)
    second=member(client,n['headers'],n['org'],'admin')
    assert client.post(n['root']+'/apply',headers=second,json=payload).status_code==409
    assert client.post(n['root']+'/apply',headers=n['headers'],json=payload).status_code==200
    result=client.get(n['root']+'/for-finding/'+str(n['source'].finding_id),headers=n['headers']).json()['items'][0]
    endpoint,body=undo_request(client,n,dict(consolidation_id=result['id']))
    assert client.post(endpoint+'/undo',headers=second,json=body).status_code==409


def test_group_approval_must_be_explicitly_revoked_even_when_expired(client,db_session,native):
    from datetime import timedelta
    from tests.integration.test_consolidation_proof import approved
    n=native;endpoint,result=approved(client,db_session,n)
    finding=db_session.get(Finding,n['source'].finding_id)
    finding.risk_verification_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db_session.commit()
    group_id=str(finding.consolidation_id)
    response=client.post(n['root']+'/'+group_id+'/undo-preview',headers=n['headers'],json={})
    assert response.status_code==409 and 'revoke' in response.text


def test_restore_refuses_unrelated_reappearance_instead_of_purging_history(client,db_session,native):
    from tests.helpers import upload
    from tests.integration.test_scan_snapshots import _nessus
    n=native;target_id=n['target'].finding_id;payload,result=publish(client,n)
    xml=_nessus('1001').replace(b'pilot-host',b'pilot-alias').replace(b'10.0.0.10',b'10.0.0.44')
    imported=upload(client,n['base']+'/findings/import',n['headers'],'reappearance-before-undo.nessus',xml+b'\n<!-- retained independent reappearance -->')
    assert imported.status_code==201,imported.text
    endpoint,body=undo_request(client,n,result)
    assert client.post(endpoint+'/undo',headers=n['headers'],json=body).status_code==200
    original=db_session.get(Finding,target_id)
    archived=client.post(n['base']+f'/scans/{original.scan_id}/archive',headers=n['headers'])
    assert archived.status_code==200,archived.text
    restored=client.post(n['base']+f"/archive/{archived.json()['batch_id']}/restore",headers=n['headers'])
    assert restored.status_code==200,restored.text
    assert restored.json()['status']=='failed' and 'conflict' in restored.json()['summary']['error']
    assert db_session.get(Finding,target_id,populate_existing=True).archived_at is not None
    assert db_session.scalar(select(func.count()).select_from(Finding))==3


def test_busy_reviewer_row_returns_conflict_without_mutating_setting(db_session,native):
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    from app.models.user import User
    from app.schemas.finding_consolidation import ConsolidationSettingUpdate
    from app.services import consolidation_policy
    from tests.integration.test_consolidation_transactions import actor
    n=native;org=uuid.UUID(n['org']);who=actor(db_session,n);db_session.commit()
    with Session(db_session.get_bind()) as blocker,Session(db_session.get_bind()) as candidate:
        blocker.scalar(select(User).where(User.id==who).with_for_update())
        with pytest.raises(HTTPException) as caught:
            consolidation_policy.update(candidate,org,who,ConsolidationSettingUpdate(expected_version=0,enabled=True))
        assert caught.value.status_code==409
        candidate.commit()
        assert consolidation_policy.configuration(candidate,org)==dict(enabled=False,version=0)


def test_pending_later_observation_source_blocks_undo_until_failed_job_recovery(client,db_session,native):
    from app.models.finding_observation import FindingObservation
    from app.models.scan import Scan
    import copy
    n=native;payload,result=publish(client,n)
    later=Scan(org_id=uuid.UUID(n['org']),scan_type='nessus',source='upload',status=ScanStatus.completed,filename='Later source')
    db_session.add(later);db_session.flush()
    source=db_session.get(FindingObservation,n['source'].id)
    values={column.name:copy.deepcopy(getattr(source,column.name)) for column in FindingObservation.__table__.columns}
    values.update(id=uuid.uuid4(),scan_id=later.id,import_id=later.id,occurrence=10)
    db_session.add(FindingObservation(**values))
    batch=ArchiveBatch(org_id=uuid.UUID(n['org']),item_type=ArchiveItemType.upload,item_id=later.id,label='Later source',state=ArchiveState.archiving)
    db_session.add(batch);db_session.flush()
    job=ArchiveJob(org_id=uuid.UUID(n['org']),batch_id=batch.id,action=ArchiveAction.archive,status=ScanStatus.pending)
    db_session.add(job);db_session.commit()
    endpoint=n['root']+'/'+result['consolidation_id']
    response=client.post(endpoint+'/undo-preview',headers=n['headers'],json={})
    assert response.status_code==409 and 'source operation' in response.text
    assert archive_service.run_job(db_session,job.id).status==ScanStatus.failed
    assert client.post(endpoint+'/undo-preview',headers=n['headers'],json={}).status_code==200


def test_reapply_after_undo_requires_fresh_preview_and_preserves_old_replay(client,db_session,native):
    n=native;original,result=publish(client,n)
    endpoint,body=undo_request(client,n,result)
    assert client.post(endpoint+'/undo',headers=n['headers'],json=body).status_code==200
    fresh=request(client,n)
    assert fresh['expected_version']==2
    applied=client.post(n['root']+'/apply',headers=n['headers'],json=fresh)
    assert applied.status_code==200,applied.text
    assert applied.json()['version']==3
    assert applied.json()['consolidation_id']==result['consolidation_id']
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==1
    replay=client.post(n['root']+'/apply',headers=n['headers'],json=original)
    assert replay.status_code==200 and replay.json()['replayed']
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==1
    groups=client.get(n['root']+'/for-finding/'+str(n['source'].finding_id),headers=n['headers'],params={'limit':1,'offset':0})
    assert groups.status_code==200,groups.text
    assert groups.json()['current_group_id']==result['consolidation_id']
    assert len(groups.json()['items'])==1
    assert client.get(n['root']+'/for-finding/'+str(n['source'].finding_id),headers=n['headers'],params={'limit':0}).status_code==422
    assert db_session.scalar(select(func.count()).select_from(FindingConsolidationDecision))==3


def test_group_history_paging_keeps_current_membership_visible(client,db_session,native):
    from datetime import timedelta
    from tests.integration.test_finding_consolidation_foundation import group
    n=native;_,result=publish(client,n)
    for index in range(21):
        other=uuid.uuid4()
        group(db_session,n,pair_key=str(uuid.uuid4()),finding_a_id=n['source'].finding_id,finding_b_id=other,state='undone',
            updated_at=datetime.now(timezone.utc)+timedelta(seconds=index+1))
    db_session.commit()
    path=n['root']+'/for-finding/'+str(n['source'].finding_id)
    first=client.get(path,headers=n['headers']).json()
    assert first['current_group_id']==result['consolidation_id']
    assert first['has_more'] and len(first['items'])==20
    assert not any(row['published'] for row in first['items'])
    second=client.get(path,headers=n['headers'],params={'offset':20}).json()
    assert second['current_group_id']==result['consolidation_id']
    assert not second['has_more'] and len(second['items'])==2
    assert any(row['published'] for row in second['items'])
