import uuid
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select, func, delete, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_suppression import FindingSuppression, FindingSuppressionDecision, FindingSuppressionReappearance
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.models.session import PlatformSetting
from app.models.dashboard_snapshot import DashboardSnapshot
from app.models.finding_identity_binding import ObservationIdentityBinding
from app.models.enums import UserRole
from app.schemas.finding_suppression import SuppressionWrite
from app.services.finding_suppressions import decide, revision
from app.services.org_lock import lock_org
from app.services.report_service import create_rule_based_test_report
from tests.helpers import register, first_org_id, member, upload, run_worker
from tests.conftest import requires_db
from tests.integration.test_scan_snapshots import _nessus, _bind_observation

pytestmark = requires_db


@pytest.fixture
def native(client, db_session):
    headers = register(client, "suppression-api@example.io")
    org = first_org_id(client, headers)
    owner = (headers, org)
    response = upload(client, f"/api/v1/orgs/{org}/findings/import", headers, "baseline.nessus", _nessus("1001"))
    assert response.status_code == 201, response.text
    scan_id = response.json()["scan_id"]
    observation = db_session.scalar(select(FindingObservation).where(FindingObservation.scan_id == uuid.UUID(scan_id)))
    tool = client.post(f"/api/v1/orgs/{org}/identity-tools", headers=headers,
        json=dict(name="Reviewed scanner", rationale="Synthetic local test")).json()["id"]
    _bind_observation(client, owner, db_session, scan_id, tool, observation.asset_identity["asset_id"])
    return dict(headers=headers, org=org, finding=str(observation.finding_id), scan=scan_id, tool=tool,
        observation=str(observation.id), asset=observation.asset_identity["asset_id"])


def root(n): return f"/api/v1/orgs/{n['org']}/finding-suppressions"


def preview(client, n, action="suppress", suppression_id=None, headers=None):
    target = dict(action=action, **({"finding_id":n["finding"]} if action=="suppress" else {"suppression_id":suppression_id}))
    response = client.post(root(n)+"/preview", headers=headers or n["headers"], json=target)
    assert response.status_code == 200, response.text
    return {**target, **{key:response.json()[key] for key in ("review_token","expected_version")},
        "request_id":str(uuid.uuid4()), "rationale":"Reviewed visibility decision", "confirm":True}


def suppress(client,n):
    response=client.post(root(n)+"/decisions",headers=n["headers"],json=preview(client,n))
    assert response.status_code==200,response.text
    return response.json()["suppression_id"]


def test_suppression_is_atomic_visible_counts_scoring_and_clear(client,db_session,native):
    n=native;base=f"/api/v1/orgs/{n['org']}"
    report=create_rule_based_test_report(db_session,uuid.UUID(n['org']),"Before suppression")
    snapshot=report.data.copy()
    assert client.get(base+"/findings",headers=n["headers"]).json()["total"]==1
    patch=preview(client,n)
    response=client.post(root(n)+"/decisions",headers=n["headers"],json=patch)
    assert response.status_code==200,response.text
    identifier=response.json()["suppression_id"]
    repeated=client.post(root(n)+"/decisions",headers=n["headers"],json=patch)
    assert repeated.status_code==200 and repeated.json()["replayed"] is True
    assert db_session.scalar(select(func.count(FindingSuppressionDecision.id)))==1
    assert client.get(base+"/findings",headers=n["headers"]).json()["total"]==0
    facets=client.get(base+"/findings/facets",headers=n["headers"]).json()
    assert "nessus" not in facets["source"]
    dashboard=client.get(base+"/dashboard",headers=n["headers"]).json()
    assert dashboard["overall_score"] is None and dashboard["top_findings"]==[]
    assert dashboard["status_scoring"]["suppressed_findings"]==1
    assert dashboard["status_scoring"]["excluded_findings"]==0
    assert dashboard["status_scoring"]["recorded_findings"]==1
    with pytest.raises(ValueError,match="Not assessed"):
        create_rule_based_test_report(db_session,uuid.UUID(n['org']),"All hidden")
    db_session.expire_all()
    assert db_session.get(type(report),report.id).data==snapshot
    finding=db_session.get(Finding,uuid.UUID(n['finding']))
    assert finding.workflow_status=="open" and finding.workflow_version==0 and finding.archived_at is None
    clear=client.post(root(n)+"/decisions",headers=n["headers"],json=preview(client,n,"clear",identifier))
    assert clear.status_code==200,clear.text
    assert client.get(base+"/findings",headers=n["headers"]).json()["total"]==1
    assert client.get(base+"/dashboard",headers=n["headers"]).json()["overall_score"] is not None
    assert len(client.get(root(n)+f"/{identifier}/history",headers=n["headers"]).json()["items"])==2


@pytest.mark.parametrize("role,code",[("viewer",403),("auditor",200)])
def test_suppress_roles_and_admin_only_clear(client,db_session,native,role,code):
    n=native;headers=member(client,n['headers'],n['org'],role)
    response=client.post(root(n)+"/decisions",headers=headers,json=preview(client,n))
    assert response.status_code==code,response.text
    if code==200:
        patch=preview(client,n,"clear",response.json()["suppression_id"])
        assert client.post(root(n)+"/decisions",headers=headers,json=patch).status_code==403
        assert client.post(root(n)+"/decisions",headers=n['headers'],json=patch).status_code==200


def test_stale_identity_workflow_and_payload_validation(client,db_session,native):
    n=native;patch=preview(client,n)
    finding=db_session.get(Finding,uuid.UUID(n['finding']))
    finding.workflow_version+=1;db_session.commit()
    assert client.post(root(n)+"/decisions",headers=n['headers'],json=patch).status_code==409
    patch=preview(client,n)
    revoke=client.post(f"/api/v1/orgs/{n['org']}/findings/{n['finding']}/observations/{n['observation']}/identity-binding/revoke",
        headers=n['headers'],json=dict(expected_version=1,rationale="Withdraw reviewed mapping"))
    assert revoke.status_code==200,revoke.text
    assert client.post(root(n)+"/decisions",headers=n['headers'],json=patch).status_code==409
    for change in (dict(confirm=False),dict(rationale=" "),dict(review_token="x")):
        response=client.post(root(n)+"/decisions",headers=n['headers'],json={**patch,**change})
        assert response.status_code==422
    assert db_session.scalar(select(func.count(FindingSuppression.id)))==0


def test_foreign_targets_and_unsupported_sources(client,db_session,native):
    n=native;other=register(client,"suppression-foreign-api@example.io")
    patch=preview(client,n)
    assert client.post(root(n)+"/decisions",headers=other,json=patch).status_code==403
    foreign_org=first_org_id(client,other)
    response=client.post(f"/api/v1/orgs/{foreign_org}/finding-suppressions/preview",headers=other,
        json=dict(action="suppress",finding_id=n['finding']))
    assert response.status_code==404
    finding=db_session.get(Finding,uuid.UUID(n['finding']))
    db_session.execute(delete(ObservationIdentityBinding));db_session.commit()
    assert client.post(root(n)+"/preview",headers=n['headers'],json=dict(action="suppress",finding_id=str(finding.id))).status_code==409


def test_busy_import_rejects_without_waiting_and_workflow_unchanged(client,db_session,native):
    n=native;patch=preview(client,n)
    with Session(db_session.get_bind()) as publication:
        lock_org(publication,uuid.UUID(n['org']))
        db_session.execute(text("SET LOCAL lock_timeout='1s'"))
        response=client.post(root(n)+"/decisions",headers=n['headers'],json=patch)
        assert response.status_code==409,response.text
        assert "busy" in response.text.lower()
        publication.rollback()
    assert db_session.get(Finding,uuid.UUID(n['finding'])).suppression_id is None


def test_unreviewed_reappearance_stays_visible_and_receipt_survives_source_purge(client,db_session,native):
    n=native;identifier=suppress(client,n)
    response=upload(client,f"/api/v1/orgs/{n['org']}/findings/import",n['headers'],"reappeared.nessus",_nessus("1001"))
    assert response.status_code==201,response.text
    assert response.json()["report"]["created"]==1
    listed=client.get(f"/api/v1/orgs/{n['org']}/findings",headers=n['headers']).json()
    assert listed["total"]==1 and listed["items"][0]["id"]!=n['finding']
    source=client.get(root(n)+f"/{identifier}/reappearances",headers=n['headers']).json()
    assert len(source["items"])==1 and source["items"][0]["state"]=="needs_identity_review"
    # Clear refuses to resurrect an active legacy duplicate silently.
    assert client.post(root(n)+"/preview",headers=n['headers'],json=dict(action="clear",suppression_id=identifier)).status_code==409
    db_session.execute(delete(Scan).where(Scan.id==uuid.UUID(n['scan'])));db_session.commit()
    assert db_session.get(FindingSuppression,uuid.UUID(identifier)).state=="suppressed"
    assert client.post(root(n)+"/decisions",headers=n['headers'],json=preview(client,n,"clear",identifier)).status_code==200
    assert client.get(f"/api/v1/orgs/{n['org']}/findings",headers=n['headers']).json()["total"]==1
    assert db_session.get(Finding,uuid.UUID(n['finding'])) is None


def test_clear_does_not_require_retained_or_current_binding(client,db_session,native):
    n=native;identifier=suppress(client,n)
    client.post(f"/api/v1/orgs/{n['org']}/findings/{n['finding']}/observations/{n['observation']}/identity-binding/revoke",
        headers=n['headers'],json=dict(expected_version=1,rationale="Retired binding"))
    response=client.post(root(n)+"/decisions",headers=n['headers'],json=preview(client,n,"clear",identifier))
    assert response.status_code==200,response.text


def test_two_independent_reviewers_have_one_winner(client,db_session,native):
    n=native;patch=preview(client,n)
    org=uuid.UUID(n['org']);member_id=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==org))
    engine=db_session.get_bind();db_session.rollback();barrier=Barrier(2)
    def act(index):
        with Session(engine) as independent:
            member=independent.get(OrgMembership,{"user_id":member_id,"org_id":org})
            barrier.wait(timeout=10)
            try:
                decide(independent,org,member,SuppressionWrite(**{**patch,"request_id":uuid.uuid4()}))
                return 200
            except HTTPException as exc:
                independent.rollback();return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(act,range(2)))==[200,409]
    db_session.expire_all()
    assert db_session.scalar(select(func.count(FindingSuppressionDecision.id)))==1


def test_dashboard_snapshot_is_invalidated_atomically(client,db_session,native):
    from app.services.dashboard_snapshots import process
    n=native;org=uuid.UUID(n['org'])
    db_session.add(PlatformSetting(key="dashboard_snapshots",value=dict(enabled=True,refresh_interval_seconds=3600,version=1)))
    db_session.commit()
    client.get(f"/api/v1/orgs/{n['org']}/dashboard",headers=n['headers'])
    job=db_session.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id==org));process(db_session,job.id)
    assert client.get(f"/api/v1/orgs/{n['org']}/dashboard",headers=n['headers']).json().get("snapshot_state") is None
    suppress(client,n)
    pending=client.get(f"/api/v1/orgs/{n['org']}/dashboard",headers=n['headers']).json()
    assert pending["snapshot_state"]=="pending"
    process(db_session,job.id)
    current=client.get(f"/api/v1/orgs/{n['org']}/dashboard",headers=n['headers']).json()
    assert current["status_scoring"]["suppressed_findings"]==1
    assert current["top_findings"]==[] and current["overall_score"] is None


@pytest.mark.parametrize("clear_while_archived", [False, True])
def test_source_archive_restore_preserves_standing_suppression_and_history(client,db_session,native,clear_while_archived):
    n=native;identifier=suppress(client,n);base=f"/api/v1/orgs/{n['org']}"
    archived=client.post(base+f"/scans/{n['scan']}/archive",headers=n['headers'])
    assert archived.status_code in (200,202),archived.text
    run_worker()
    batch=archived.json()["batch_id"]
    if clear_while_archived:
        patch=preview(client,n,"clear",identifier)
        response=client.post(root(n)+"/decisions",headers=n['headers'],json=patch)
        assert response.status_code==200,response.text
    restored=client.post(base+f"/archive/{batch}/restore",headers=n['headers'])
    assert restored.status_code in (200,202),restored.text
    run_worker()
    db_session.expire_all()
    finding=db_session.get(Finding,uuid.UUID(n['finding']))
    assert finding is not None and finding.archived_at is None and finding.suppression_history_id is not None
    assert (finding.suppression_id is None)==clear_while_archived
    assert client.get(base+"/findings",headers=n['headers']).json()["total"]==int(clear_while_archived)
    assert db_session.get(FindingSuppression,uuid.UUID(identifier)) is not None


def test_reviewed_cleared_payload_restore_conflict_is_not_deleted_or_silently_duplicated(client,db_session,native):
    n=native;identifier=suppress(client,n);base=f"/api/v1/orgs/{n['org']}"
    assert client.post(root(n)+"/decisions",headers=n['headers'],json=preview(client,n,"clear",identifier)).status_code==200
    archived=client.post(base+f"/scans/{n['scan']}/archive",headers=n['headers']);run_worker()
    assert archived.status_code in (200,202),archived.text
    # Keep the old source asset present so the next upload's finding really has
    # the same legacy key as the reviewed archived payload.
    from app.models.asset import Asset
    asset=db_session.get(Asset,uuid.UUID(n['asset']));asset.archived_at=None;db_session.commit()
    response=upload(client,base+"/findings/import",n['headers'],"active-duplicate.nessus",_nessus("1001"))
    assert response.status_code==201,response.text
    restored=client.post(base+f"/archive/{archived.json()['batch_id']}/restore",headers=n['headers'])
    assert restored.status_code in (200,202),restored.text
    run_worker()
    from app.models.archive import ArchiveJob
    job=db_session.get(ArchiveJob,uuid.UUID(restored.json()['id']));db_session.refresh(job)
    assert job.status.value=="failed" and "Restore blocked" in job.summary["error"]
    original=db_session.get(Finding,uuid.UUID(n['finding']));db_session.refresh(original)
    assert original is not None and original.archived_at is not None
    assert db_session.scalar(select(func.count(Finding.id)))==2


def test_publication_failure_rolls_back_visibility_history_and_invalidation(client,db_session,native,monkeypatch):
    from app.services import finding_suppressions as service
    from app.services import evidence_jobs
    n=native;org=uuid.UUID(n['org']);patch=preview(client,n)
    before=evidence_jobs.revision(db_session,org)
    def fail(*args,**kwargs):raise RuntimeError("Synthetic activity persistence failure")
    monkeypatch.setattr(service,"record_event",fail)
    with pytest.raises(RuntimeError,match="Synthetic activity"):
        client.post(root(n)+"/decisions",headers=n['headers'],json=patch)
    db_session.expire_all()
    assert db_session.get(Finding,uuid.UUID(n['finding'])).suppression_id is None
    assert db_session.scalar(select(func.count(FindingSuppression.id)))==0
    assert db_session.scalar(select(func.count(FindingSuppressionDecision.id)))==0
    assert service.revision(db_session,org)==0
    assert evidence_jobs.revision(db_session,org)==before


def test_older_dashboard_capture_cannot_publish_over_new_suppression(client,db_session,native,monkeypatch):
    from app.services import dashboard_snapshots
    from app.api.routes import dashboard
    from app.services import finding_suppressions as service
    n=native;org=uuid.UUID(n['org']);patch=preview(client,n)
    db_session.add(PlatformSetting(key="dashboard_snapshots",value=dict(enabled=True,refresh_interval_seconds=3600,version=1)))
    db_session.commit()
    dashboard_snapshots.enqueue(db_session,org)
    job=db_session.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id==org));job_id=job.id
    original=dashboard.capture_inventory
    def capture_then_commit_suppression(org_id,snapshot):
        old=original(org_id,snapshot)
        with Session(db_session.get_bind()) as writer:
            membership=writer.scalar(select(OrgMembership).where(OrgMembership.org_id==org))
            service.decide(writer,org,membership,SuppressionWrite(**patch))
        return old
    monkeypatch.setattr(dashboard,"capture_inventory",capture_then_commit_suppression)
    dashboard_snapshots.process(db_session,job_id)
    db_session.expire_all();saved=db_session.get(DashboardSnapshot,job_id)
    assert saved.status=="pending" and saved.payload is None
    monkeypatch.setattr(dashboard,"capture_inventory",original)
    dashboard_snapshots.process(db_session,job_id)
    current=client.get(f"/api/v1/orgs/{n['org']}/dashboard",headers=n['headers']).json()
    assert current["top_findings"]==[] and current["status_scoring"]["suppressed_findings"]==1


def test_non_native_batches_do_not_add_suppression_queries():
    from unittest.mock import Mock
    from app.services.finding_suppressions import record_reappearances
    db=Mock()
    record_reappearances(db,uuid.uuid4(),[dict(scan_type="endpoint_agent_import",source="endpoint",profile="endpoint_agent")]*1000)
    db.execute.assert_not_called();db.scalars.assert_not_called()


def test_organization_purge_removes_source_and_ledger_without_trigger_or_fk_failure(client,db_session,native):
    from app.models.organization import Organization
    n=native;suppress(client,n)
    db_session.execute(delete(Organization).where(Organization.id==uuid.UUID(n['org'])))
    db_session.commit()
    for model in (Finding,FindingSuppression,FindingSuppressionDecision,FindingSuppressionReappearance):
        assert db_session.scalar(select(func.count()).select_from(model))==0


def test_large_target_text_is_bounded_but_suffix_edits_invalidate_preview(client,db_session,native):
    from sqlalchemy import update, inspect
    from app.services.finding_suppressions import _retained_finding
    n=native;identifier=uuid.UUID(n['finding'])
    db_session.execute(update(Finding).where(Finding.id==identifier).values(description="x"*20000+"A"));db_session.commit()
    first=preview(client,n)
    target=_retained_finding(db_session,uuid.UUID(n['org']),identifier)
    assert "description" in inspect(target).unloaded
    assert len(target._suppression_label)==500
    db_session.execute(update(Finding).where(Finding.id==identifier).values(description="x"*20000+"B"));db_session.commit()
    assert client.post(root(n)+"/decisions",headers=n['headers'],json=first).status_code==409


def test_all_suppressed_is_not_a_healthy_score_when_status_policy_is_off(client,db_session,native):
    n=native
    db_session.add(PlatformSetting(key="status_aware_scoring",value=dict(enabled=False,version=1)));db_session.commit()
    suppress(client,n)
    data=client.get(f"/api/v1/orgs/{n['org']}/dashboard",headers=n['headers']).json()
    assert data["overall_score"] is None
    assert data["status_scoring"]["enabled"] is False and data["status_scoring"]["all_suppressed"] is True


def test_standing_identity_can_be_explicitly_reapplied_after_source_purge(client,db_session,native):
    n=native;identifier=suppress(client,n)
    response=upload(client,f"/api/v1/orgs/{n['org']}/findings/import",n['headers'],"fresh-source.nessus",_nessus("1001"))
    assert response.status_code==201,response.text
    current_scan=response.json()["scan_id"]
    observation,key=_bind_observation(client,(n['headers'],n['org']),db_session,current_scan,n['tool'],n['asset'])
    db_session.execute(delete(Scan).where(Scan.id==uuid.UUID(n['scan'])));db_session.commit()
    new={**n,"finding":str(observation.finding_id)}
    result=client.post(root(n)+"/decisions",headers=n['headers'],json=preview(client,new))
    assert result.status_code==200,result.text
    assert result.json()["suppression_id"]==identifier and result.json()["version"]==2
    assert client.get(f"/api/v1/orgs/{n['org']}/findings",headers=n['headers']).json()["total"]==0
    assert db_session.get(FindingSuppression,uuid.UUID(identifier)).reappearance_count==1


def test_explicit_reapply_updates_reappearance_source_after_reviewed_asset_alias(client,db_session,native):
    from app.models.organization import Organization
    n=native;identifier=suppress(client,n);org_id=uuid.UUID(n['org'])
    renamed=_nessus("1001").replace(b"pilot-host",b"pilot-renamed-host").replace(b"10.0.0.10",b"10.0.0.44")
    imported=upload(client,f"/api/v1/orgs/{n['org']}/findings/import",n['headers'],"reviewed-alias.nessus",renamed)
    assert imported.status_code==201,imported.text
    observation,key=_bind_observation(client,(n['headers'],n['org']),db_session,imported.json()['scan_id'],n['tool'],n['asset'])
    new_asset=observation.asset_identity['asset_id'];assert new_asset!=n['asset']
    db_session.execute(delete(Scan).where(Scan.id==uuid.UUID(n['scan'])));db_session.commit()
    new={**n,"finding":str(observation.finding_id)}
    response=client.post(root(n)+"/decisions",headers=n['headers'],json=preview(client,new))
    assert response.status_code==200,response.text
    registry=db_session.get(FindingSuppression,uuid.UUID(identifier));db_session.refresh(registry)
    assert registry.identity['source_asset_id']==new_asset
    archived=client.post(f"/api/v1/orgs/{n['org']}/assets/{n['asset']}/archive",headers=n['headers'])
    assert archived.status_code in (200,202),archived.text
    run_worker()
    again=upload(client,f"/api/v1/orgs/{n['org']}/findings/import",n['headers'],"possible-new-source.nessus",renamed)
    assert again.status_code==201,again.text
    db_session.refresh(registry)
    assert registry.reappearance_count==1
    assert client.get(f"/api/v1/orgs/{n['org']}/findings",headers=n['headers']).json()['total']==1


@pytest.mark.parametrize('source_alias',[False,True])
def test_clear_refuses_multiple_retained_payloads_after_reapply_and_source_restore(client,db_session,native,source_alias):
    n=native;identifier=suppress(client,n);base=f"/api/v1/orgs/{n['org']}"
    content=_nessus('1001')
    if source_alias:
        content=content.replace(b'pilot-host',b'pilot-alias-host').replace(b'10.0.0.10',b'10.0.0.44')
    imported=upload(client,base+'/findings/import',n['headers'],'replacement.nessus',content)
    assert imported.status_code==201,imported.text
    observation,_=_bind_observation(client,(n['headers'],n['org']),db_session,imported.json()['scan_id'],n['tool'],n['asset'])
    archived=client.post(base+f"/scans/{n['scan']}/archive",headers=n['headers'])
    assert archived.status_code in (200,202),archived.text
    run_worker()
    if source_alias:
        # Retain the independently managed canonical asset while the older
        # source payload is archived (the binding does not recreate inventory).
        from app.models.asset import Asset
        db_session.get(Asset,uuid.UUID(n['asset'])).archived_at=None
        db_session.commit()
    replacement={**n,'finding':str(observation.finding_id)}
    decision=client.post(root(n)+'/decisions',headers=n['headers'],json=preview(client,replacement))
    assert decision.status_code==200,decision.text
    restored=client.post(base+f"/archive/{archived.json()['batch_id']}/restore",headers=n['headers'])
    assert restored.status_code in (200,202),restored.text
    run_worker()
    response=client.post(root(n)+'/preview',headers=n['headers'],json=dict(action='clear',suppression_id=identifier))
    assert response.status_code==409,response.text
    assert client.get(base+'/findings',headers=n['headers']).json()['total']==0
    # Archive the extra retained source, then clear the one current target.
    archived_again=client.post(base+f"/scans/{n['scan']}/archive",headers=n['headers'])
    assert archived_again.status_code in (200,202),archived_again.text
    run_worker()
    cleared=client.post(root(n)+'/decisions',headers=n['headers'],json=preview(client,replacement,'clear',identifier))
    assert cleared.status_code==200,cleared.text
    assert client.get(base+'/findings',headers=n['headers']).json()['total']==1
    # The old reviewed identity must not return as a duplicate, even when its
    # legacy source asset differs from the current target's reviewed alias.
    attempted=client.post(base+f"/archive/{archived_again.json()['batch_id']}/restore",headers=n['headers'])
    assert attempted.status_code in (200,202),attempted.text
    run_worker()
    from app.models.archive import ArchiveJob
    job=db_session.get(ArchiveJob,uuid.UUID(attempted.json()['id']));db_session.refresh(job)
    assert job.status.value=='failed' and 'Restore blocked' in job.summary['error']
    db_session.expire_all()
    assert db_session.get(Finding,uuid.UUID(n['finding'])).archived_at is not None
    assert db_session.scalar(select(func.count(Finding.id)))==2
    assert client.get(base+'/findings',headers=n['headers']).json()['total']==1
