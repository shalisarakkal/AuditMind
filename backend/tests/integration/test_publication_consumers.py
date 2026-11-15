"""Private integrated publication; real source, consumer and lifecycle regressions."""
import copy
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func, text, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.observation_publication import ObservationPublicationDecision as Decision, ObservationPublicationState as State
from app.models.list_revision import OrganizationListRevision
from app.models.evidence_evaluation import OrganizationEvidenceRevision
from app.models.dashboard_snapshot import DashboardSnapshot
from app.models.session import PlatformSetting
from app.models.asset import Asset
from app.models.scan import Scan
from app.models.finding_identity_binding import IdentityTool
from app.services import publication_consumers as integrated, publication_transactions as core
from app.services import dashboard_evidence, dashboard_snapshots, evidence_jobs, status_scoring
from app.services.publication_lifecycle import ensure_free
from tests.conftest import requires_db
from tests.integration.test_publication_transactions import enabled, native_preview, fields, counts

pytestmark = requires_db


def request(db, n, *, undo=False):
    plan=integrated._preview(db,n['org'],n['actor'],n['finding_id'],None if undo else n['observation_id'])
    return core.PublicationRequest(request_id=uuid.uuid4(),expected_version=plan['expected_version'],
        review_token=plan['review_token'],rationale='Reviewed synthetic consumer publication',confirm=True)


def stage(db,n,body=None,*,undo=False):
    return integrated._stage(db,n['org'],n['actor'],n['finding_id'],body or request(db,n,undo=undo),None if undo else n['observation_id'])


def test_atomic_consumers_undo_and_replay_never_revive_equal_field_proofs(db_session,enabled):
    n=enabled;original=fields(db_session,n)
    source=dashboard_evidence.finding_source(db_session,n['org'],n['finding_id'])[1]
    scope=dashboard_evidence.inventory_scope(db_session,n['org']);db_session.commit()
    body=request(db_session,n);stage(db_session,n,body)
    assert integrated.revision(db_session,n['org'])==1
    assert integrated.context(db_session,n['org'],n['finding_id'])['version']==1
    assert db_session.scalar(select(OrganizationListRevision.finding_revision).where(OrganizationListRevision.org_id==n['org']))>0
    with Session(db_session.get_bind()) as outside:
        assert integrated.revision(outside,n['org'])==0 and fields(outside,n)==original
    db_session.commit()
    assert stage(db_session,n,body)['replayed'];assert integrated.revision(db_session,n['org'])==1
    db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    assert fields(db_session,n)==original and integrated.revision(db_session,n['org'])==2
    assert dashboard_evidence.finding_source(db_session,n['org'],n['finding_id'])[1]!=source
    assert dashboard_evidence.inventory_scope(db_session,n['org'])!=scope
    assert stage(db_session,n,body)['replayed'] and integrated.revision(db_session,n['org'])==2


def test_invalidation_failure_rolls_back_fields_history_and_all_epochs(db_session,enabled,monkeypatch):
    n=enabled;before=fields(db_session,n);db_session.commit()
    evidence=evidence_jobs.revision(db_session,n['org']);db_session.commit();body=request(db_session,n)
    original=integrated._invalidate
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('Injected after consumer SQL')
    monkeypatch.setattr(integrated,'_invalidate',fail)
    with pytest.raises(RuntimeError):stage(db_session,n,body)
    assert fields(db_session,n)==before and counts(db_session)==[0,0,0,0]
    assert integrated.revision(db_session,n['org'])==0
    assert evidence_jobs.revision(db_session,n['org'])==evidence


def test_core_receipt_cannot_upgrade_to_consumer_receipt(db_session,enabled):
    from tests.integration.test_publication_transactions import request as core_request, stage as core_stage
    n=enabled;body=core_request(db_session,n);core_stage(db_session,n,body);db_session.commit()
    with pytest.raises(HTTPException):stage(db_session,n,body)
    with pytest.raises(HTTPException):request(db_session,n,undo=True)
    assert integrated.revision(db_session,n['org'])==0


@pytest.mark.parametrize('kind',['finding','observation','scan','asset','tool','identity_binding'])
def test_current_dependencies_guarded_until_exact_undo(db_session,enabled,kind):
    from app.models.observation_publication import ObservationPublicationDependency as Dependency
    n=enabled;stage(db_session,n);db_session.commit()
    identifier=db_session.scalar(select(Dependency.resource_id).where(Dependency.org_id==n['org'],Dependency.resource_kind==kind))
    with pytest.raises(HTTPException) as error:ensure_free(db_session,n['org'],kind,identifier)
    assert error.value.status_code==409
    ensure_free(db_session,uuid.uuid4(),kind,identifier)
    db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    ensure_free(db_session,n['org'],kind,identifier)


@pytest.mark.parametrize('kind',['asset','scan','tool','observation','finding'])
def test_bulk_sql_cannot_change_retained_source_but_workflow_still_works(db_session,enabled,kind):
    n=enabled;stage(db_session,n);db_session.commit()
    from app.models.observation_publication import ObservationPublicationDependency as Dependency
    identifier=db_session.scalar(select(Dependency.resource_id).where(Dependency.org_id==n['org'],Dependency.resource_kind==kind))
    query={'asset':update(Asset).where(Asset.id==identifier).values(hostname='changed.example'),
        'scan':update(Scan).where(Scan.id==identifier).values(content_hash='f'*64),
        'tool':update(IdentityTool).where(IdentityTool.id==identifier).values(active=False),
        'observation':delete(FindingObservation).where(FindingObservation.id==identifier),
        'finding':delete(Finding).where(Finding.id==identifier)}[kind]
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():db_session.execute(query)
    db_session.execute(update(Finding).where(Finding.id==n['finding_id']).values(workflow_version=5))
    db_session.commit()
    assert db_session.get(Finding,n['finding_id'],populate_existing=True).workflow_version==5


def test_later_observation_owner_is_guarded_without_rewriting_dependencies(db_session,enabled):
    n=enabled;stage(db_session,n);db_session.commit()
    observed=db_session.get(FindingObservation,n['observation_id'])
    row={column.name:copy.deepcopy(getattr(observed,column.name)) for column in FindingObservation.__table__.columns}
    row.update(id=uuid.uuid4(),occurrence=observed.occurrence+100,recorded_at=datetime.now(timezone.utc))
    # The new observation may come from another retained completed scan.
    original=db_session.get(Scan,observed.scan_id)
    scan={column.name:getattr(original,column.name) for column in Scan.__table__.columns}
    scan.update(id=uuid.uuid4(),filename='later-source.nessus')
    db_session.add(Scan(**scan));db_session.flush();row.update(scan_id=scan['id'],import_id=scan['id'])
    db_session.add(FindingObservation(**row));db_session.commit()
    with pytest.raises(HTTPException):ensure_free(db_session,n['org'],'scan',scan['id'])


def test_dashboard_capture_and_inflight_snapshot_are_fenced(client,db_session,enabled,monkeypatch):
    from app.api.routes import dashboard
    n=enabled;path=n['base']+'/dashboard';body=request(db_session,n)
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY,value={'enabled':True,'version':1}));db_session.commit()
    assert client.get(path,headers=n['headers']).status_code==202
    row=db_session.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id==n['org']))
    original=dashboard.capture_inventory
    def capture_then_publish(org_id,snapshot):
        result=original(org_id,snapshot)
        with Session(db_session.get_bind()) as other:
            stage(other,n,body);other.commit()
        return result
    monkeypatch.setattr(dashboard,'capture_inventory',capture_then_publish)
    dashboard_snapshots.process(db_session,row.id)
    db_session.expire_all();current=db_session.get(DashboardSnapshot,row.id)
    assert current.payload is None and current.status=='pending'
    monkeypatch.setattr(dashboard,'capture_inventory',original)
    dashboard_snapshots.process(db_session,current.id)
    result=client.get(path,headers=n['headers']);assert result.status_code==200,result.text
    assert result.json()['findings_by_severity']['critical']==1
    db_session.expire_all();assert db_session.get(DashboardSnapshot,row.id).payload['inventory']['publication_revision']==1


def test_pending_scoring_evidence_must_be_resubmitted_after_publish_and_undo(client,db_session,enabled):
    n=enabled;path=n['base']+f"/findings/{n['finding_id']}"
    updated=client.patch(path+'/workflow',headers=n['headers'],json=dict(expected_version=0,status='resolved',rationale='Retest',verification='Retested'))
    assert updated.status_code==200,updated.text
    instant=datetime.now(timezone.utc)
    response=client.post(path+'/risk-verification',headers=n['headers'],json=dict(expected_version=0,expected_workflow_version=1,
        source_reference='https://evidence.example/retest',observed_at=(instant-timedelta(hours=1)).isoformat(),note='Source evidence'))
    assert response.status_code==200,response.text
    stage(db_session,n);db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    response=client.post(path+'/risk-verification/review',headers=n['headers'],json=dict(expected_version=1,expected_workflow_version=1,
        decision='approved',expires_at=(instant+timedelta(days=7)).isoformat(),note='Old evidence',evidence_reviewed=True,self_review_acknowledged=True))
    assert response.status_code==409,response.text
    assert 'generation' in response.text


def test_inflight_evidence_result_is_superseded_by_publication(db_session,enabled,monkeypatch):
    n=enabled;body=request(db_session,n)
    job=evidence_jobs.enqueue(db_session,n['org'],n['actor']);job.status='running';db_session.commit();identifier=job.id
    original=dashboard_evidence.inventory_progress
    def concurrent(snapshot,org_id):
        for event in original(snapshot,org_id):
            if event['type']=='result':
                with Session(db_session.get_bind()) as other:
                    stage(other,n,body);other.commit()
            yield event
    monkeypatch.setattr(dashboard_evidence,'inventory_progress',concurrent)
    evidence_jobs.process_job(db_session,identifier)
    from app.models.evidence_evaluation import EvidenceEvaluation
    current=db_session.get(EvidenceEvaluation,identifier,populate_existing=True)
    assert current.status=='superseded' and current.result is None


def test_list_count_cache_and_sort_see_changed_source_fields(client,db_session,enabled):
    n=enabled;path=n['base']+'/findings'
    old=client.get(path,headers=n['headers'],params={'severity':'medium'});assert old.status_code==200,old.text
    assert old.json()['total']==1
    # Repeat to warm count reuse before the transaction changes severity.
    assert client.get(path,headers=n['headers'],params={'severity':'medium'}).json()['total']==1
    stage(db_session,n);db_session.commit()
    assert client.get(path,headers=n['headers'],params={'severity':'medium'}).json()['total']==0
    result=client.get(path,headers=n['headers'],params={'severity':'critical','sort':'severity'})
    assert result.status_code==200,result.text
    assert result.json()['total']==1
    stage(db_session,n,undo=True);db_session.commit()
    assert client.get(path,headers=n['headers'],params={'severity':'medium'}).json()['total']==1


def test_current_publication_approval_works_and_old_approval_cannot_return_after_undo(client,db_session,enabled):
    from app.models.finding_verification import FindingVerification
    n=enabled;stage(db_session,n);db_session.commit()
    path=n['base']+f"/findings/{n['finding_id']}"
    assert client.patch(path+'/workflow',headers=n['headers'],json=dict(expected_version=0,status='resolved',rationale='Retest',verification='Tested')).status_code==200
    instant=datetime.now(timezone.utc)
    assert client.post(path+'/risk-verification',headers=n['headers'],json=dict(expected_version=0,expected_workflow_version=1,
        source_reference='https://evidence.example/current',observed_at=(instant-timedelta(hours=1)).isoformat(),note='Current evidence')).status_code==200
    response=client.post(path+'/risk-verification/review',headers=n['headers'],json=dict(expected_version=1,expected_workflow_version=1,
        decision='approved',expires_at=(instant+timedelta(days=7)).isoformat(),note='Approved',evidence_reviewed=True,self_review_acknowledged=True))
    assert response.status_code==200,response.text
    assert response.json()['eligible_for_exclusion']
    finding=db_session.get(Finding,n['finding_id'],populate_existing=True)
    keys=[column.name for column in Finding.__table__.columns if column.name.startswith('risk_')]
    approved={key:getattr(finding,key) for key in keys};db_session.commit()
    # Approval must first be explicitly revoked; generation cannot overwrite it.
    with pytest.raises(HTTPException):request(db_session,n,undo=True)
    response=client.post(path+'/risk-verification/review',headers=n['headers'],json=dict(expected_version=2,expected_workflow_version=1,
        decision='revoked',note='Explicit revoke before Undo',evidence_reviewed=False,self_review_acknowledged=False))
    assert response.status_code==200,response.text
    stage(db_session,n,undo=True);db_session.commit()
    # Simulate a stale restoration of materialized approval fields, without a new decision.
    db_session.execute(update(Finding).where(Finding.id==n['finding_id']).values(**approved));db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Finding).where(Finding.id==n['finding_id'],status_scoring.eligible_exclusion()))==0


def test_unchanged_identity_import_updates_remain_allowed(db_session,enabled):
    n=enabled;stage(db_session,n);db_session.commit()
    from app.models.observation_publication import ObservationPublicationDependency as Dependency
    asset_id=db_session.scalar(select(Dependency.resource_id).where(Dependency.resource_kind=='asset'))
    asset=db_session.get(Asset,asset_id)
    db_session.execute(update(Asset).where(Asset.id==asset_id).values(hostname=asset.hostname,environment='test'))
    db_session.commit()
    assert db_session.get(Asset,asset_id,populate_existing=True).environment=='test'


def test_archive_admission_and_worker_recheck_guard_publication_sources(client,db_session,enabled):
    from app.services import archive_service
    from app.models.enums import ArchiveItemType, ArchiveAction
    from app.models.archive import ArchiveBatch, ArchiveJob
    n=enabled;stage(db_session,n);db_session.commit()
    observation=db_session.get(FindingObservation,n['observation_id']);scan_id=observation.scan_id
    with pytest.raises(archive_service.ArchiveError):
        archive_service.start_archive(db_session,n['org'],ArchiveItemType.upload,scan_id,n['actor'])
    db_session.rollback()
    # A previously queued operation must not acquire permission by bypassing admission.
    batch=ArchiveBatch(org_id=n['org'],item_type=ArchiveItemType.upload,item_id=scan_id,label='Synthetic prior queue',state='archiving')
    db_session.add(batch);db_session.flush()
    job=ArchiveJob(org_id=n['org'],batch_id=batch.id,action=ArchiveAction.archive,status='running')
    db_session.add(job);db_session.commit()
    with pytest.raises(archive_service.ArchiveError):archive_service._check_consolidation_lifecycle(db_session,n['org'],ArchiveItemType.upload,scan_id)


def test_guard_ddl_is_identical_in_migration_and_metadata():
    import runpy
    from pathlib import Path
    from app.db.publication_lifecycle import SQL
    migration=runpy.run_path(str(Path(__file__).resolve().parents[2]/'alembic/versions/0058_publication_consumer_fences.py'))
    assert migration['GUARDS']==SQL


def test_unchanged_identity_bulk_updates_do_not_probe_dependencies(db_session,enabled):
    import time
    n=enabled;stage(db_session,n);db_session.commit()
    db_session.execute(text("SET LOCAL track_functions = 'all'"))
    db_session.execute(text("INSERT INTO assets (id,org_id,type,details,created_at,hostname) SELECT gen_random_uuid(), :org, 'server', '{}'::jsonb, now(), 'synthetic-'||i FROM generate_series(1,10000) i"),{'org':n['org']})
    started=time.monotonic()
    db_session.execute(text("UPDATE assets SET hostname=hostname WHERE org_id=:org"),{'org':n['org']})
    elapsed=time.monotonic()-started
    calls=db_session.scalar(text("SELECT coalesce(sum(calls),0) FROM pg_stat_xact_user_functions WHERE funcname='am_publication_affected'"))
    assert calls==0
    print(f'10,000 unchanged asset identity updates: {elapsed:.3f}s; dependency probes: {calls}')


def test_purge_after_undo_removes_source_snapshots_without_recreating_payloads(db_session,enabled):
    from app.models.observation_publication import ObservationPublicationSnapshot as Snapshot
    n=enabled;stage(db_session,n);db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    source=db_session.get(FindingObservation,n['observation_id']).scan_id
    before=db_session.scalar(select(func.count()).select_from(Snapshot))
    db_session.execute(delete(Scan).where(Scan.id==source));db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Snapshot))<before
    assert db_session.scalar(select(func.count()).select_from(Decision))==2
    assert integrated.context(db_session,n['org'],n['finding_id'])['state']=='undone'
    with pytest.raises(HTTPException):request(db_session,n,undo=True)


def test_restore_conflict_preserves_reviewed_history_instead_of_purging_duplicate(db_session,enabled):
    from app.services import archive_service
    from app.models.archive import ArchiveBatch
    from app.models.enums import ArchiveItemType
    n=enabled;stage(db_session,n);db_session.commit();stage(db_session,n,undo=True);db_session.commit()
    old=db_session.get(Finding,n['finding_id']);batch=ArchiveBatch(org_id=n['org'],item_type=ArchiveItemType.upload,
        item_id=old.scan_id,label='Synthetic restored history',state='archived')
    db_session.add(batch);db_session.flush()
    values={column.name:copy.deepcopy(getattr(old,column.name)) for column in Finding.__table__.columns}
    values.update(id=uuid.uuid4(),workflow_version=0)
    old.archived_at=datetime.now(timezone.utc);old.archive_batch_id=batch.id
    db_session.add(Finding(**values));db_session.commit()
    with pytest.raises(archive_service.ArchiveError):
        archive_service._check_consolidation_restore_conflict(db_session,n['org'],batch.id)
    assert db_session.get(Finding,n['finding_id']) is not None


@pytest.mark.parametrize('already_active',[False,True])
def test_noop_does_not_invalidate_consumer_epochs_or_add_receipts(db_session,enabled,already_active):
    from app.services.observation_payload import FIELDS
    n=enabled
    if already_active:
        stage(db_session,n);db_session.commit()
    else:
        payload=db_session.get(FindingObservation,n['observation_id']).payload
        core._materialize(db_session.get(Finding,n['finding_id']),{key:payload[key] for key in FIELDS});db_session.commit()
    epoch=integrated.revision(db_session,n['org']);old_counts=counts(db_session);db_session.commit()
    result=stage(db_session,n)
    assert result['no_op'] and integrated.revision(db_session,n['org'])==epoch and counts(db_session)==old_counts


def test_failed_undo_invalidation_restores_active_generation(db_session,enabled,monkeypatch):
    n=enabled;stage(db_session,n);db_session.commit();before=fields(db_session,n);body=request(db_session,n,undo=True)
    original=integrated._invalidate
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('Injected consumer failure during Undo')
    monkeypatch.setattr(integrated,'_invalidate',fail)
    with pytest.raises(RuntimeError):stage(db_session,n,body,undo=True)
    assert fields(db_session,n)==before and counts(db_session)[:3]==[1,2,1]
    assert integrated.revision(db_session,n['org'])==1
    assert integrated.context(db_session,n['org'],n['finding_id'])['state']=='active'


def test_unrelated_matched_scan_can_be_purged_without_touching_creator_ownership(db_session,enabled):
    from app.models.archive import AssetScan
    n=enabled;stage(db_session,n);db_session.commit()
    scan=Scan(org_id=n['org'],scan_type='cloud_inventory',status='completed',filename='unrelated-match.json')
    db_session.add(scan);db_session.flush()
    db_session.add(AssetScan(scan_id=scan.id,asset_id=n['asset_id'],created=False));db_session.commit()
    ensure_free(db_session,n['org'],'scan',scan.id)
    db_session.execute(delete(Scan).where(Scan.id==scan.id));db_session.commit()
    assert integrated.context(db_session,n['org'],n['finding_id'])['state']=='active'


def test_large_unrelated_asset_purge_remains_indexed_and_allowed(db_session,enabled):
    import time
    n=enabled;stage(db_session,n);db_session.commit()
    db_session.execute(text("INSERT INTO assets (id,org_id,type,details,created_at,hostname) SELECT gen_random_uuid(), :org, 'server', '{}'::jsonb, now(), 'purge-probe-'||i FROM generate_series(1,10000) i"),{'org':n['org']})
    started=time.monotonic()
    result=db_session.execute(text("DELETE FROM assets WHERE org_id=:org AND hostname LIKE 'purge-probe-%'"),{'org':n['org']})
    elapsed=time.monotonic()-started
    assert result.rowcount==10000
    assert integrated.context(db_session,n['org'],n['finding_id'])['state']=='active'
    print(f'10,000 unrelated assets purged with an active publication: {elapsed:.3f}s')


def test_organization_purge_owns_active_publication_and_all_retained_sources(db_session,enabled):
    from app.models.organization import Organization
    n=enabled;stage(db_session,n);db_session.commit()
    db_session.execute(delete(Organization).where(Organization.id==n['org']));db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(Decision))==0


def test_actor_purge_keeps_identity_review_without_requiring_source_undo(db_session,enabled):
    from app.models.user import User
    n=enabled;stage(db_session,n);db_session.commit()
    db_session.execute(delete(User).where(User.id==n['actor']));db_session.commit()
    assert db_session.scalar(select(Decision.actor_id)) is None
    assert db_session.get(Finding,n['finding_id']) is not None


@pytest.mark.parametrize('mutation',['label','context','actor_and_context'])
def test_actor_cleanup_exception_cannot_change_review_material(db_session,enabled,mutation):
    from app.models.finding_identity_binding import ObservationIdentityBinding
    n=enabled;stage(db_session,n);db_session.commit()
    row=db_session.scalar(select(ObservationIdentityBinding).where(ObservationIdentityBinding.observation_id==n['observation_id']))
    values={'actor_label':'Rewritten reviewer'} if mutation=='label' else {'context':{**row.context,'unexpected':'tamper'}}
    if mutation=='actor_and_context':values['actor_id']=None
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(update(ObservationIdentityBinding).where(ObservationIdentityBinding.id==row.id).values(**values))
