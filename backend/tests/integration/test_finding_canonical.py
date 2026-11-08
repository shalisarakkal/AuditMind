"""Canonical designation never consumes the independent source histories."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision as Decision
from app.models.finding_history import FindingHistory
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import IdentityTool
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import member, register
from tests.integration.test_identity_bindings import prepared  # noqa: F401
from tests.integration.test_identity_comparison import pair  # noqa: F401

pytestmark = requires_db


@pytest.fixture
def conflict(client, db_session, pair):
    h, org, base, source, target, _, binding = pair
    separate = Finding(org_id=UUID(org), source="nessus", domain="network_config", severity="high",
        description="Second canonical candidate", scan_id=target.scan_id,
        asset_id=UUID(target.asset_identity["asset_id"]))
    db_session.add(separate); db_session.flush()
    target.finding_id = separate.id; db_session.commit()
    path = f"{base}/findings/{separate.id}/observations/{target.id}/identity-binding"
    assert client.put(path, headers=h, json=binding).status_code == 200
    for finding_id, values in ((source.finding_id, dict(rationale="Earlier independent rationale")),
            (target.finding_id, dict(status="resolved", rationale="Later independent rationale", verification="Source verification assertion"))):
        response = client.patch(f"{base}/findings/{finding_id}/workflow", headers=h, json=dict(expected_version=0, **values))
        assert response.status_code == 200, response.text
    return h, org, base, source, target, path, binding


def preview(client, conflict):
    return client.post(conflict[5] + "/canonical/preview", headers=conflict[0],
        json=dict(source_observation_id=str(conflict[3].id)))


def payload(conflict, body):
    return dict(source_observation_id=str(conflict[3].id), canonical_finding_id=str(conflict[3].finding_id),
        expected_version=body["expected_version"], review_token=body["review_token"],
        confirm_histories=True, rationale="Reviewed both independent decisions; designate reference")


def test_preview_select_revoke_preserves_both_records_and_all_histories(client, db_session, conflict):
    result = preview(client, conflict)
    assert result.status_code == 200, result.text
    body = result.json()
    states = body["context"]["findings"]
    assert {row["workflow"]["status"] for row in states} == {"open", "resolved"}
    assert {row["workflow"]["latest_rationale"]["text"] for row in states} == {"Earlier independent rationale", "Later independent rationale"}
    assert body["expected_version"] == 0
    assert db_session.query(Decision).count() == 0
    histories = db_session.query(FindingHistory).count()
    observations = [(o.id, o.finding_id) for o in db_session.scalars(select(FindingObservation))]
    response = client.post(conflict[5] + "/canonical", headers=conflict[0], json=payload(conflict, body))
    assert response.status_code == 200, response.text
    decision = response.json()
    assert decision["version"] == 1 and decision["current"] is None
    current = preview(client, conflict).json()
    assert current["saved"]["current"] is True
    assert db_session.query(FindingHistory).count() == histories
    assert [(o.id, o.finding_id) for o in db_session.scalars(select(FindingObservation))] == observations
    assert db_session.get(Finding, conflict[3].finding_id).archived_at is None
    assert db_session.get(Finding, conflict[4].finding_id).archived_at is None
    listed = client.get(f"{conflict[2]}/findings/{conflict[4].finding_id}/canonical-decisions", headers=conflict[0])
    assert listed.status_code == 200 and len(listed.json()) == 1
    revoked = client.post(f"{conflict[2]}/canonical-decisions/{decision['id']}/revoke", headers=conflict[0],
        json=dict(expected_version=1, rationale="Withdraw the designation"))
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["version"] == 2 and revoked.json()["state"] == "revoked"
    assert preview(client, conflict).json()["saved"]["current"] is False


@pytest.mark.parametrize("change", ["workflow", "verification", "asset", "scan", "finding", "tool", "observation"])
def test_stale_context_never_saves(client, db_session, conflict, change):
    body = preview(client, conflict).json()
    source, target = conflict[3:5]
    finding = db_session.get(Finding, target.finding_id)
    if change == "workflow":
        response=client.patch(f"{conflict[2]}/findings/{target.finding_id}/workflow", headers=conflict[0],
            json=dict(expected_version=1, rationale="Changed after preview"))
        assert response.status_code == 200
    elif change == "verification":
        finding.risk_verification_version += 1
    elif change == "asset":
        db_session.get(Asset, UUID(target.asset_identity["asset_id"])).hostname = "changed-host"
    elif change == "scan":
        db_session.get(Scan, target.scan_id).archived_at = datetime.now(timezone.utc)
    elif change == "finding":
        finding.archived_at = datetime.now(timezone.utc)
    elif change == "tool":
        db_session.get(IdentityTool, UUID(conflict[6]["tool_id"])).active = False
    else:
        target.source_identity = {**target.source_identity, "port": 12345}
    db_session.commit()
    response=client.post(conflict[5]+"/canonical", headers=conflict[0], json=payload(conflict,body))
    assert response.status_code == 409, response.text
    assert db_session.query(Decision).count() == 0


def test_replay_wrong_survivor_and_unconfirmed_preview_are_rejected(client, db_session, conflict):
    body=preview(client,conflict).json()
    for edit, status in ((dict(confirm_histories=False),422), (dict(canonical_finding_id=str(uuid4())),422),
                         (dict(review_token="0"*64),409), (dict(expected_version=5),409)):
        response=client.post(conflict[5]+"/canonical",headers=conflict[0],json={**payload(conflict,body),**edit})
        assert response.status_code == status, response.text
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code == 200
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code == 409
    assert db_session.query(Decision).count() == 1


@pytest.mark.parametrize("role", ["viewer", "auditor"])
def test_permissions_and_foreign_organization(client, conflict, role):
    body=preview(client,conflict).json()
    other=member(client,conflict[0],conflict[1],role)
    assert client.post(conflict[5]+"/canonical/preview",headers=other,
        json=dict(source_observation_id=str(conflict[3].id))).status_code == 200
    assert client.post(conflict[5]+"/canonical",headers=other,json=payload(conflict,body)).status_code == 403
    foreign=register(client,f"canonical-{role}@elsewhere.example")
    assert client.post(conflict[5]+"/canonical/preview",headers=foreign,
        json=dict(source_observation_id=str(conflict[3].id))).status_code == 403


def test_archive_restore_and_purge_never_rewrite_or_delete_receipt(client, db_session, conflict):
    body=preview(client,conflict).json()
    saved=client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).json()
    scan=db_session.get(Scan,conflict[4].scan_id)
    scan.archived_at=datetime.now(timezone.utc); db_session.commit()
    assert preview(client,conflict).status_code == 409
    scan.archived_at=None; db_session.commit()
    assert preview(client,conflict).json()["saved"]["current"] is True
    target_id=conflict[4].finding_id
    db_session.delete(db_session.get(Finding,target_id)); db_session.commit()
    rows=client.get(f"{conflict[2]}/findings/{target_id}/canonical-decisions",headers=conflict[0]).json()
    assert rows[0]["id"] == saved["id"]
    assert {state["workflow"]["status"] for state in rows[0]["context"]["findings"]} == {"open","resolved"}
    revoked=client.post(f"{conflict[2]}/canonical-decisions/{saved['id']}/revoke",headers=conflict[0],
        json=dict(expected_version=1,rationale="Withdraw after source purge"))
    assert revoked.status_code == 200


def test_context_change_during_preparation_cannot_capture_unreviewed_workflow(client, db_session, conflict, monkeypatch):
    from app.services import finding_canonical
    body=preview(client,conflict).json()
    original=finding_canonical._summary
    calls=0
    def raced(db, org_id, finding):
        nonlocal calls
        calls += 1
        if calls == 3:
            finding.description="Changed during canonical save"
            db.flush()
        return original(db,org_id,finding)
    monkeypatch.setattr(finding_canonical,"_summary",raced)
    response=client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body))
    assert response.status_code == 409, response.text
    assert db_session.query(Decision).count() == 0


def test_another_pair_cannot_create_canonical_chains(client, db_session, conflict):
    from datetime import timedelta
    body=preview(client,conflict).json()
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code == 200
    original=conflict[4]
    third=Finding(org_id=UUID(conflict[1]),source="nessus",domain="network_config",severity="medium",description="Third duplicate")
    db_session.add(third); db_session.flush()
    obs=FindingObservation(id=uuid4(),org_id=UUID(conflict[1]),finding_id=third.id,
        scan_id=original.scan_id,import_id=uuid4(),occurrence=1,source_row=1,source="nessus",scan_type="nessus",
        recorded_at=original.recorded_at+timedelta(seconds=1),asset_identity=original.asset_identity,
        source_identity=original.source_identity,payload=original.payload,reconciliation_eligible=False,ineligibility_reasons=[])
    db_session.add(obs); db_session.commit()
    path=f"{conflict[2]}/findings/{third.id}/observations/{obs.id}/identity-binding"
    assert client.put(path,headers=conflict[0],json=conflict[6]).status_code == 200
    response=client.post(path+"/canonical/preview",headers=conflict[0],json=dict(source_observation_id=str(conflict[3].id)))
    assert response.status_code == 409, response.text
    assert "another canonical selection" in response.text


def test_simultaneous_admins_have_one_versioned_winner(client, db_session, conflict):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from sqlalchemy import text
    from fastapi import HTTPException
    from app.api.deps import authorize_org_write
    from app.models.membership import OrgMembership
    from app.models.enums import UserRole
    from app.schemas.identity_binding import CanonicalSelection
    from app.services.finding_canonical import save
    body=preview(client,conflict).json()
    actor=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==UUID(conflict[1])))
    engine=db_session.get_bind(); db_session.commit()
    barrier=Barrier(2)
    def submit(_):
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            barrier.wait(timeout=10)
            try:
                authorize_org_write(db,UUID(conflict[1]),actor,(UserRole.admin,))
                save(db,UUID(conflict[1]),db.get(FindingObservation,conflict[4].id),actor,CanonicalSelection(**payload(conflict,body)))
                return 200
            except HTTPException as exc:
                db.rollback(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit,range(2))) == [200,409]
    assert db_session.query(Decision).count() == 1


def test_real_archive_restore_purge_keeps_independent_receipt(client, db_session, conflict):
    body=preview(client,conflict).json()
    saved=client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).json()
    target_id=conflict[4].finding_id
    def archive():
        response=client.post(f"{conflict[2]}/scans/{conflict[4].scan_id}/archive",headers=conflict[0])
        assert response.status_code == 200, response.text
        items=client.get(conflict[2]+"/archive",headers=conflict[0]).json()["items"]
        return next(row["id"] for row in items if row["item_id"]==str(conflict[4].scan_id))
    batch=archive()
    assert preview(client,conflict).status_code == 409
    restored=client.post(f"{conflict[2]}/archive/{batch}/restore",headers=conflict[0])
    assert restored.status_code == 200, restored.text
    assert preview(client,conflict).json()["saved"]["current"] is True
    batch=archive()
    purged=client.post(f"{conflict[2]}/archive/{batch}/purge",headers=conflict[0])
    assert purged.status_code == 200, purged.text
    assert db_session.get(Finding,target_id) is None
    assert db_session.get(Decision,UUID(saved["id"])) is not None
    rows=client.get(f"{conflict[2]}/findings/{target_id}/canonical-decisions",headers=conflict[0]).json()
    assert rows[0]["id"]==saved["id"]


def test_repeated_import_makes_old_review_stale_without_transferring_it(client, db_session, conflict):
    from tests.helpers import FIXTURES,upload
    body=preview(client,conflict).json()
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code == 200
    response=upload(client,conflict[2]+"/findings/import",conflict[0],"another.nessus",
        (FIXTURES/"sample.nessus").read_bytes()+b"\n<!-- third occurrence -->")
    assert response.status_code == 201, response.text
    result=preview(client,conflict)
    assert result.status_code == 200,result.text
    assert result.json()["saved"]["current"] is False
    assert db_session.query(Decision).count() == 1


def test_recorded_scoring_approval_is_visible_but_never_transferred(client, db_session, conflict):
    from app.models.finding_verification import FindingVerification
    from app.models.membership import OrgMembership
    actor=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==UUID(conflict[1])))
    target=db_session.get(Finding,conflict[4].finding_id)
    target.risk_verification_version=1; target.risk_verification_state="approved"
    db_session.add(FindingVerification(org_id=UUID(conflict[1]),finding_id=target.id,version=1,
        workflow_version=target.workflow_version,workflow_status="resolved",state="approved",
        source_reference="Synthetic retained observation",observed_at=datetime.now(timezone.utc),
        source_observation_count=1,submitter_id=actor,submitter_label="Reviewer",actor_id=actor,
        actor_label="Reviewer",note="Independent recorded approval",created_at=datetime.now(timezone.utc),attestation={}))
    db_session.commit()
    body=preview(client,conflict).json()
    assert next(row for row in body["context"]["findings"] if row["id"]==str(target.id))["verification"]["note"]=="Independent recorded approval"
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code == 200
    db_session.refresh(target)
    source=db_session.get(Finding,conflict[3].finding_id);db_session.refresh(source)
    assert target.risk_verification_state=="approved"
    assert source.risk_verification_state=="unverified"
    assert db_session.query(FindingVerification).count()==1


def test_archived_org_cannot_save_and_stale_revocations_cannot_append(client, db_session, conflict):
    from app.models.organization import Organization
    body=preview(client,conflict).json()
    org=db_session.get(Organization,UUID(conflict[1]));org.archived_at=datetime.now(timezone.utc);db_session.commit()
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code==409
    org.archived_at=None;db_session.commit()
    saved=client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).json()
    path=f"{conflict[2]}/canonical-decisions/{saved['id']}/revoke"
    request=dict(expected_version=1,rationale="Withdraw recorded choice")
    assert client.post(path,headers=conflict[0],json={**request,"expected_version":0}).status_code==409
    assert client.post(path,headers=conflict[0],json=request).status_code==200
    assert client.post(path,headers=conflict[0],json=request).status_code==409
    assert db_session.query(Decision).count()==2


def _disjoint_pair(client, db_session, conflict):
    from app.models.enums import ScanStatus
    original=conflict[4]
    material=[]
    for number in (2,3):
        captured=Asset(org_id=UUID(conflict[1]),type="server",hostname=f"disjoint-{number}")
        scan=Scan(org_id=UUID(conflict[1]),scan_type="nessus",status=ScanStatus.completed,
            completed_at=datetime.now(timezone.utc),source="upload",filename=f"disjoint-{number}.nessus",
            ingestion_config_fingerprint=db_session.get(Scan,original.scan_id).ingestion_config_fingerprint)
        db_session.add_all([captured,scan]);db_session.flush()
        finding=Finding(org_id=UUID(conflict[1]),source="nessus",domain="network_config",severity="high",
            description=f"Disjoint native {number}",asset_id=captured.id,scan_id=scan.id)
        db_session.add(finding);db_session.flush()
        obs=FindingObservation(id=uuid4(),org_id=UUID(conflict[1]),finding_id=finding.id,scan_id=scan.id,
            import_id=scan.id,occurrence=1,source_row=1,source="nessus",scan_type="nessus",
            recorded_at=datetime.now(timezone.utc),asset_identity=dict(asset_id=str(captured.id),hostname=captured.hostname),
            source_identity=original.source_identity,payload=original.payload,reconciliation_eligible=False,ineligibility_reasons=[])
        db_session.add(obs);db_session.commit()
        path=f"{conflict[2]}/findings/{finding.id}/observations/{obs.id}/identity-binding"
        assert client.put(path,headers=conflict[0],json=conflict[6]).status_code==200
        material.append((finding,obs,path))
    return material


def test_same_identity_cannot_select_disjoint_pairs_until_explicit_revocation(client, db_session, conflict):
    body=preview(client,conflict).json()
    first=client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).json()
    a,b=_disjoint_pair(client,db_session,conflict)
    response=client.post(b[2]+"/canonical/preview",headers=conflict[0],json=dict(source_observation_id=str(a[1].id)))
    assert response.status_code==409,response.text
    assert response.json()["detail"]["canonical_finding_id"]==str(conflict[3].finding_id)
    assert response.json()["detail"]["decision_id"]==first["id"]
    assert client.post(f"{conflict[2]}/canonical-decisions/{first['id']}/revoke",headers=conflict[0],
        json=dict(expected_version=1,rationale="Clear first explicit identity designation")).status_code==200
    fresh=client.post(b[2]+"/canonical/preview",headers=conflict[0],json=dict(source_observation_id=str(a[1].id)))
    assert fresh.status_code==200,fresh.text


def test_superseded_identity_version_is_not_treated_as_an_active_selection(client, db_session, conflict):
    body=preview(client,conflict).json()
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code==200
    a,b=_disjoint_pair(client,db_session,conflict)
    tool=client.post(conflict[2]+"/identity-tools",headers=conflict[0],json=dict(name="Re-reviewed scanner",rationale="Independent reviewed namespace")).json()
    for obs in conflict[3:5]:
        path=f"{conflict[2]}/findings/{obs.finding_id}/observations/{obs.id}/identity-binding"
        assert client.put(path,headers=conflict[0],json={**conflict[6],"expected_version":1,"tool_id":tool["id"]}).status_code==200
    changed=preview(client,conflict)
    assert changed.status_code==200,changed.text
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,changed.json())).status_code==200
    # The first pair's old scanner decision is superseded, not an active blocker.
    candidate=client.post(b[2]+"/canonical/preview",headers=conflict[0],json=dict(source_observation_id=str(a[1].id)))
    assert candidate.status_code==200,candidate.text


def test_unknown_legacy_identity_blocks_other_pairs_until_reviewed(client, db_session, conflict):
    body=preview(client,conflict).json()
    assert client.post(conflict[5]+"/canonical",headers=conflict[0],json=payload(conflict,body)).status_code==200
    prior=db_session.scalar(select(Decision));prior.context={key:value for key,value in prior.context.items() if key!="candidate_key"};db_session.commit()
    a,b=_disjoint_pair(client,db_session,conflict)
    response=client.post(b[2]+"/canonical/preview",headers=conflict[0],json=dict(source_observation_id=str(a[1].id)))
    assert response.status_code==409,response.text


def test_many_revoked_historical_pairs_do_not_permanently_block_new_review(client, db_session, conflict):
    import copy
    body=preview(client,conflict).json()
    for _ in range(101):
        a,b=sorted((uuid4(),uuid4()),key=str)
        context=copy.deepcopy(body["context"])
        for state,identifier in zip(context["findings"],(a,b)):
            state["id"]=str(identifier);state["workflow"]["finding_id"]=str(identifier)
        for version,state in ((1,"selected"),(2,"revoked")):
            db_session.add(Decision(org_id=UUID(conflict[1]),pair_key=f"{a}:{b}",finding_a_id=a,finding_b_id=b,
                canonical_finding_id=a,source_observation_id=uuid4(),target_observation_id=uuid4(),version=version,
                state=state,context=context,rationale="Retained historical decision",actor_label="Historical admin"))
    db_session.commit()
    response=preview(client,conflict)
    assert response.status_code==200,response.text
