import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from threading import Barrier
from datetime import datetime, timedelta, timezone

import pytest
from app.models.enums import ScanStatus
from app.models.finding import Finding
from app.models.finding_history import FindingHistory
from app.models.scan import Scan
from app.models.scan_snapshot import ScanSnapshotDeclaration
from app.models.membership import OrgMembership
from app.models.enums import UserRole, ArchiveState, ArchiveItemType
from app.models.archive import ArchiveBatch
from app.schemas.scan_snapshot import SnapshotWrite
from app.services.scan_snapshots import write_snapshot
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register, upload

pytestmark = requires_db


@pytest.fixture
def owner(client):
    headers = register(client, "snapshots@example.io")
    return headers, first_org_id(client, headers)


def root(owner):
    return f"/api/v1/orgs/{owner[1]}/scans"


def imported(client, owner, **changes):
    row = {"hostname": "snapshot-host", "domain": "network_config", "severity": "high",
        "category": "RULE-1", "source": "snapshot-tool", **changes}
    response = upload(client, root(owner).replace('/scans','/findings/import'), owner[0], "snapshot.json", json.dumps([row]).encode())
    assert response.status_code == 201, response.text
    return response.json()["scan_id"]


def fields(**changes):
    return dict(expected_version=0, snapshot_kind="complete", tool_name="Scanner", tool_instance_id="scanner-1",
        tool_configuration_id="policy-v1", targets=["10.0.0.0/24"], exclusions=["10.0.0.20"],
        unreachable_targets=[], coverage_confirmed=True, rationale="Reviewed source scan coverage",
        source_snapshot_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(), **changes)


def declare(client, owner, scan_id, changes=None, status=200):
    payload = fields()
    payload.update(changes or {})
    response = client.put(f"{root(owner)}/{scan_id}/snapshot", headers=owner[0], json=payload)
    assert response.status_code == status, response.text
    return response.json()


def test_running_snapshot_rejects_promptly_with_import_foreign_keys(client,owner,db_session):
    from app.models.asset import Asset
    from app.models.archive import AssetScan
    identifier = uuid.UUID(imported(client,owner))
    scan=db_session.get(Scan,identifier)
    scan.status=ScanStatus.running
    db_session.commit()
    with Session(db_session.get_bind()) as publication:
        asset=Asset(org_id=uuid.UUID(owner[1]),type="server",hostname="snapshot-lock-test")
        publication.add(asset);publication.flush()
        publication.add(AssetScan(scan_id=identifier,asset_id=asset.id,created=True))
        publication.flush()
        db_session.execute(text("SET LOCAL lock_timeout='2s'"))
        response=client.put(f"{root(owner)}/{identifier}/snapshot",headers=owner[0],json=fields())
        assert response.status_code==409,response.text
        assert "scan_not_successfully_completed" in response.json()["detail"]["reasons"]
        publication.rollback()


def compare(client, owner, baseline, current, **changes):
    payload = dict(baseline_scan_id=baseline, current_scan_id=current, baseline_version=1, current_version=1)
    payload.update(changes)
    return client.post(f"{root(owner)}/snapshot-comparison", headers=owner[0], json=payload)


def test_matching_declarations_are_not_absence_authority_and_preserve_finding(client, owner, db_session):
    a, b = imported(client, owner), imported(client, owner, severity="critical")
    finding = db_session.query(Finding).one()
    workflow = {"status": finding.workflow_status, "version": finding.workflow_version,
        "severity": finding.severity, "archived_at": finding.archived_at, "scan_id": finding.scan_id}
    for scan_id in (a,b):
        view = declare(client, owner, scan_id)
        assert len(view["scan"]["ingestion_config_fingerprint"]) == 64
        assert view["declaration"]["actor_label"]
    response = compare(client, owner, a, b)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["declared_metadata_matches"] is True
    assert result["absence_eligible"] is False and result["review_candidates"] == []
    assert result["baseline_unreviewable_observations"] == 1
    assert result["current_unreviewable_observations"] == 1
    assert "current:unreviewable_observations_present" in result["absence_blockers"]
    assert result["baseline"]["scan"]["id"] == a and result["current"]["scan"]["id"] == b
    assert result["scope_differences"]["baseline_exclusions"] == ["10.0.0.20"]
    assert result["blocking_reasons"] == []
    assert response.headers["Cache-Control"] == "no-store"
    db_session.refresh(finding)
    assert workflow == {"status": finding.workflow_status, "version": finding.workflow_version,
        "severity": finding.severity, "archived_at": finding.archived_at, "scan_id": finding.scan_id}
    assert db_session.query(FindingHistory).count() == 0


def _nessus(plugin_id):
    return f"""<NessusClientData_v2><Report name="synthetic">
      <ReportHost name="pilot-host"><HostProperties><tag name="host-ip">10.0.0.10</tag></HostProperties>
        <ReportItem port="443" protocol="tcp" severity="2" pluginID="{plugin_id}" pluginName="Synthetic finding" pluginFamily="Test">
          <risk_factor>Medium</risk_factor><synopsis>Synthetic test finding.</synopsis>
        </ReportItem>
      </ReportHost></Report></NessusClientData_v2>""".encode()


def _nessus_two_hosts(plugin_id):
    return f"""<NessusClientData_v2><Report name="synthetic">
      <ReportHost name="pilot-a"><HostProperties><tag name="host-ip">10.0.0.10</tag></HostProperties>
        <ReportItem port="443" protocol="tcp" severity="2" pluginID="{plugin_id}" pluginName="Synthetic finding" pluginFamily="Test">
          <risk_factor>Medium</risk_factor><synopsis>Synthetic test finding.</synopsis>
        </ReportItem>
      </ReportHost>
      <ReportHost name="pilot-b"><HostProperties><tag name="host-ip">10.0.0.11</tag></HostProperties>
        <ReportItem port="443" protocol="tcp" severity="2" pluginID="{plugin_id}" pluginName="Synthetic finding" pluginFamily="Test">
          <risk_factor>Medium</risk_factor><synopsis>Synthetic test finding.</synopsis>
        </ReportItem>
      </ReportHost></Report></NessusClientData_v2>""".encode()


def _nessus_many(plugin_ids):
    items = "".join(
        f'<ReportItem port="443" protocol="tcp" severity="2" pluginID="{plugin_id}" '
        f'pluginName="Synthetic finding {plugin_id}" pluginFamily="Test">'
        '<risk_factor>Medium</risk_factor><synopsis>Synthetic finding.</synopsis></ReportItem>'
        for plugin_id in plugin_ids
    )
    return f"""<NessusClientData_v2><Report name="synthetic">
      <ReportHost name="pilot-host"><HostProperties><tag name="host-ip">10.0.0.10</tag></HostProperties>
        {items}
      </ReportHost></Report></NessusClientData_v2>""".encode()


def _bind_observation(client, owner, db_session, scan_id, tool_id, canonical_asset_id):
    from app.models.finding_observation import FindingObservation

    observation = db_session.query(FindingObservation).filter_by(scan_id=uuid.UUID(scan_id)).one()
    path = (f"/api/v1/orgs/{owner[1]}/findings/{observation.finding_id}/"
        f"observations/{observation.id}/identity-binding")
    response = client.put(path, headers=owner[0], json=dict(expected_version=0,
        tool_id=tool_id, expected_tool_version=1, canonical_asset_id=str(canonical_asset_id),
        confirm_mapping=True, rationale="Reviewed synthetic scanner and host"))
    assert response.status_code == 200, response.text
    return observation, response.json()["identity_assessment"]["candidate_key"]


def test_durable_queue_is_idempotent_versioned_tenant_scoped_and_survives_source_purge(
        client, owner, db_session):
    from app.models.finding_observation import FindingObservation
    from app.models.finding_identity_binding import ObservationIdentityBinding
    from app.models.finding_absence_review import (
        FindingAbsenceReviewBatch, FindingAbsenceReviewDecision, FindingAbsenceReviewItem,
    )

    baseline_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "baseline.nessus", _nessus_many(["1001", "1002"]))
    current_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "current.nessus", _nessus("1003"))
    assert baseline_response.status_code == current_response.status_code == 201
    baseline_id, current_id = baseline_response.json()["scan_id"], current_response.json()["scan_id"]
    baseline_observations = db_session.query(FindingObservation).filter_by(
        scan_id=uuid.UUID(baseline_id)).order_by(FindingObservation.source_row).all()
    current_observations = db_session.query(FindingObservation).filter_by(
        scan_id=uuid.UUID(current_id)).all()
    assert len(baseline_observations) == 2 and len(current_observations) == 1
    tool_response = client.post(f"/api/v1/orgs/{owner[1]}/identity-tools",
        headers=owner[0], json=dict(name="Synthetic Nessus", rationale="Test scanner"))
    assert tool_response.status_code == 201, tool_response.text
    tool_id = tool_response.json()["id"]
    canonical_asset_id = baseline_observations[0].asset_identity["asset_id"]
    for observation in baseline_observations + current_observations:
        response = client.put(
            f"/api/v1/orgs/{owner[1]}/findings/{observation.finding_id}/observations/"
            f"{observation.id}/identity-binding",
            headers=owner[0], json=dict(expected_version=0, tool_id=tool_id,
                expected_tool_version=1, canonical_asset_id=canonical_asset_id,
                confirm_mapping=True, rationale="Reviewed synthetic scanner and host"))
        assert response.status_code == 200, response.text
    assert db_session.query(ObservationIdentityBinding).count() == 3

    source_time = datetime.now(timezone.utc)
    declare(client, owner, baseline_id, {"source_snapshot_at": (source_time - timedelta(minutes=2)).isoformat()})
    declare(client, owner, current_id, {"source_snapshot_at": (source_time - timedelta(minutes=1)).isoformat()})
    payload = dict(baseline_scan_id=baseline_id, current_scan_id=current_id,
        baseline_version=1, current_version=1, candidate_offset=0, candidate_limit=1)
    payload["review_token"] = client.post(f"{root(owner)}/snapshot-comparison", headers=owner[0], json=payload).json()["review_token"]
    path = f"{root(owner)}/snapshot-comparison/queue"
    viewer = member(client, owner[0], owner[1], "viewer")
    assert client.post(path, headers=viewer, json=payload).status_code == 403

    before_findings = {
        row.id: (row.workflow_status, row.workflow_version, row.severity, row.description, row.archived_at)
        for row in db_session.query(Finding).all()
    }
    saved = client.post(path, headers=owner[0], json=payload)
    assert saved.status_code == 200, saved.text
    batch_id = saved.json()["review_queue_batch_id"]
    assert batch_id and saved.json()["review_queue_item_count"] == 2
    assert len(saved.json()["review_candidates"]) == 1
    repeated = client.post(path, headers=owner[0], json=payload)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["review_queue_batch_id"] == batch_id
    assert db_session.query(FindingAbsenceReviewBatch).count() == 1
    assert db_session.query(FindingAbsenceReviewItem).count() == 2

    queue_path = f"{root(owner)}/absence-review-queue"
    read = client.get(queue_path, headers=viewer, params={"state": "all", "limit": 1})
    assert read.status_code == 200, read.text
    assert read.json()["total"] == 2 and len(read.json()["items"]) == 1
    item = read.json()["items"][0]
    assert item["comparison"]["baseline"]["scan"]["id"] == baseline_id
    assert item["comparison"]["current"]["scan"]["id"] == current_id
    next_page = client.get(queue_path, headers=viewer,
        params={"state": "all", "limit": 1, "offset": 1})
    assert next_page.status_code == 200 and next_page.json()["total"] == 2
    assert len(next_page.json()["items"]) == 1
    other = register(client, "foreign-queue@example.io", "Other")
    assert client.get(f"/api/v1/orgs/{owner[1]}/scans/absence-review-queue",
        headers=other).status_code == 403

    decision_path = f"{queue_path}/{item['id']}/decision"
    assert client.post(decision_path, headers=viewer, json=dict(
        expected_version=0, action="keep_active", rationale="Not authorized")).status_code == 403
    kept = client.post(decision_path, headers=owner[0], json=dict(
        expected_version=0, action="keep_active", rationale="Still valid in inventory"))
    assert kept.status_code == 200, kept.text
    assert kept.json()["state"] == "kept_active" and kept.json()["decision_version"] == 1
    assert client.get(queue_path, headers=viewer, params={"state": "pending"}).json()["total"] == 1
    assert client.get(queue_path, headers=viewer, params={"state": "kept_active"}).json()["total"] == 1
    assert client.post(decision_path, headers=owner[0], json=dict(
        expected_version=0, action="keep_active", rationale="Stale decision")).status_code == 409
    reopened = client.post(decision_path, headers=owner[0], json=dict(
        expected_version=1, action="reopen", rationale="Needs another review"))
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["state"] == "pending" and reopened.json()["decision_version"] == 2
    assert [row.version for row in db_session.query(FindingAbsenceReviewDecision).filter_by(
        item_id=uuid.UUID(item["id"])).order_by(FindingAbsenceReviewDecision.version)] == [1, 2]

    db_session.expire_all()
    after_findings = {
        row.id: (row.workflow_status, row.workflow_version, row.severity, row.description, row.archived_at)
        for row in db_session.query(Finding).all()
    }
    assert before_findings == after_findings
    assert db_session.query(FindingHistory).count() == 0

    db_session.query(FindingObservation).filter(
        FindingObservation.scan_id.in_([uuid.UUID(baseline_id), uuid.UUID(current_id)])
    ).delete(synchronize_session=False)
    db_session.query(ScanSnapshotDeclaration).filter(
        ScanSnapshotDeclaration.scan_id.in_([uuid.UUID(baseline_id), uuid.UUID(current_id)])
    ).delete(synchronize_session=False)
    db_session.commit()
    retained = client.get(queue_path, headers=viewer, params={"state": "all", "limit": 1})
    assert retained.status_code == 200 and retained.json()["total"] == 2
    assert retained.json()["items"][0]["candidate"]["finding_id"]
    assert retained.json()["items"][0]["comparison"]["baseline"]["scan"]["filename"] == "baseline.nessus"


@pytest.mark.parametrize(("current_plugin", "expected_candidates"), [("1001", 0), ("1002", 1)])
def test_review_queue_only_lists_absent_current_reviewed_native_identity(
        client, owner, db_session, current_plugin, expected_candidates):
    from app.models.finding_observation import FindingObservation
    from app.models.finding_identity_binding import ObservationIdentityBinding

    baseline_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "baseline.nessus", _nessus("1001"))
    current_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "current.nessus", _nessus(current_plugin))
    assert baseline_response.status_code == current_response.status_code == 201
    baseline_id, current_id = baseline_response.json()["scan_id"], current_response.json()["scan_id"]
    baseline_observation = db_session.query(FindingObservation).filter_by(
        scan_id=uuid.UUID(baseline_id)).one()
    tool_response = client.post(f"/api/v1/orgs/{owner[1]}/identity-tools",
        headers=owner[0], json=dict(name="Synthetic Nessus", rationale="Test scanner"))
    assert tool_response.status_code == 201, tool_response.text
    tool_id = tool_response.json()["id"]
    canonical_asset_id = baseline_observation.asset_identity["asset_id"]
    baseline_observation, baseline_key = _bind_observation(
        client, owner, db_session, baseline_id, tool_id, canonical_asset_id)
    current_observation, current_key = _bind_observation(
        client, owner, db_session, current_id, tool_id, canonical_asset_id)
    assert (baseline_key == current_key) is (current_plugin == "1001")

    source_time = datetime.now(timezone.utc)
    declare(client, owner, baseline_id, {"source_snapshot_at": (source_time - timedelta(hours=1)).isoformat()})
    declare(client, owner, current_id, {"source_snapshot_at": (source_time - timedelta(minutes=30)).isoformat()})
    finding = db_session.get(Finding, baseline_observation.finding_id)
    before = (finding.workflow_status, finding.workflow_version, finding.severity,
        finding.description, finding.scan_id, finding.archived_at)

    response = compare(client, owner, baseline_id, current_id)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["absence_eligible"] is True
    assert result["candidate_count"] == expected_candidates
    assert len(result["review_candidates"]) == expected_candidates
    assert result["baseline_reviewable_observations"] == 1
    assert result["current_reviewable_observations"] == 1
    if expected_candidates:
        candidate = result["review_candidates"][0]
        assert candidate["finding_id"] == str(baseline_observation.finding_id)
        assert candidate["baseline_observation_id"] == str(baseline_observation.id)
        assert candidate["reviewable_baseline_observation_count"] == 1
        assert candidate["severity"] == "medium"
        next_page = compare(client, owner, baseline_id, current_id, candidate_offset=1, candidate_limit=1).json()
        assert next_page["candidate_count"] == 1 and next_page["review_candidates"] == []
    db_session.refresh(finding)
    assert before == (finding.workflow_status, finding.workflow_version, finding.severity,
        finding.description, finding.scan_id, finding.archived_at)
    assert db_session.query(FindingHistory).count() == 0
    assert db_session.query(ObservationIdentityBinding).count() == 2
    assert db_session.get(FindingObservation, current_observation.id) is not None


def test_review_queue_excludes_unreviewed_native_observations(client, owner, db_session):
    baseline_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "baseline.nessus", _nessus("1001"))
    current_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "current.nessus", _nessus("1002"))
    baseline_id, current_id = baseline_response.json()["scan_id"], current_response.json()["scan_id"]
    source_time = datetime.now(timezone.utc)
    declare(client, owner, baseline_id, {"source_snapshot_at": (source_time - timedelta(hours=1)).isoformat()})
    declare(client, owner, current_id, {"source_snapshot_at": (source_time - timedelta(minutes=30)).isoformat()})
    result = compare(client, owner, baseline_id, current_id).json()
    assert result["absence_eligible"] is False
    assert result["review_candidates"] == []
    assert result["baseline_unreviewable_observations"] == 1
    assert result["current_unreviewable_observations"] == 1
    assert "current:unreviewable_observations_present" in result["absence_blockers"]


def test_review_queue_excludes_ambiguous_baseline_native_identity(client, owner, db_session):
    from app.models.finding_observation import FindingObservation

    baseline_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "baseline.nessus", _nessus_two_hosts("1001"))
    current_response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import",
        owner[0], "current.nessus", _nessus("1002"))
    assert baseline_response.status_code == current_response.status_code == 201
    baseline_id, current_id = baseline_response.json()["scan_id"], current_response.json()["scan_id"]
    observations = db_session.query(FindingObservation).filter_by(
        scan_id=uuid.UUID(baseline_id)).order_by(FindingObservation.source_row).all()
    assert len(observations) == 2 and observations[0].finding_id != observations[1].finding_id
    tool_response = client.post(f"/api/v1/orgs/{owner[1]}/identity-tools",
        headers=owner[0], json=dict(name="Synthetic Nessus", rationale="Test scanner"))
    assert tool_response.status_code == 201, tool_response.text
    tool_id = tool_response.json()["id"]
    canonical_asset_id = observations[0].asset_identity["asset_id"]
    for observation in observations:
        path = (f"/api/v1/orgs/{owner[1]}/findings/{observation.finding_id}/"
            f"observations/{observation.id}/identity-binding")
        response = client.put(path, headers=owner[0], json=dict(expected_version=0,
            tool_id=tool_id, expected_tool_version=1, canonical_asset_id=canonical_asset_id,
            confirm_mapping=True, rationale="Reviewed duplicate synthetic identity"))
        assert response.status_code == 200, response.text
    _bind_observation(client, owner, db_session, current_id, tool_id, canonical_asset_id)
    source_time = datetime.now(timezone.utc)
    declare(client, owner, baseline_id, {"source_snapshot_at": (source_time - timedelta(hours=1)).isoformat()})
    declare(client, owner, current_id, {"source_snapshot_at": (source_time - timedelta(minutes=30)).isoformat()})
    result = compare(client, owner, baseline_id, current_id).json()
    assert result["absence_eligible"] is True
    assert result["ambiguous_baseline_identity_count"] == 1
    assert result["candidate_count"] == 0 and result["review_candidates"] == []


def test_review_queue_fails_closed_when_scan_observation_cap_is_exceeded(
        client, owner, monkeypatch):
    from app.services import scan_snapshots

    baseline_id, current_id = imported(client, owner), imported(client, owner)
    source_time = datetime.now(timezone.utc)
    declare(client, owner, baseline_id, {"source_snapshot_at": (source_time - timedelta(hours=1)).isoformat()})
    declare(client, owner, current_id, {"source_snapshot_at": (source_time - timedelta(minutes=30)).isoformat()})
    monkeypatch.setattr(scan_snapshots, "_MAX_REVIEW_OBSERVATIONS_PER_SCAN", 0)
    result = compare(client, owner, baseline_id, current_id).json()
    assert result["absence_eligible"] is False
    assert "baseline:scan_observation_limit_exceeded" in result["absence_blockers"]
    assert "current:scan_observation_limit_exceeded" in result["absence_blockers"]
    assert result["review_candidates"] == [] and result["candidate_count"] == 0


@pytest.mark.parametrize("field,value,reason", [
    ("tool_name", "Other scanner", "tool_name_changed"),
    ("tool_instance_id", "scanner-2", "tool_instance_id_changed"),
    ("tool_configuration_id", "policy-v2", "tool_configuration_id_changed"),
    ("targets", ["10.0.1.0/24"], "target_scope_changed"),
    ("exclusions", [], "scope_exclusions_changed"),
    ("snapshot_kind", "partial", "current:source_snapshot_not_complete"),
    ("snapshot_kind", "incremental", "current:source_snapshot_not_complete"),
    ("snapshot_kind", "cancelled", "current:source_snapshot_not_complete"),
    ("snapshot_kind", "failed", "current:source_snapshot_not_complete"),
])
def test_incompatible_metadata_is_explained(client, owner, field, value, reason):
    a, b = imported(client, owner), imported(client, owner)
    declare(client, owner, a)
    declare(client, owner, b, {field:value})
    result = compare(client, owner, a,b).json()
    assert result["declared_metadata_matches"] is False
    assert reason in result["blocking_reasons"]
    assert not result["absence_eligible"] and result["review_candidates"] == []


def test_settings_change_is_captured_at_import_not_reconstructed(client, owner):
    a = imported(client, owner)
    assert client.patch(f"/api/v1/orgs/{owner[1]}/settings", headers=owner[0],
        json={"nessus_info_severity": "low"}).status_code == 200
    b = imported(client, owner)
    old = declare(client, owner, a)["scan"]["ingestion_config_fingerprint"]
    new = declare(client, owner, b)["scan"]["ingestion_config_fingerprint"]
    assert old != new
    assert "ingestion_config_fingerprint_changed" in compare(client, owner, a,b).json()["blocking_reasons"]


def test_declarations_are_versioned_stale_edits_rejected_and_revocation_invalidates_review(client, owner, db_session):
    a, b = imported(client, owner), imported(client, owner)
    first = declare(client, owner, a)
    declare(client, owner, b)
    declare(client, owner, a, status=409)
    updated = declare(client, owner, a, {"expected_version":1,"targets":["10.0.1.0/24"]})
    assert updated["declaration"]["version"] == 2
    assert compare(client, owner, a,b).status_code == 409
    response = client.post(f"{root(owner)}/{a}/snapshot/revoke", headers=owner[0],
        json={"expected_version":2,"rationale":"Scope was incorrect"})
    assert response.status_code == 200, response.text
    assert response.json()["declaration"]["state"] == "revoked"
    result = compare(client, owner, a,b, baseline_version=3).json()
    assert "baseline:declaration_revoked" in result["blocking_reasons"]
    old = db_session.get(ScanSnapshotDeclaration, uuid.UUID(first["declaration"]["id"]))
    assert old.version == 1 and old.state == "declared" and old.declaration["targets"] == ["10.0.0.0/24"]
    assert db_session.query(ScanSnapshotDeclaration).count() == 4


@pytest.mark.parametrize("field,value,expected", [
    ("snapshot_kind","unknown",422), ("coverage_confirmed",False,422),
    ("unreachable_targets",["10.0.0.12"],422), ("tool_instance_id","  ",422),
    ("targets",[],422), ("targets",[" "],422), ("rationale"," ",422),
    ("source_snapshot_at",None,422), ("source_snapshot_at","2026-11-01T12:00:00",422),
    ("source_snapshot_at","0001-01-01T00:00:00+05:00",422),
    ("source_snapshot_at","9999-12-31T23:59:59-05:00",422),
    ("ingestion_config_fingerprint","forged",422),
])
def test_invalid_or_forged_declarations_are_rejected(client, owner, field, value, expected):
    a=imported(client, owner)
    declare(client, owner, a, {field:value}, status=expected)


@pytest.mark.parametrize("state", [ScanStatus.pending, ScanStatus.running, ScanStatus.failed])
def test_uncompleted_scans_cannot_be_declared(client, owner, db_session, state):
    a=imported(client, owner)
    scan=db_session.get(Scan, uuid.UUID(a));scan.status=state;db_session.commit()
    declare(client, owner, a,status=409)


@pytest.mark.parametrize("problem", ["failed","skipped","warnings_total"])
def test_incomplete_imports_allow_partial_declaration_only(client, owner, db_session, problem):
    a=imported(client, owner)
    scan=db_session.get(Scan,uuid.UUID(a));scan.summary={**scan.summary, problem:1};db_session.commit()
    declare(client, owner,a,status=409)
    result=declare(client,owner,a,{"snapshot_kind":"partial","coverage_confirmed":False})
    assert result["complete_blockers"] == ["import_has_errors_skips_or_warnings"]


def test_legacy_missing_capture_and_failed_live_state_cannot_be_compared(client, owner, db_session):
    a,b=imported(client,owner),imported(client,owner)
    declare(client,owner,a);declare(client,owner,b)
    scan=db_session.get(Scan,uuid.UUID(b));scan.status=ScanStatus.failed;db_session.commit()
    result=compare(client,owner,a,b).json()
    assert "current:scan_not_successfully_completed" in result["blocking_reasons"]
    assert not result["absence_eligible"]
    scan.status=ScanStatus.completed;scan.ingestion_config_fingerprint=None;db_session.commit()
    declare(client,owner,b,{"expected_version":1},status=409)
    assert "current:captured_import_configuration_unavailable" in compare(client,owner,a,b).json()["blocking_reasons"]


def test_roles_tenants_order_and_archive(client, owner, db_session):
    a,b=imported(client,owner),imported(client,owner)
    declare(client,owner,a);declare(client,owner,b)
    viewer=member(client,owner[0],owner[1],"viewer")
    read=client.get(f"{root(owner)}/{a}/snapshot",headers=viewer)
    assert read.status_code==200
    assert client.put(f"{root(owner)}/{a}/snapshot",headers=viewer,json=fields()).status_code==403
    assert compare(client,(viewer,owner[1]),a,b).status_code==200
    other=register(client,"foreign-snapshot@example.io","Other")
    assert compare(client,(other,first_org_id(client,other)),a,b).status_code==404
    assert compare(client,(other,owner[1]),a,b).status_code==403
    assert compare(client,owner,a,a).status_code==422
    assert "current_source_snapshot_is_not_newer" in compare(client,owner,b,a).json()["blocking_reasons"]
    archived=client.post(f"{root(owner)}/{b}/archive",headers=owner[0]);assert archived.status_code==200
    assert compare(client,owner,a,b).status_code==404
    assert db_session.query(ScanSnapshotDeclaration).count()==2


def test_stopped_archive_blocks_declarations_and_reviews(client, owner, db_session):
    a,b=imported(client,owner),imported(client,owner)
    declare(client,owner,a);declare(client,owner,b)
    db_session.add(ArchiveBatch(org_id=uuid.UUID(owner[1]), item_type=ArchiveItemType.upload,
        item_id=uuid.UUID(a), label="Stopped archive", state=ArchiveState.archiving))
    db_session.commit()
    declare(client,owner,b,{"expected_version":1},status=409)
    result=compare(client,owner,a,b).json()
    assert "current:organization_archive_operation_in_progress" in result["blocking_reasons"]
    assert not result["absence_eligible"]


def test_role_cached_before_removal_cannot_authorize_declaration(client, owner, db_session):
    a=imported(client,owner)
    membership=db_session.scalar(select(OrgMembership).where(OrgMembership.org_id==uuid.UUID(owner[1])))
    stale=SimpleNamespace(user_id=membership.user_id,role=UserRole.admin)
    membership.role=UserRole.viewer;db_session.commit()
    with pytest.raises(HTTPException) as error:
        write_snapshot(db_session,uuid.UUID(owner[1]),uuid.UUID(a),stale,SnapshotWrite(**fields()))
    assert error.value.status_code==403
    db_session.rollback()
    assert db_session.query(ScanSnapshotDeclaration).count()==0


def test_concurrent_first_declarations_have_one_winner(client, owner, db_session):
    a=imported(client,owner)
    user_id=db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id==uuid.UUID(owner[1])))
    engine=db_session.get_bind();barrier=Barrier(2)
    def write():
        with Session(engine,autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            barrier.wait(timeout=10)
            try:
                return write_snapshot(db,uuid.UUID(owner[1]),uuid.UUID(a),SimpleNamespace(user_id=user_id),SnapshotWrite(**fields())).declaration.version
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:write(),range(2)))
    assert sorted(results)==[1,409]
    assert db_session.query(ScanSnapshotDeclaration).count()==1


def test_source_time_not_upload_order_controls_chronology(client,owner):
    a,b=imported(client,owner),imported(client,owner)
    now=datetime.now(timezone.utc)
    declare(client,owner,a,{"source_snapshot_at":(now-timedelta(hours=1)).isoformat()})
    declare(client,owner,b,{"source_snapshot_at":(now-timedelta(hours=2)).isoformat()})
    assert "current_source_snapshot_is_not_newer" in compare(client,owner,a,b).json()["blocking_reasons"]
    assert compare(client,owner,b,a).json()["declared_metadata_matches"] is True


def test_source_time_after_import_is_rejected(client,owner):
    a=imported(client,owner)
    declare(client,owner,a,{"source_snapshot_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},status=422)


def test_partial_unknown_source_time_stays_unknown(client,owner):
    a,b=imported(client,owner),imported(client,owner)
    declare(client,owner,a)
    view=declare(client,owner,b,{"snapshot_kind":"partial","coverage_confirmed":False,"source_snapshot_at":None})
    assert view["declaration"]["declaration"]["source_snapshot_at"] is None
    result=compare(client,owner,a,b).json()
    assert "current:source_snapshot_time_unavailable" in result["blocking_reasons"]
    assert not result["declared_metadata_matches"] and not result["absence_eligible"]


def test_same_source_time_cannot_become_newer_by_reuploading(client,owner):
    a,b=imported(client,owner),imported(client,owner)
    stamp=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    declare(client,owner,a,{"source_snapshot_at":stamp});declare(client,owner,b,{"source_snapshot_at":stamp})
    result=compare(client,owner,a,b).json()
    assert "current_source_snapshot_is_not_newer" in result["blocking_reasons"]
    assert not result["absence_eligible"] and result["review_candidates"] == []


def test_scope_order_and_duplicate_entries_do_not_change_declared_identity(client,owner):
    a,b=imported(client,owner),imported(client,owner)
    first=declare(client,owner,a,{"targets":[" Host-B ","Host-A","Host-A"],"exclusions":["x","y","x"]})
    declare(client,owner,b,{"targets":["Host-A","Host-B"],"exclusions":["y","x"]})
    assert first["declaration"]["declaration"]["targets"] == ["Host-A","Host-B"]
    assert compare(client,owner,a,b).json()["declared_metadata_matches"] is True


@pytest.fixture
def queue_review_pair(client, owner, db_session):
    from app.models.finding_observation import FindingObservation
    baseline = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import", owner[0], "baseline.nessus", _nessus("1001")).json()["scan_id"]
    current = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import", owner[0], "current.nessus", _nessus("1002")).json()["scan_id"]
    observation = db_session.scalar(select(FindingObservation).where(FindingObservation.scan_id == uuid.UUID(baseline)))
    tool = client.post(f"/api/v1/orgs/{owner[1]}/identity-tools", headers=owner[0], json=dict(name="Review scanner", rationale="Synthetic test")).json()["id"]
    for identifier in (baseline, current):
        _bind_observation(client, owner, db_session, identifier, tool, observation.asset_identity["asset_id"])
    now = datetime.now(timezone.utc)
    declare(client, owner, baseline, {"source_snapshot_at": (now-timedelta(minutes=2)).isoformat()})
    declare(client, owner, current, {"source_snapshot_at": (now-timedelta(minutes=1)).isoformat()})
    return dict(baseline_scan_id=baseline, current_scan_id=current, baseline_version=1, current_version=1), observation.finding_id


def test_review_regression_queue_save_rejects_changed_preview(client, owner, db_session, queue_review_pair):
    payload, finding_id = queue_review_pair
    preview = client.post(f"{root(owner)}/snapshot-comparison", headers=owner[0], json=payload).json()
    finding = db_session.get(Finding, finding_id)
    finding.workflow_status = "resolved"
    finding.workflow_version += 1
    db_session.commit()
    if preview.get("review_token"):
        payload = {**payload, "review_token": preview["review_token"]}
    response = client.post(f"{root(owner)}/snapshot-comparison/queue", headers=owner[0], json=payload)
    assert response.status_code == 409, response.text


def test_review_regression_keep_active_rejects_changed_finding(client, owner, db_session, queue_review_pair):
    payload, finding_id = queue_review_pair
    preview = client.post(f"{root(owner)}/snapshot-comparison", headers=owner[0], json=payload).json()
    if preview.get("review_token"):
        payload = {**payload, "review_token": preview["review_token"]}
    saved = client.post(f"{root(owner)}/snapshot-comparison/queue", headers=owner[0], json=payload)
    assert saved.status_code == 200, saved.text
    item = client.get(f"{root(owner)}/absence-review-queue", headers=owner[0]).json()["items"][0]
    finding = db_session.get(Finding, finding_id)
    finding.workflow_status = "resolved"
    finding.workflow_version += 1
    db_session.commit()
    response = client.post(f"{root(owner)}/absence-review-queue/{item['id']}/decision", headers=owner[0],
        json=dict(expected_version=0, action="keep_active", rationale="Reviewed original preview"))
    assert response.status_code == 409, response.text


@pytest.fixture
def saved_queue_item(client, owner, queue_review_pair):
    payload, finding_id = queue_review_pair
    preview = client.post(f"{root(owner)}/snapshot-comparison", headers=owner[0], json=payload).json()
    response = client.post(f"{root(owner)}/snapshot-comparison/queue", headers=owner[0],
        json={**payload, "review_token": preview["review_token"]})
    assert response.status_code == 200, response.text
    item = client.get(f"{root(owner)}/absence-review-queue", headers=owner[0]).json()["items"][0]
    return payload, finding_id, item


def test_queue_preview_token_is_mandatory_and_bound_to_context(client, owner, queue_review_pair):
    payload, _ = queue_review_pair
    path = f"{root(owner)}/snapshot-comparison/queue"
    assert client.post(path, headers=owner[0], json=payload).status_code == 422
    assert client.post(path, headers=owner[0], json={**payload, "review_token": "0"*64}).status_code == 409


def test_queue_save_fails_promptly_instead_of_waiting_for_import(client, owner, db_session, queue_review_pair):
    from app.services.org_lock import lock_org
    from app.services.scan_snapshots import compare_snapshots
    from app.schemas.scan_snapshot import SnapshotComparisonRequest
    payload, _ = queue_review_pair
    member_row = db_session.scalar(select(OrgMembership).where(OrgMembership.org_id == uuid.UUID(owner[1])))
    org_id = member_row.org_id
    actor = SimpleNamespace(user_id=member_row.user_id, role=member_row.role)
    with Session(db_session.get_bind()) as writer:
        lock_org(writer, org_id)
        db_session.execute(text("SET LOCAL statement_timeout='2s'"))
        with pytest.raises(HTTPException) as error:
            compare_snapshots(db_session, org_id, SnapshotComparisonRequest(**payload),
                persist_queue=True, membership=actor, expected_review_token="0"*64)
        assert error.value.status_code == 409
        assert "publication" in str(error.value.detail)
        writer.rollback()
    db_session.rollback()


def test_keep_active_does_not_wait_for_import_and_two_admins_cannot_overwrite(client, owner, db_session, saved_queue_item):
    from app.services.org_lock import lock_org
    from app.services.scan_snapshots import decide_absence_review
    from app.schemas.scan_snapshot import AbsenceReviewDecisionWrite
    from app.models.finding_absence_review import FindingAbsenceReviewDecision
    payload, finding_id, item = saved_queue_item
    member_row = db_session.scalar(select(OrgMembership).where(OrgMembership.org_id == uuid.UUID(owner[1])))
    org_id, user_id = member_row.org_id, member_row.user_id
    # No inventory lock is needed to record a historical review note.
    with Session(db_session.get_bind()) as writer:
        lock_org(writer, org_id)
        db_session.execute(text("SET LOCAL statement_timeout='2s'"))
        response = client.post(f"{root(owner)}/absence-review-queue/{item['id']}/decision", headers=owner[0],
            json=dict(expected_version=0, action="keep_active", rationale="Independent of inventory publication"))
        assert response.status_code == 200, response.text
        writer.rollback()
    db_session.execute(text("SET LOCAL statement_timeout=0"))
    second_headers = member(client, owner[0], owner[1], "admin")
    second_id = db_session.scalar(select(OrgMembership.user_id).where(
        OrgMembership.org_id == org_id, OrgMembership.user_id != user_id))
    engine = db_session.get_bind(); barrier = Barrier(2)
    def save(actor_id):
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'")); barrier.wait(timeout=10)
            try:
                result = decide_absence_review(db, org_id, uuid.UUID(item["id"]),
                    SimpleNamespace(user_id=actor_id), AbsenceReviewDecisionWrite(
                        expected_version=1, action="reopen", rationale="Independent admin review"))
                return result.decision_version
            except HTTPException as exc:
                db.rollback(); return exc.status_code
    db_session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(save, (user_id, second_id)))
    assert sorted(result) == [2, 409]
    assert db_session.query(FindingAbsenceReviewDecision).count() == 2


def test_queue_survives_actual_upload_purge_and_rejects_missing_finding(client, owner, db_session, saved_queue_item):
    payload, finding_id, item = saved_queue_item
    identifier = payload["baseline_scan_id"]
    response = client.post(f"{root(owner)}/{identifier}/archive", headers=owner[0])
    assert response.status_code == 200, response.text
    batches = client.get(f"/api/v1/orgs/{owner[1]}/archive", headers=owner[0]).json()["items"]
    batch = next(row["id"] for row in batches if row["item_id"] == identifier)
    assert client.post(f"/api/v1/orgs/{owner[1]}/archive/{batch}/purge", headers=owner[0]).status_code == 200
    assert db_session.get(Finding, finding_id) is None
    retained = client.get(f"{root(owner)}/absence-review-queue", headers=owner[0])
    assert retained.status_code == 200
    assert retained.json()["items"][0]["candidate"]["finding_id"] == str(finding_id)
    assert "declaration" not in retained.json()["items"][0]["comparison"]["baseline"]
    response = client.post(f"{root(owner)}/absence-review-queue/{item['id']}/decision", headers=owner[0],
        json=dict(expected_version=0, action="keep_active", rationale="Source is gone"))
    assert response.status_code == 409



def test_queue_item_ids_cannot_be_used_through_another_organization(client, owner, saved_queue_item):
    _, _, item = saved_queue_item
    headers = register(client, "foreign-review@example.io", "Independent organization")
    other_id = first_org_id(client, headers)
    response = client.post(f"/api/v1/orgs/{other_id}/scans/absence-review-queue/{item['id']}/decision",
        headers=headers, json=dict(expected_version=0, action="keep_active", rationale="Foreign item"))
    assert response.status_code == 404
    assert client.get(f"/api/v1/orgs/{other_id}/scans/absence-review-queue", headers=headers).json()["total"] == 0
