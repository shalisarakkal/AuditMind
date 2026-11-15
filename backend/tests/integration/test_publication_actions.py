"""Real authorized API actions reuse fully integrated, versioned transactions."""
import uuid
import pytest
from sqlalchemy import select, func, text
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.user import User
from app.models.event import Event
from app.models.observation_publication import ObservationPublicationDecision as Decision
from app.services import publication_consumers, publication_transactions as core
from tests.conftest import requires_db
from tests.helpers import member
from tests.integration.test_observation_publication import native_preview

pytestmark=requires_db


def paths(n):
    root=n['base']+'/observation-publication'
    target=root+f"/findings/{n['finding_id']}"
    return root,target,target+f"/observations/{n['observation_id']}"


def enable(client,n):
    response=client.patch(paths(n)[0]+'/settings',headers=n['headers'],json={'expected_version':0,'enabled':True})
    assert response.status_code==200,response.text


def payload(plan,**extra):
    return dict(request_id=str(uuid.uuid4()),expected_version=plan['expected_version'],review_token=plan['review_token'],rationale='Reviewed real native source and preserved workflow',confirm=True,**extra)


def prepare(client,n,undo=False):
    _,target,observation=paths(n)
    response=client.post(target+'/undo-preview' if undo else observation+'/preview',headers=n['headers'],json={})
    assert response.status_code==200,response.text
    assert '_transaction' not in response.text and 'snapshots' not in response.json()
    return response.json()


def test_default_off_actual_admin_setting_noop_and_stale_version(client,db_session,native_preview):
    n=native_preview;root,_,obs=paths(n)
    value=client.get(root+'/settings',headers=n['headers']);assert value.status_code==200 and value.json()=={'available':True,'enabled':False,'version':0,'reason':None}
    assert client.post(obs+'/preview',headers=n['headers'],json={}).status_code==409
    enable(client,n)
    response=client.patch(root+'/settings',headers=n['headers'],json={'expected_version':1,'enabled':True})
    assert response.status_code==200 and response.json()['version']==1
    assert client.patch(root+'/settings',headers=n['headers'],json={'expected_version':0,'enabled':False}).status_code==409


def test_apply_undo_exact_replay_disabled_policy_and_current_workflow(client,db_session,native_preview):
    n=native_preview;enable(client,n);root,target,obs=paths(n)
    before=client.get(n['base']+f"/findings/{n['finding_id']}/workflow",headers=n['headers']).json()
    plan=prepare(client,n);assert plan['apply_available'] and plan['operation']=='publish'
    body=payload(plan);result=client.post(obs+'/publish',headers=n['headers'],json=body)
    assert result.status_code==200,result.text
    assert result.json()['version']==1 and not result.json()['replayed']
    assert db_session.get(Finding,n['finding_id'],populate_existing=True).severity.value=='critical'
    assert client.post(obs+'/publish',headers=n['headers'],json=body).json()['replayed']
    assert db_session.scalar(select(func.count()).select_from(Decision))==1
    assert client.get(n['base']+f"/findings/{n['finding_id']}/workflow",headers=n['headers']).json()==before
    assert client.patch(root+'/settings',headers=n['headers'],json={'expected_version':1,'enabled':False}).status_code==200
    assert client.post(obs+'/preview',headers=n['headers'],json={}).status_code==409
    undo=payload(prepare(client,n,undo=True));response=client.post(target+'/undo',headers=n['headers'],json=undo)
    assert response.status_code==200,response.text
    assert response.json()['version']==2
    assert db_session.get(Finding,n['finding_id'],populate_existing=True).severity.value=='medium'
    assert client.post(obs+'/publish',headers=n['headers'],json=body).json()['replayed']
    assert client.post(target+'/undo',headers=n['headers'],json=undo).json()['replayed']
    assert publication_consumers.revision(db_session,n['org'])==2


@pytest.mark.parametrize('role',['viewer','auditor','platform'])
def test_nonadmins_cannot_enable_preview_apply_or_undo(client,db_session,native_preview,role):
    n=native_preview;enable(client,n);root,target,obs=paths(n);body=payload(prepare(client,n))
    headers=member(client,n['headers'],str(n['org']),'viewer' if role=='platform' else role)
    if role=='platform':
        actor=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==n['org'],OrgMembership.role=='viewer'))
        db_session.get(User,actor).is_sysadmin=True;db_session.commit()
    assert client.get(root+'/settings',headers=headers).status_code==200
    for endpoint,data in ((root+'/settings',{'expected_version':1,'enabled':False}),(obs+'/preview',{}),(obs+'/publish',body),(target+'/undo-preview',{}),(target+'/undo',body)):
        response=client.patch(endpoint,headers=headers,json=data) if endpoint.endswith('/settings') else client.post(endpoint,headers=headers,json=data)
        assert response.status_code==403,response.text


@pytest.mark.parametrize('damage',['settings_table','receipt_columns','revision_table','dependency_table','guard_function','guard_trigger'])
def test_incomplete_activation_cannot_open_writer_or_setting(client,db_session,native_preview,damage):
    n=native_preview;root,_,obs=paths(n)
    if damage=='settings_table':db_session.execute(text('DROP TABLE organization_publication_settings'))
    elif damage=='receipt_columns':db_session.execute(text('ALTER TABLE observation_publication_decisions DROP COLUMN source_context_hash'))
    elif damage=='dependency_table':db_session.execute(text('DROP TABLE observation_publication_dependencies'))
    elif damage=='revision_table':db_session.execute(text('DROP TABLE organization_publication_revisions'))
    elif damage=='guard_function':db_session.execute(text('DROP FUNCTION am_publication_affected(uuid,text,uuid)'))
    else:db_session.execute(text('ALTER TABLE assets DISABLE TRIGGER am_publication_source_guard'))
    db_session.commit()
    read=client.get(root+'/settings',headers=n['headers']);assert read.status_code==200,read.text
    assert not read.json()['available'] and not read.json()['enabled']
    assert client.patch(root+'/settings',headers=n['headers'],json={'expected_version':0,'enabled':True}).status_code==409
    assert client.post(obs+'/preview',headers=n['headers'],json={}).status_code==409


def test_stale_review_and_readonly_token_cannot_authorize_publish(client,db_session,native_preview):
    n=native_preview;enable(client,n);_,_,obs=paths(n)
    old=client.post(n['path'],headers=n['headers'],json={}).json();body=payload(dict(old,expected_version=0))
    assert client.post(obs+'/publish',headers=n['headers'],json=body).status_code==409
    body=payload(prepare(client,n))
    assert client.patch(n['base']+f"/findings/{n['finding_id']}/workflow",headers=n['headers'],json={'expected_version':0,'rationale':'Concurrent review note'}).status_code==200
    assert client.post(obs+'/publish',headers=n['headers'],json=body).status_code==409
    assert db_session.scalar(select(func.count()).select_from(Decision))==0


@pytest.mark.parametrize('change',[{'confirm':False},{'confirm':'true'},{'replacement':{'severity':'low'}},{'allow_writes':True}])
def test_confirm_and_payload_are_strict(client,db_session,native_preview,change):
    n=native_preview;enable(client,n);_,_,obs=paths(n);body={**payload(prepare(client,n)),**change}
    response=client.post(obs+'/publish',headers=n['headers'],json=body);assert response.status_code==422,response.text
    assert db_session.scalar(select(func.count()).select_from(Decision))==0


def test_consumer_failure_rolls_back_entire_public_request(client,db_session,native_preview,monkeypatch):
    n=native_preview;enable(client,n);_,_,obs=paths(n);body=payload(prepare(client,n));original=publication_consumers._invalidate
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('Injected public consumer failure')
    monkeypatch.setattr(publication_consumers,'_invalidate',fail)
    with pytest.raises(RuntimeError):client.post(obs+'/publish',headers=n['headers'],json=body)
    assert db_session.get(Finding,n['finding_id'],populate_existing=True).severity.value=='medium'
    assert db_session.scalar(select(func.count()).select_from(Decision))==0
    assert publication_consumers.revision(db_session,n['org'])==0
