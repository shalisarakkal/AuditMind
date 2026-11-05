"""Observation provenance never grants scan comparability or changes workflow."""
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete

from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import FIXTURES, first_org_id, member, register, run_worker, upload

pytestmark = requires_db


@pytest.fixture
def owner(client):
    headers = register(client, "observations@example.io")
    return headers, first_org_id(client, headers)


def send(client, owner, rows):
    headers, org = owner
    response = upload(client, f"/api/v1/orgs/{org}/findings/import", headers, "source.json", json.dumps(rows).encode())
    assert response.status_code == 201, response.text
    return response.json()


def row(**changes):
    return {"hostname": "server", "domain": "network_config", "severity": "high",
        "category": "RULE-1", "description": "Initial", "source": "tool", **changes}


def observations(client, owner, finding_id, **params):
    return client.get(f"/api/v1/orgs/{owner[1]}/findings/{finding_id}/observations", headers=owner[0], params=params)


def test_repeated_changed_and_same_file_occurrences_preserve_workflow(client, owner, db_session):
    first = send(client, owner, [row()])
    finding = db_session.query(Finding).one()
    finding_id = finding.id
    url = f"/api/v1/orgs/{owner[1]}/findings/{finding.id}/workflow"
    response = client.patch(url, headers=owner[0], json={"expected_version": 0,
        "status": "mitigated", "rationale": "Patched", "verification": "Verified"})
    assert response.status_code == 200, response.text
    before = response.json()
    changed = row()
    changed.update(severity="critical", description="Changed source description")
    second = send(client, owner, [changed, changed])
    assert second["report"]["duplicates"] == 2
    assert db_session.query(Finding).count() == 1
    assert client.get(url, headers=owner[0]).json() == before
    db_session.expire_all()
    finding = db_session.get(Finding, finding_id)
    assert finding.scan_id == uuid.UUID(first["scan_id"])
    assert finding.description == "Initial"
    rows = observations(client, owner, finding.id).json()
    assert len(rows) == 3
    assert [entry["payload"]["severity"] for entry in rows] == ["critical", "critical", "high"]
    assert {entry["import_id"] for entry in rows} == {first["scan_id"], second["scan_id"]}
    assert {entry["occurrence"] for entry in rows[:2]} == {1, 2}
    assert all(not entry["reconciliation_eligible"] for entry in rows)
    assert all(entry["observed_at"] is None for entry in rows)


@pytest.mark.parametrize("strategy", ["update", "skip", "duplicate"])
def test_asset_bearing_profiles_preserve_strategy(client, owner, db_session, strategy, monkeypatch):
    from app.services import import_profiles
    monkeypatch.setattr(import_profiles, "utc_now", lambda: datetime(2026, 9, 28, 12, tzinfo=timezone.utc))
    headers, org = owner
    assert client.patch(f"/api/v1/orgs/{org}/settings", headers=headers,
        json={"asset_existing_strategy": strategy}).status_code == 200
    for _ in range(2):
        response = client.post(f"/api/v1/orgs/{org}/imports", headers=headers,
            files={"file": ("endpoint_agents.csv", (FIXTURES / "endpoint_agents.csv").read_bytes())},
            data={"profile": "endpoint_agent", "confirm": "true"})
        assert response.status_code == 201, response.text
    assert db_session.query(FindingObservation).count() == 16
    assert db_session.query(Finding).count() == (16 if strategy == "duplicate" else 8)


def test_nessus_records_native_identity_without_guessing_tool_instance(client, owner, db_session):
    response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import", owner[0], "sample.nessus")
    assert response.status_code == 201
    entries = db_session.query(FindingObservation).all()
    assert len(entries) == 6
    entry = next(entry for entry in entries if entry.source_identity["plugin_id"] == "187095")
    assert entry.source_identity == {"plugin_id": "187095", "port": "443", "protocol": "tcp"}
    assert "source_instance_not_configured" in entry.ineligibility_reasons
    assert not entry.reconciliation_eligible


def test_tenant_permissions_seek_and_empty_legacy_history(client, owner, db_session):
    send(client, owner, [row()] * 3)
    finding = db_session.query(Finding).one()
    # Tie timestamps to exercise UUID ordering, and insert while navigating.
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.query(FindingObservation).update({"recorded_at": stamp})
    db_session.commit()
    page = observations(client, owner, finding.id, limit=2).json()
    send(client, owner, [row()])
    older = observations(client, owner, finding.id, limit=2, before=page[-1]["id"]).json()
    assert len(older) == 1 and older[0]["id"] not in {entry["id"] for entry in page}
    outsider = register(client, "outsider@example.io", "Other")
    assert observations(client, (outsider, owner[1]), finding.id).status_code == 403
    assert observations(client, (outsider, first_org_id(client, outsider)), finding.id).status_code == 404
    viewer = member(client, owner[0], owner[1], "viewer")
    assert observations(client, (viewer, owner[1]), finding.id).status_code == 200
    assert observations(client, owner, finding.id, before=uuid.uuid4()).status_code == 404
    assert observations(client, owner, finding.id, limit=101).status_code == 422


def test_archive_reimport_and_purge_keep_existing_contract(client, owner, db_session):
    first = send(client, owner, [row()])
    finding_id = db_session.query(Finding.id).scalar()
    base = f"/api/v1/orgs/{owner[1]}"
    archived = client.post(f"{base}/scans/{first['scan_id']}/archive", headers=owner[0])
    assert archived.status_code == 200, archived.text
    assert len(observations(client, owner, finding_id).json()) == 1
    send(client, owner, [row()])
    assert db_session.query(Finding).count() == 2
    assert db_session.query(FindingObservation).count() == 2
    batch = archived.json()["batch_id"]
    response = client.post(f"{base}/archive/{batch}/purge", headers=owner[0])
    assert response.status_code == 200, response.text
    assert db_session.query(FindingObservation).count() == 1
    assert observations(client, owner, finding_id).status_code == 404


def test_scan_link_can_disappear_without_erasing_repeated_import_id(client, owner, db_session):
    send(client, owner, [row()])
    second = send(client, owner, [row()])
    # A duplicate-only scan owns no finding. Purging it leaves provenance UUID.
    db_session.execute(delete(Scan).where(Scan.id == uuid.UUID(second["scan_id"])))
    db_session.commit()
    entry = db_session.query(FindingObservation).filter_by(import_id=uuid.UUID(second["scan_id"])).one()
    assert entry.scan_id is None and entry.import_id == uuid.UUID(second["scan_id"])


def test_failed_atomic_import_records_no_observations(client, owner, db_session):
    client.patch(f"/api/v1/orgs/{owner[1]}/settings", headers=owner[0], json={"import_partial_success": False})
    result = send(client, owner, [row(), {"bad": "row"}])
    assert result["status"] == "failed"
    assert db_session.query(FindingObservation).count() == 0


def test_supplied_identifiers_and_observed_time_are_preserved_but_not_trusted(client, owner, db_session):
    send(client, owner, [row(source_instance_id="scanner-1", source_finding_id="QID-42",
        observed_at="2026-11-05T08:00:00-05:00"), row(observed_at="2026-11-05T08:00:00")])
    entries = db_session.query(FindingObservation).order_by(FindingObservation.occurrence).all()
    assert entries[0].source_identity["source_finding_id"] == "QID-42"
    assert entries[0].observed_at == datetime(2026, 11, 5, 13, tzinfo=timezone.utc)
    assert not entries[0].reconciliation_eligible
    assert entries[1].observed_at is None
    assert "source_observed_time_invalid" in entries[1].ineligibility_reasons


@pytest.mark.parametrize("timestamp", ["0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-05:00"])
def test_observed_time_outside_utc_range_does_not_reject_an_otherwise_valid_import(client, owner, db_session, timestamp):
    result = send(client, owner, [row(observed_at=timestamp)])
    assert result["status"] == "completed"
    entry = db_session.query(FindingObservation).one()
    assert entry.observed_at is None
    assert "source_observed_time_invalid" in entry.ineligibility_reasons
    assert entry.payload["raw_data"]["observed_at"] == timestamp


def test_publish_failure_rolls_back_observations_and_retry_does_not_duplicate(client, owner, db_session, monkeypatch):
    from app.services import ingestion_service
    original = ingestion_service._PendingWrites.flush

    def fail_after_write(writes):
        original(writes)
        raise RuntimeError("Synthetic interrupted publication")

    with monkeypatch.context() as patch:
        patch.setattr(ingestion_service._PendingWrites, "flush", fail_after_write)
        with pytest.raises(RuntimeError, match="Synthetic interrupted"):
            send(client, owner, [row()])
    db_session.rollback()
    assert db_session.query(FindingObservation).count() == 0
    assert db_session.query(Finding).count() == 0
    scan = db_session.query(Scan).one()
    ingestion_service.process_import(db_session, scan, "findings", "json", json.dumps([row()]).encode())
    assert db_session.query(FindingObservation).count() == 1
    assert db_session.query(Finding).count() == 1


def test_background_batches_and_repeated_imports(client, owner, db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ingestion_service
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 10)
    monkeypatch.setattr(ingestion_service, "WRITE_BATCH", 200)
    content = json.dumps([row(category=f"RULE-{i}") for i in range(5000)]).encode()
    for count in (5000, 10000):
        response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import", owner[0], "batch.json", content)
        assert response.status_code == 202, response.text
        run_worker()
        assert db_session.query(FindingObservation).count() == count
        assert db_session.query(Finding).count() == 5000


def test_manual_and_preexisting_findings_have_no_invented_history(client, owner):
    response = client.post(f"/api/v1/orgs/{owner[1]}/findings", headers=owner[0],
        json={"domain": "network_config", "severity": "high", "description": "Manual"})
    assert response.status_code == 201, response.text
    finding_id = response.json()["id"]
    assert observations(client, owner, finding_id).json() == []
    response = client.post(f"/api/v1/orgs/{owner[1]}/findings/{finding_id}/observations", headers=owner[0], json={})
    assert response.status_code == 405
