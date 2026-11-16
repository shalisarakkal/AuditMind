import uuid
import pytest
from sqlalchemy import select,func,text,update,delete
from sqlalchemy.exc import IntegrityError
from app.models.asset import Asset
from app.models.asset_context import AssetContext,AssetContextHistory
from app.models.user import User
from app.models.membership import OrgMembership
from app.models.event import Event
from app.services import asset_context,list_pages
from tests.conftest import requires_db
from tests.helpers import register,first_org_id,member,upload
pytestmark=requires_db

@pytest.fixture
def context_asset(client,db_session):
    h=register(client,'context-admin@example.io');org=first_org_id(client,h);base=f'/api/v1/orgs/{org}/assets'
    r=client.post(base,headers=h,json={'type':'server','hostname':'managed-context.example','environment':'scanner-prod','criticality':'scanner-low'})
    assert r.status_code==201,r.text
    actor=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(org)))
    return dict(h=h,org=org,base=base,id=r.json()['id'],owner=str(actor),path=base+'/'+r.json()['id']+'/context')

def save(client,n,version=0,**fields):
    return client.patch(n['path'],headers=n['h'],json=dict(expected_version=version,rationale='Reviewed business context',**fields))

def test_unknown_defaults_versioned_save_noop_and_stale(client,db_session,context_asset):
    n=context_asset;before=client.get(n['path'],headers=n['h']);assert before.status_code==200,before.text
    assert before.json()['available'] and before.json()['version']==0 and before.json()['owner_status']=='unassigned'
    result=save(client,n,owner_id=n['owner'],environment=' Production ',business_criticality='critical');assert result.status_code==200,result.text
    data=result.json();assert data['version']==1 and data['environment']=='Production' and data['owner_status']=='active'
    assert data['owner_label']=='context-admin@example.io'
    same=save(client,n,1,owner_id=n['owner'],environment='Production',business_criticality='critical');assert same.status_code==200 and same.json()['version']==1
    assert db_session.scalar(select(func.count()).select_from(AssetContextHistory))==1
    assert save(client,n,environment='Stale').status_code==409
    clear=save(client,n,1,owner_id=None,environment=None,business_criticality=None);assert clear.status_code==200,clear.text
    assert clear.json()['version']==2 and clear.json()['owner_status']=='unassigned'
    assert save(client,n,environment='ABA').status_code==409
    history=client.get(n['path']+'/history',headers=n['h']);assert [x['version'] for x in history.json()]==[2,1]
    asset=db_session.get(Asset,uuid.UUID(n['id']),populate_existing=True)
    assert asset.environment=='scanner-prod' and asset.criticality=='scanner-low'
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.type=='asset_context_changed'))==2

@pytest.mark.parametrize('role',['auditor','viewer'])
def test_editor_roles_and_owner_does_not_grant_access(client,context_asset,role):
    n=context_asset;h=member(client,n['h'],n['org'],role)
    response=client.patch(n['path'],headers=h,json={'expected_version':0,'environment':'Reviewed','rationale':'Role test'})
    assert response.status_code==(200 if role=='auditor' else 403),response.text
    assert client.get(n['path'],headers=h).status_code==200

@pytest.mark.parametrize('payload',[{'environment':'x'*51},{'business_criticality':'maximum'},{'expected_version':True},{'rationale':' '},{'details':{}},{'environment':'line\nbreak'}])
def test_strict_validation(client,context_asset,payload):
    n=context_asset;response=client.patch(n['path'],headers=n['h'],json={'expected_version':0,'rationale':'Valid reason',**payload});assert response.status_code==422,response.text


def test_foreign_asset_and_owner_cannot_cross_tenant(client,context_asset,db_session):
    n=context_asset;foreign=register(client,'foreign-context@example.io');org=first_org_id(client,foreign)
    owner=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(org)))
    assert save(client,n,owner_id=str(owner)).status_code==422
    assert client.get(n['path'],headers=foreign).status_code==403
    assert client.get(f'/api/v1/orgs/{org}/assets/{n["id"]}/context',headers=foreign).status_code==404
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(AssetContext(asset_id=uuid.UUID(n['id']),org_id=uuid.UUID(org),version=1));db_session.flush()


def test_filters_counts_common_search_and_owner_rename(client,db_session,context_asset):
    n=context_asset
    for i in range(2):assert client.post(n['base'],headers=n['h'],json={'type':'server','hostname':f'unknown-{i}.example'}).status_code==201
    assert client.get(n['base']+'?managed_environment=Production',headers=n['h']).json()['total']==0
    stamp=list_pages.revision_stamp(db_session,uuid.UUID(n['org']),'assets');db_session.commit()
    assert save(client,n,owner_id=n['owner'],environment='Production',business_criticality='high').status_code==200
    assert list_pages.revision_stamp(db_session,uuid.UUID(n['org']),'assets')!=stamp
    for query,total in [('managed_environment=Production',1),('business_criticality=high',1),('managed_owner='+n['owner'],1),('managed_owner=',2),('managed_environment=',2),('q=Production',1)]:
        r=client.get(n['base']+'?'+query,headers=n['h']);assert r.status_code==200,r.text;assert r.json()['total']==total,(query,r.json())
    db_session.execute(update(User).where(User.id==uuid.UUID(n['owner'])).values(name='Unique Business Owner'));db_session.commit()
    r=client.get(n['base']+'?q=Unique%20Business%20Owner',headers=n['h']);assert r.status_code==200,r.text
    assert r.json()['total']==1 and r.json()['items'][0]['context']['owner_label']=='Unique Business Owner (context-admin@example.io)'
    facets=client.get(n['base']+'/context-facets',headers=n['h']);assert facets.status_code==200,facets.text
    assert facets.json()['managed_environment']==['Production'] and facets.json()['managed_owner_labels'][n['owner']]=='Unique Business Owner (context-admin@example.io)'
    assert client.get(n['base']+'?managed_owner=invalid',headers=n['h']).status_code==422


def test_atomic_rollback_and_context_not_rewritten_by_import(client,db_session,context_asset,monkeypatch):
    n=context_asset;stamp=list_pages.revision_stamp(db_session,uuid.UUID(n['org']),'assets');db_session.commit()
    original=asset_context.record_event
    def fail(*args,**kwargs):db_session.flush();raise RuntimeError('Injected after context/history flush')
    monkeypatch.setattr(asset_context,'record_event',fail)
    with pytest.raises(RuntimeError):save(client,n,environment='Must roll back')
    assert client.get(n['path'],headers=n['h']).json()['version']==0
    assert db_session.scalar(select(func.count()).select_from(AssetContextHistory))==0
    assert list_pages.revision_stamp(db_session,uuid.UUID(n['org']),'assets')==stamp
    monkeypatch.setattr(asset_context,'record_event',original)
    assert save(client,n,environment='Business production',business_criticality='critical').status_code==200
    content=b'type,hostname,environment,criticality\nserver,managed-context.example,scanner-new,scanner-high\n'
    r=upload(client,n['base']+'/import',n['h'],'context-source.csv',content);assert r.status_code==201,r.text
    data=client.get(n['path'],headers=n['h']).json();assert data['version']==1 and data['environment']=='Business production' and data['business_criticality']=='critical'


def test_membership_removal_retains_reference_and_invalidates_context_search(client,db_session,context_asset):
    n=context_asset;h=member(client,n['h'],n['org'],'viewer')
    owner=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(n['org']),OrgMembership.role=='viewer'))
    assert save(client,n,owner_id=str(owner)).status_code==200
    before=list_pages.revision_stamp(db_session,uuid.UUID(n['org']),'assets');db_session.commit()
    assert client.delete(f'/api/v1/orgs/{n["org"]}/members/{owner}',headers=n['h']).status_code==204
    data=client.get(n['path'],headers=n['h']).json();assert data['owner_status']=='former' and data['owner_id']==str(owner) and data['version']==1
    assert list_pages.revision_stamp(db_session,uuid.UUID(n['org']),'assets')!=before
    assert save(client,n,1,environment='Other context').status_code==200
    assert save(client,n,2,owner_id=None).status_code==200


def test_context_save_can_commit_while_scanner_update_is_uncommitted(client,db_session,context_asset):
    from sqlalchemy.orm import Session
    n=context_asset
    with Session(db_session.get_bind()) as scanner:
        scanner.execute(update(Asset).where(Asset.id==uuid.UUID(n['id'])).values(environment='Uncommitted scanner update'))
        db_session.execute(text("SET LOCAL lock_timeout='700ms'"))
        response=save(client,n,environment='Business context during import')
        assert response.status_code==200,response.text
        assert response.json()['version']==1
        scanner.rollback()
    assert client.get(n['path'],headers=n['h']).json()['environment']=='Business context during import'


@pytest.mark.parametrize('damage',['table','revision','guard'])
def test_pre_activation_and_partial_activation_fail_closed(client,db_session,context_asset,damage):
    n=context_asset
    if damage=='table':db_session.execute(text('DROP TABLE asset_context_history'))
    elif damage=='revision':db_session.execute(text('DROP TABLE organization_asset_context_revisions'))
    else:db_session.execute(text('ALTER TABLE asset_contexts DISABLE TRIGGER am_asset_context_guard'))
    db_session.commit()
    r=client.get(n['path'],headers=n['h']);assert r.status_code==200 and not r.json()['available']
    assert save(client,n,environment='Blocked').status_code==409
    page=client.get(n['base'],headers=n['h']);assert page.status_code==200,page.text
    assert not page.json()['items'][0]['context']['available']
    assert client.get(n['base']+'?managed_environment=Production',headers=n['h']).status_code==409


def test_archive_restore_preserves_context_and_purge_removes_only_its_history(client,context_asset):
    n=context_asset;root=f'/api/v1/orgs/{n["org"]}'
    assert save(client,n,environment='Retained business environment').status_code==200
    archived=client.post(n['base']+'/'+n['id']+'/archive',headers=n['h']);assert archived.status_code==200,archived.text
    record=client.get(root+'/archive',headers=n['h']).json()['items'][0]
    assert client.get(n['path'],headers=n['h']).json()['asset_archived']
    assert save(client,n,1,environment='Forbidden while archived').status_code==404
    restored=client.post(root+'/archive/'+record['id']+'/restore',headers=n['h']);assert restored.status_code==200,restored.text
    current=client.get(n['path'],headers=n['h']).json();assert not current['asset_archived'] and current['version']==1 and current['environment']=='Retained business environment'
    assert client.post(n['base']+'/'+n['id']+'/archive',headers=n['h']).status_code==200
    record=client.get(root+'/archive',headers=n['h']).json()['items'][0]
    assert client.post(root+'/archive/'+record['id']+'/purge',headers=n['h']).status_code==200
    assert client.get(n['path'],headers=n['h']).status_code==404
    assert client.get(n['path']+'/history',headers=n['h']).status_code==404


def test_retained_context_blocks_tenant_move_and_missing_generation(client,db_session,context_asset):
    from app.models.organization import Organization
    n=context_asset;assert save(client,n,environment='Reviewed').status_code==200
    other=Organization(name='Other owner');db_session.add(other);db_session.commit()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():db_session.execute(update(Asset).where(Asset.id==uuid.UUID(n['id'])).values(org_id=other.id))
    db_session.execute(delete(AssetContext).where(AssetContext.asset_id==uuid.UUID(n['id'])));db_session.commit()
    assert save(client,n,environment='Cannot reset version').status_code==409


def test_managed_metadata_does_not_invalidate_evidence_or_reweight_scores(client,db_session,context_asset):
    from app.services.evidence_jobs import revision
    n=context_asset;before=revision(db_session,uuid.UUID(n['org']));db_session.commit()
    assert save(client,n,business_criticality='critical').status_code==200
    assert revision(db_session,uuid.UUID(n['org']))==before


def test_platform_privilege_without_org_write_role_cannot_edit(client,db_session,context_asset):
    n=context_asset;h=member(client,n['h'],n['org'],'viewer')
    identifier=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(n['org']),OrgMembership.role=='viewer'))
    db_session.get(User,identifier).is_sysadmin=True;db_session.commit()
    assert client.patch(n['path'],headers=h,json={'expected_version':0,'environment':'Blocked','rationale':'Not an org writer'}).status_code==403


def test_context_metadata_reads_and_edits_do_not_load_imported_payloads(client,db_session,context_asset):
    from sqlalchemy import event
    n=context_asset;queries=[]
    def inspect_sql(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'FROM assets' in statement:queries.append(statement)
    engine=db_session.get_bind();event.listen(engine,'before_cursor_execute',inspect_sql)
    try:
        assert client.get(n['path'],headers=n['h']).status_code==200
        assert save(client,n,environment='Narrow metadata write').status_code==200
    finally:event.remove(engine,'before_cursor_execute',inspect_sql)
    assert queries and all('assets.details' not in sql and 'assets.tags' not in sql for sql in queries)



def test_two_reviewers_cannot_overwrite_the_same_context_generation(client,db_session,context_asset,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.schemas.asset_context import AssetContextPatch
    n=context_asset;member(client,n['h'],n['org'],'auditor')
    second=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(n['org']),OrgMembership.role=='auditor'));db_session.commit()
    held=Event();release=Event();attempted=Event();original=asset_context.record_event
    def hold(*args,**kwargs):
        if kwargs['actor'].id==uuid.UUID(n['owner']):
            held.set();assert release.wait(10),'Test did not release first writer'
        return original(*args,**kwargs)
    monkeypatch.setattr(asset_context,'record_event',hold)
    engine=db_session.get_bind()
    def write(actor,value):
        if actor==second:attempted.set()
        with Session(engine) as session:
            try:
                result=asset_context.save(session,uuid.UUID(n['org']),uuid.UUID(n['id']),actor,
                    AssetContextPatch(expected_version=0,environment=value,rationale='Concurrent context reviewer'))
                return 200,result.version
            except HTTPException as exc:return exc.status_code,None
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(write,uuid.UUID(n['owner']),'First reviewer')
        try:
            assert held.wait(10)
            other=pool.submit(write,second,'Second reviewer');assert attempted.wait(10)
        finally:release.set()
        assert first.result(timeout=10)==(200,1)
        assert other.result(timeout=10)==(409,None)
    result=client.get(n['path'],headers=n['h']).json();assert result['version']==1 and result['environment']=='First reviewer'
    assert db_session.scalar(select(func.count()).select_from(AssetContextHistory))==1


def test_owner_account_removal_keeps_reviewed_label_without_authority(client,db_session,context_asset):
    n=context_asset;member(client,n['h'],n['org'],'viewer')
    owner=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(n['org']),OrgMembership.role=='viewer'))
    assert save(client,n,owner_id=str(owner)).status_code==200
    label=client.get(n['path'],headers=n['h']).json()['owner_label']
    db_session.execute(delete(User).where(User.id==owner));db_session.commit()
    result=client.get(n['path'],headers=n['h']).json()
    assert result['owner_id']==str(owner) and result['owner_status']=='former' and result['owner_label']==label and result['version']==1
    assert client.get(n['path']+'/history',headers=n['h']).json()[0]['after']['owner_label']==label
