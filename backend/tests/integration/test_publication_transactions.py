"""Private transaction core on real native sources; no production writer."""
import copy
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.finding import Finding
from app.models.finding_history import FindingHistory
from app.models.finding_observation import FindingObservation
from app.models.membership import OrgMembership
from app.models.user import User
from app.models.scan import Scan
from app.models.observation_publication import (
    ObservationPublicationDecision as Decision, ObservationPublicationSnapshot as Snapshot,
    ObservationPublicationState as State, ObservationPublicationDependency as Dependency,
    OrganizationPublicationSettings as Settings,
)
from app.services import publication_transactions as core
from app.services import observation_payload as contract
from app.services.org_lock import _key
from tests.conftest import requires_db
from tests.helpers import member
from tests.integration.test_observation_publication import native_preview

pytestmark = requires_db


@pytest.fixture
def enabled(db_session, native_preview):
    n = native_preview
    n['actor'] = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == n['org']))
    db_session.commit()
    core._stage_setting(db_session, n['org'], n['actor'], core.SettingRequest(expected_version=0, enabled=True))
    db_session.commit()
    return n


def request(db, n, *, undo=False):
    plan = core._preview(db, n['org'], n['actor'], n['finding_id'], None if undo else n['observation_id'])
    assert not plan['apply_available']
    return core.PublicationRequest(request_id=uuid.uuid4(), expected_version=plan['expected_version'],
        review_token=plan['review_token'], confirm=True, rationale='Explicit synthetic source-field review')


def stage(db, n, body, *, undo=False):
    return core._stage(db, n['org'], n['actor'], n['finding_id'], body, None if undo else n['observation_id'])


def counts(db):
    return [db.scalar(select(func.count()).select_from(model)) for model in (Decision, Snapshot, State, Dependency)]


def fields(db, n):
    f = db.get(Finding, n['finding_id'], populate_existing=True)
    return {key: copy.deepcopy(getattr(f, key)) for key in contract.FIELDS}


def test_publish_is_savepoint_atomic_and_caller_owned(db_session, enabled):
    n=enabled; before=fields(db_session,n); db_session.commit()
    body=request(db_session,n); result=stage(db_session,n,body)
    assert result['version']==1 and not result['replayed']
    assert fields(db_session,n)['severity'].value=='critical'
    assert counts(db_session)[:3]==[1,2,1]
    assert {row.resource_id for row in db_session.scalars(select(Dependency).where(Dependency.resource_kind=='observation'))}=={n['original_id'],n['observation_id']}
    with Session(db_session.get_bind()) as outside:
        assert fields(outside,n)==before and counts(outside)==[0,0,0,0]
    db_session.rollback()
    assert fields(db_session,n)==before and counts(db_session)==[0,0,0,0]


def test_publish_undo_preserve_current_workflow_ownership_and_history(client,db_session,enabled):
    n=enabled
    updated=client.patch(n['base']+f"/findings/{n['finding_id']}/workflow",headers=n['headers'],
        json=dict(expected_version=0,status='accepted_risk',assignee_id=str(n['actor']),
            due_date='2030-10-25',risk_review_date='2030-10-26',deadline_timezone='America/New_York',rationale='Initial review'))
    assert updated.status_code==200,updated.text
    f=db_session.get(Finding,n['finding_id'],populate_existing=True)
    ownership=(f.id,f.org_id,f.scan_id,f.asset_id,f.created_at);before=fields(db_session,n);db_session.commit()
    body=request(db_session,n);first=stage(db_session,n,body);db_session.commit()
    assert first['version']==1 and counts(db_session)[:3]==[1,2,1]
    again=client.patch(n['base']+f"/findings/{n['finding_id']}/workflow",headers=n['headers'],
        json=dict(expected_version=1,status='open',rationale='Current follow-up review'))
    assert again.status_code==200,again.text
    f=db_session.get(Finding,n['finding_id'],populate_existing=True)
    workflow={key:getattr(f,key) for key in ('workflow_status','workflow_version','assignee_id','due_date',
        'due_timezone','due_expires_at','risk_review_date','risk_verification_state','risk_verification_version')}
    history=db_session.scalar(select(func.count()).select_from(FindingHistory));db_session.commit()
    undone=stage(db_session,n,request(db_session,n,undo=True),undo=True);db_session.commit()
    f=db_session.get(Finding,n['finding_id'],populate_existing=True)
    assert undone['version']==2 and fields(db_session,n)==before
    assert (f.id,f.org_id,f.scan_id,f.asset_id,f.created_at)==ownership
    assert {key:getattr(f,key) for key in workflow}==workflow
    assert db_session.scalar(select(func.count()).select_from(FindingHistory))==history==2
    assert db_session.get(State,(n['org'],n['finding_id'])).state=='undone'
    assert stage(db_session,n,body)['replayed']  # Never reapply an old publish after Undo.
    assert fields(db_session,n)==before


def test_failure_after_materialization_rolls_back_rows_and_event(db_session,enabled,monkeypatch):
    n=enabled;before=fields(db_session,n);events=db_session.scalar(select(func.count()).select_from(Event));db_session.commit()
    body=request(db_session,n)
    def fail(*args,**kwargs):raise RuntimeError('Injected Activity failure')
    monkeypatch.setattr(core,'record_event',fail)
    with pytest.raises(RuntimeError,match='Activity'):stage(db_session,n,body)
    assert fields(db_session,n)==before and counts(db_session)==[0,0,0,0]
    assert db_session.scalar(select(func.count()).select_from(Event))==events


@pytest.mark.parametrize('change',['workflow','policy','source','context','confirm','old_preview'])
def test_stale_or_unconfirmed_request_cannot_write(db_session,enabled,change):
    n=enabled;body=request(db_session,n)
    if change=='workflow':db_session.get(Finding,n['finding_id']).workflow_version+=1
    elif change=='policy':db_session.get(Settings,n['org']).version+=1
    elif change=='source':
        obs=db_session.get(FindingObservation,n['observation_id']);obs.filename='Renamed source.nessus'
    elif change=='context':body=body.model_copy(update=dict(expected_version=3))
    elif change=='confirm':body=body.model_copy(update=dict(confirm=False))
    else:
        from app.services.observation_publication import preview
        body=body.model_copy(update=dict(review_token=preview(db_session,n['org'],n['actor'],n['finding_id'],n['observation_id'])['review_token']))
    db_session.commit()
    with pytest.raises(HTTPException) as error:stage(db_session,n,body)
    assert error.value.status_code in (409,422) and counts(db_session)==[0,0,0,0]


def test_replay_is_exact_actor_bound_and_survives_disabled_policy(db_session,enabled):
    n=enabled;body=request(db_session,n);first=stage(db_session,n,body);db_session.commit()
    core._stage_setting(db_session,n['org'],n['actor'],core.SettingRequest(expected_version=1,enabled=False));db_session.commit()
    assert stage(db_session,n,body)==dict(first,replayed=True)
    changed=body.model_copy(update=dict(rationale='Changed request reuse'))
    with pytest.raises(HTTPException,match='409'):stage(db_session,n,changed)
    db_session.commit()
    assert stage(db_session,n,request(db_session,n,undo=True),undo=True)['version']==2


def test_identical_effective_fields_do_not_create_version_or_event(db_session,enabled):
    n=enabled;obs=db_session.get(FindingObservation,n['observation_id'])
    values,_=contract.validate(obs.payload,org_id=n['org'],source_identity=obs.source_identity)
    core._materialize(db_session.get(Finding,n['finding_id']),values);db_session.commit()
    events=db_session.scalar(select(func.count()).select_from(Event));db_session.commit()
    result=stage(db_session,n,request(db_session,n))
    assert result['no_op'] and result['version']==0 and result['decision_id'] is None
    assert counts(db_session)==[0,0,0,0]
    assert db_session.scalar(select(func.count()).select_from(Event))==events


@pytest.mark.parametrize('mutation',['before','after','purged_snapshot','current_fields','approved','ownership'])
def test_undo_refuses_missing_or_changed_sources_and_never_revives_approval(db_session,enabled,mutation):
    n=enabled;stage(db_session,n,request(db_session,n));db_session.commit()
    if mutation in ('before','after'):
        snap=db_session.scalar(select(Snapshot).where(Snapshot.side==mutation));snap.payload={**snap.payload,'description':'Tampered'}
    elif mutation=='purged_snapshot':db_session.execute(delete(Snapshot).where(Snapshot.side=='before'))
    elif mutation=='current_fields':db_session.get(Finding,n['finding_id']).description='Later source edit'
    elif mutation=='approved':db_session.get(Finding,n['finding_id']).risk_verification_state='approved'
    else:
        snap=db_session.scalar(select(Snapshot).where(Snapshot.side=='before'));snap.source_scan_id=n['scan_id']
    db_session.commit()
    with pytest.raises(HTTPException) as error:request(db_session,n,undo=True)
    assert error.value.status_code==409 and db_session.get(State,(n['org'],n['finding_id'])).state=='active'


def test_public_entry_points_remain_closed_even_with_setting_enabled(db_session,enabled):
    for entry in (core.publish,core.undo,core.update_settings):
        with pytest.raises(HTTPException) as error:entry(db_session,enabled,allow_writes=True)
        assert error.value.status_code==409
    assert counts(db_session)==[0,0,0,0]


def test_setting_is_separate_default_off_versioned_noop_and_caller_owned(db_session,native_preview):
    n=native_preview;actor=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org']));db_session.commit()
    assert core.configuration(db_session,n['org'])==dict(enabled=False,version=0)
    assert core._stage_setting(db_session,n['org'],actor,core.SettingRequest(expected_version=0,enabled=False))==dict(enabled=False,version=0)
    assert db_session.get(Settings,n['org']) is None
    core._stage_setting(db_session,n['org'],actor,core.SettingRequest(expected_version=0,enabled=True))
    with Session(db_session.get_bind()) as other:assert core.configuration(other,n['org'])==dict(enabled=False,version=0)
    db_session.rollback()
    assert core.configuration(db_session,n['org'])==dict(enabled=False,version=0)


def test_busy_publication_lock_is_prompt_and_timezone_is_restored(db_session,enabled):
    n=enabled;body=request(db_session,n);engine=db_session.get_bind()
    with engine.connect() as blocker:
        blocker.execute(select(func.pg_advisory_xact_lock(_key(n['org']))))
        with pytest.raises(HTTPException) as error:stage(db_session,n,body)
        assert error.value.status_code==409
        blocker.rollback()
    db_session.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
    result=stage(db_session,n,body)
    assert result['version']==1
    assert db_session.scalar(text("SELECT current_setting('TimeZone')"))=='America/Los_Angeles'


@pytest.mark.parametrize('target',['finding','actor'])
def test_row_lock_conflicts_roll_back_and_restore_transaction_settings(db_session,enabled,target):
    n=enabled;body=request(db_session,n)
    db_session.execute(text("SET LOCAL lock_timeout='2500ms'"))
    db_session.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
    with Session(db_session.get_bind()) as blocker:
        model,identifier=(Finding,n['finding_id']) if target=='finding' else (User,n['actor'])
        blocker.scalar(select(model.id).where(model.id==identifier).with_for_update())
        with pytest.raises(HTTPException) as error:stage(db_session,n,body)
        assert error.value.status_code==409
    assert counts(db_session)==[0,0,0,0]
    assert db_session.scalar(text("SELECT current_setting('lock_timeout')"))=='2500ms'
    assert db_session.scalar(text("SELECT current_setting('TimeZone')"))=='America/Los_Angeles'


def test_two_admins_cannot_overwrite_or_replay_each_others_requests(client,db_session,enabled):
    n=enabled;member(client,n['headers'],str(n['org']),'admin')
    second=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org'],OrgMembership.user_id!=n['actor']));db_session.commit()
    other=dict(n,actor=second)
    first=request(db_session,n);second_request=request(db_session,other)
    stage(db_session,n,first)
    with Session(db_session.get_bind()) as competing:
        with pytest.raises(HTTPException) as error:stage(competing,other,second_request)
        assert error.value.status_code==409 and 'busy' in str(error.value.detail).lower()
        assert counts(competing)==[0,0,0,0]  # No partial commit is visible.
    db_session.commit()
    with pytest.raises(HTTPException):stage(db_session,other,second_request)
    with pytest.raises(HTTPException):stage(db_session,other,first)
    assert counts(db_session)[:3]==[1,2,1]


@pytest.mark.parametrize('role',['viewer','auditor'])
def test_nonadmins_are_rejected_even_for_unknown_undo_or_recorded_replays(client,db_session,enabled,role):
    n=enabled;body=request(db_session,n);stage(db_session,n,body);db_session.commit()
    member(client,n['headers'],str(n['org']),role)
    who=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org'],OrgMembership.role==role));db_session.commit()
    with pytest.raises(HTTPException) as error:core._preview(db_session,n['org'],who,uuid.uuid4())
    assert error.value.status_code==403
    with pytest.raises(HTTPException) as error:core._stage(db_session,n['org'],who,n['finding_id'],body,n['observation_id'])
    assert error.value.status_code==403


@pytest.mark.parametrize('mutation',['workflow','new_observation','backdated_observation','policy'])
def test_undo_fences_changes_after_preview_and_keeps_the_publication(db_session,enabled,mutation):
    n=enabled;stage(db_session,n,request(db_session,n));db_session.commit()
    body=request(db_session,n,undo=True)
    if mutation=='workflow':db_session.get(Finding,n['finding_id']).workflow_version+=1
    elif mutation=='policy':db_session.get(Settings,n['org']).version+=1
    else:
        from datetime import datetime,timezone
        observed=db_session.get(FindingObservation,n['observation_id'])
        row={column.name:getattr(observed,column.name) for column in FindingObservation.__table__.columns}
        row.update(id=uuid.uuid4(),occurrence=observed.occurrence+100,recorded_at=datetime.now(timezone.utc))
        if mutation=='backdated_observation':row['recorded_at']=datetime(2000,1,1,tzinfo=timezone.utc)
        db_session.add(FindingObservation(**row))
    db_session.commit()
    with pytest.raises(HTTPException):stage(db_session,n,body,undo=True)
    assert db_session.get(State,(n['org'],n['finding_id'])).state=='active'
    # A fresh review can preserve the newer workflow/observation context.
    assert stage(db_session,n,request(db_session,n,undo=True),undo=True)['version']==2


def test_second_publication_requires_undo_and_advances_generation(db_session,enabled):
    n=enabled;first=request(db_session,n);stage(db_session,n,first);db_session.commit()
    repeated=stage(db_session,n,request(db_session,n))
    assert repeated['no_op'] and repeated['version']==1 and counts(db_session)[:3]==[1,2,1]
    stage(db_session,n,request(db_session,n,undo=True),undo=True);db_session.commit()
    fresh=request(db_session,n)
    assert fresh.expected_version==2
    assert stage(db_session,n,fresh)['version']==3
    db_session.commit()
    assert stage(db_session,n,first)['replayed'] and db_session.get(State,(n['org'],n['finding_id'])).version==3


@pytest.mark.parametrize('history',['policy','publication'])
def test_migration_cannot_erase_admission_or_policy_history(db_session,enabled,history,monkeypatch):
    import importlib.util
    from pathlib import Path
    n=enabled
    if history=='publication':stage(db_session,n,request(db_session,n));db_session.commit()
    path=Path(__file__).resolve().parents[2]/'alembic/versions/0057_observation_publication_core.py'
    spec=importlib.util.spec_from_file_location('publication_core_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    monkeypatch.setattr(migration.op,'get_bind',lambda:db_session.connection())
    with pytest.raises(RuntimeError,match='policy history'):migration.downgrade()


def test_http_preview_never_discloses_private_transaction_payload(client,enabled):
    response=client.post(enabled['path'],headers=enabled['headers'],json={})
    assert response.status_code==200,response.text
    assert '_transaction' not in response.json() and not response.json()['apply_available']


@pytest.mark.parametrize('damage',['missing_source_hash','unknown_mapping'])
def test_incomplete_inactive_admission_cannot_authorize_a_new_generation(db_session,enabled,damage):
    n=enabled;stage(db_session,n,request(db_session,n));db_session.commit()
    stage(db_session,n,request(db_session,n,undo=True),undo=True);db_session.commit()
    state=db_session.get(State,(n['org'],n['finding_id']))
    receipt=db_session.get(Decision,state.decision_id)
    if damage=='missing_source_hash':receipt.source_context_hash=None
    else:receipt.mapping_version='unsupported-native-mapping'
    db_session.commit()
    with pytest.raises(HTTPException):request(db_session,n)


def test_undo_failure_after_activity_insert_rolls_back_every_effect(db_session,enabled):
    n=enabled;stage(db_session,n,request(db_session,n));db_session.commit()
    before=fields(db_session,n);events=db_session.scalar(select(func.count()).select_from(Event));db_session.commit()
    body=request(db_session,n,undo=True)
    def interrupt(conn,cursor,statement,parameters,context,many):
        if statement.startswith('INSERT INTO events'):raise RuntimeError('Injected failure after Activity insert')
    engine=db_session.get_bind();event.listen(engine,'after_cursor_execute',interrupt)
    try:
        with pytest.raises(RuntimeError,match='Activity insert'):stage(db_session,n,body,undo=True)
    finally:event.remove(engine,'after_cursor_execute',interrupt)
    assert fields(db_session,n)==before and counts(db_session)[:3]==[1,2,1]
    assert db_session.get(State,(n['org'],n['finding_id'])).state=='active'
    assert db_session.scalar(select(func.count()).select_from(Event))==events


@pytest.mark.parametrize('revocation',['role','inactive','password_reset'])
def test_recorded_replays_require_fresh_authorization(db_session,enabled,revocation):
    n=enabled;body=request(db_session,n);stage(db_session,n,body);db_session.commit()
    if revocation=='role':
        db_session.scalar(select(OrgMembership).where(OrgMembership.org_id==n['org'],OrgMembership.user_id==n['actor'])).role='viewer'
    else:setattr(db_session.get(User,n['actor']),'is_active' if revocation=='inactive' else 'must_change_password',revocation!='inactive')
    db_session.commit()
    with pytest.raises(HTTPException) as error:stage(db_session,n,body)
    assert error.value.status_code==403 and counts(db_session)[:3]==[1,2,1]


def test_setting_noop_and_aba_changes_fence_old_preview(db_session,enabled):
    n=enabled;body=request(db_session,n);events=db_session.scalar(select(func.count()).select_from(Event))
    assert core._stage_setting(db_session,n['org'],n['actor'],core.SettingRequest(expected_version=1,enabled=True))==dict(enabled=True,version=1)
    assert db_session.scalar(select(func.count()).select_from(Event))==events
    with pytest.raises(HTTPException):core._stage_setting(db_session,n['org'],n['actor'],core.SettingRequest(expected_version=0,enabled=False))
    core._stage_setting(db_session,n['org'],n['actor'],core.SettingRequest(expected_version=1,enabled=False))
    core._stage_setting(db_session,n['org'],n['actor'],core.SettingRequest(expected_version=2,enabled=True));db_session.commit()
    with pytest.raises(HTTPException):stage(db_session,n,body)
    assert core.configuration(db_session,n['org'])==dict(enabled=True,version=3) and counts(db_session)==[0,0,0,0]


def test_setting_row_lock_is_bounded_and_does_not_leak_timeout(db_session,enabled):
    n=enabled;db_session.execute(text("SET LOCAL lock_timeout='2500ms'"))
    with Session(db_session.get_bind()) as blocker:
        blocker.scalar(select(Settings.org_id).where(Settings.org_id==n['org']).with_for_update())
        with pytest.raises(HTTPException) as error:
            core._stage_setting(db_session,n['org'],n['actor'],core.SettingRequest(expected_version=1,enabled=False))
        assert error.value.status_code==409
    assert core.configuration(db_session,n['org'])==dict(enabled=True,version=1)
    assert db_session.scalar(text("SELECT current_setting('lock_timeout')"))=='2500ms'


def test_reserved_receipt_cannot_be_silently_upgraded_by_replay(db_session,enabled):
    n=enabled;body=request(db_session,n);result=stage(db_session,n,body);db_session.commit()
    db_session.get(Decision,uuid.UUID(result['decision_id'])).admission_contract='reserved-storage-v1';db_session.commit()
    with pytest.raises(HTTPException):stage(db_session,n,body)
    assert fields(db_session,n)['severity'].value=='critical' and counts(db_session)[:3]==[1,2,1]


def test_retained_observation_limit_is_bounded_without_loading_payloads(db_session,enabled):
    n=enabled
    db_session.execute(text('''INSERT INTO finding_observations
        (id,org_id,finding_id,import_id,scan_id,occurrence,source_row,source,scan_type,
        recorded_at,asset_identity,source_identity,reconciliation_eligible,ineligibility_reasons,payload)
        SELECT gen_random_uuid(),:org,:finding,:scan,:scan,x+100,1,'nessus','nessus',
        '2000-01-01'::timestamptz,jsonb_build_object('asset_id',CAST(:asset AS text)),'{}',false,'[]','{}'
        FROM generate_series(1,999) x'''),dict(org=n['org'],finding=n['finding_id'],scan=n['scan_id'],asset=str(n['asset_id'])))
    db_session.commit()
    with pytest.raises(HTTPException,match='1,000'):request(db_session,n)
    assert counts(db_session)==[0,0,0,0]


def test_old_unselected_observation_owner_is_part_of_write_admission(db_session,enabled):
    from datetime import datetime,timezone
    n=enabled
    scan=Scan(org_id=n['org'],scan_type='nessus',status='completed');db_session.add(scan);db_session.flush()
    selected=db_session.get(FindingObservation,n['observation_id'])
    values={column.name:getattr(selected,column.name) for column in FindingObservation.__table__.columns}
    values.update(id=uuid.uuid4(),import_id=scan.id,scan_id=scan.id,occurrence=1,recorded_at=datetime(2000,1,1,tzinfo=timezone.utc))
    db_session.add(FindingObservation(**values));db_session.commit()
    body=request(db_session,n)
    scan.archived_at=datetime.now(timezone.utc);db_session.commit()
    with pytest.raises(HTTPException):stage(db_session,n,body)
    assert counts(db_session)==[0,0,0,0] and fields(db_session,n)['severity'].value=='medium'


def test_undo_review_shows_bounded_actual_source_differences(db_session,enabled):
    n=enabled;selected=db_session.get(FindingObservation,n['observation_id'])
    changed=copy.deepcopy(selected.payload);changed['raw_data']['synopsis']='z'*5000
    changed['description']=(changed['raw_data']['plugin_name'] or '')+': '+changed['raw_data']['synopsis']
    selected.payload=changed;db_session.commit()
    stage(db_session,n,request(db_session,n));db_session.commit()
    review=core._preview(db_session,n['org'],n['actor'],n['finding_id'])
    changes={row['field']:row for row in review['changes']}
    assert review['operation']=='undo' and not review['apply_available']
    assert changes['severity']['before']['value']=='critical' and changes['severity']['after']['value']=='medium'
    assert changes['description']['before']['truncated'] and len(changes['description']['before']['value'])==2000
    assert changes['description']['before']['sha256']==contract.digest(changed['description'])
    assert '_transaction' not in review and 'snapshots' not in review


def test_different_payload_cannot_replace_an_active_publication(db_session,enabled):
    n=enabled;stage(db_session,n,request(db_session,n));db_session.commit()
    row=db_session.get(FindingObservation,n['observation_id']);value=copy.deepcopy(row.payload)
    value['raw_data']['plugin_output']='Different retained source output';row.payload=value;db_session.commit()
    with pytest.raises(HTTPException,match='Undo the exact current'):request(db_session,n)
    assert counts(db_session)[:3]==[1,2,1]
