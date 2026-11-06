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
    assert result["absence_eligible"] is False and result["not_observed_finding_ids"] is None
    assert result["baseline"]["scan"]["id"] == a and result["current"]["scan"]["id"] == b
    assert result["scope_differences"]["baseline_exclusions"] == ["10.0.0.20"]
    assert result["blocking_reasons"] == []
    assert response.headers["Cache-Control"] == "no-store"
    db_session.refresh(finding)
    assert workflow == {"status": finding.workflow_status, "version": finding.workflow_version,
        "severity": finding.severity, "archived_at": finding.archived_at, "scan_id": finding.scan_id}
    assert db_session.query(FindingHistory).count() == 0


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
    assert not result["absence_eligible"] and result["not_observed_finding_ids"] is None


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
    assert result["not_observed_finding_ids"] is None


def test_scope_order_and_duplicate_entries_do_not_change_declared_identity(client,owner):
    a,b=imported(client,owner),imported(client,owner)
    first=declare(client,owner,a,{"targets":[" Host-B ","Host-A","Host-A"],"exclusions":["x","y","x"]})
    declare(client,owner,b,{"targets":["Host-A","Host-B"],"exclusions":["y","x"]})
    assert first["declaration"]["declaration"]["targets"] == ["Host-A","Host-B"]
    assert compare(client,owner,a,b).json()["declared_metadata_matches"] is True
