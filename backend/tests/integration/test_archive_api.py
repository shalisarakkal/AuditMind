"""Archive, restore and purge (Phase 2d part 2): what each archives, that
archived rows vanish from every read path and from import matching, restore
(with duplicates purged), purge and its log, auto-purge, roles, background
jobs, resuming, and the repeat-upload warning."""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.archive import ArchiveBatch, ArchiveJob, AssetScan
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.enums import ArchiveAction, ArchiveItemType, ArchiveState, ScanStatus
from app.models.scan import Scan
from app.services import archive_service
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register, upload

pytestmark = requires_db

INVENTORY = b"type,hostname\nserver,shared-01\nserver,inv-02\n"
FINDINGS = (
    b"hostname,domain,severity,category,description,source\n"
    b"shared-01,vulnerability_management,high,CVE-1,Old OpenSSL,nessus\n"
    b"own-01,identity_access,critical,MFA,No MFA,audit\n"
    b"own-02,network_config,low,SMB,SMBv1 on,audit\n"
)
OTHER_FINDINGS = b"hostname,domain,severity,category,description,source\nown-02,backup_recovery,medium,BKP,No backup,audit\n"


@pytest.fixture
def admin(client):
    headers = register(client, "owner@acmecorp.io")
    return headers, first_org_id(client, headers)


def _url(admin, path):
    return f"/api/v1/orgs/{admin[1]}{path}"


def _import(client, admin, kind, content, name="f.csv", confirm=True, headers=None):
    resp = upload(client, _url(admin, f"/{kind}/import"), headers or admin[0], name, content, confirm=confirm)
    assert resp.status_code in (201, 202), resp.text
    return resp.json()["scan_id"]


def _get(client, admin, path, **params):
    resp = client.get(_url(admin, path), headers=admin[0], params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _post(client, admin, path, headers=None):
    return client.post(_url(admin, path), headers=headers or admin[0])


def _hosts(client, admin):
    return sorted(a["hostname"] for a in _get(client, admin, "/assets")["items"])


def _findings(client, admin, **params):
    return sorted(f["category"] for f in _get(client, admin, "/findings", **params)["items"])


def _archived(client, admin, item_type):
    return _get(client, admin, "/archive", item_type=item_type)["items"]


def _setup(client, admin):
    """An inventory (shared-01, inv-02), then findings on shared-01 and two
    new hosts (own-01, own-02), then another upload that also uses own-02."""
    inventory = _import(client, admin, "assets", INVENTORY, "inv.csv")
    findings = _import(client, admin, "findings", FINDINGS, "findings.csv")
    other = _import(client, admin, "findings", OTHER_FINDINGS, "other.csv")
    return inventory, findings, other


def test_imports_record_which_assets_each_upload_touched(client, admin, db_session):
    inventory, findings, _ = _setup(client, admin)
    host_of = {uuid.UUID(a["id"]): a["hostname"] for a in _get(client, admin, "/assets")["items"]}
    touched: dict[str, list[str]] = {}
    for link in db_session.query(AssetScan):
        touched.setdefault(str(link.scan_id), []).append(host_of[link.asset_id])
    assert sorted(touched[inventory]) == ["inv-02", "shared-01"]
    assert sorted(touched[findings]) == ["own-01", "own-02", "shared-01"]


def test_archiving_an_upload_archives_its_findings_and_the_assets_only_it_created(client, admin):
    _, findings, _ = _setup(client, admin)

    resp = _post(client, admin, f"/scans/{findings}/archive")
    assert resp.status_code == 200, resp.text
    job = resp.json()
    assert job["status"] == "completed" and job["action"] == "archive" and job["label"] == "findings.csv"
    # own-01 was only this upload's; own-02 is also used by the other upload;
    # shared-01 came from the inventory.
    assert job["summary"] == {"uploads": 1, "assets": 1, "findings": 3}
    assert _hosts(client, admin) == ["inv-02", "own-02", "shared-01"]
    assert _findings(client, admin) == ["BKP"]

    [item] = _archived(client, admin, "upload")
    assert item["label"] == "findings.csv" and item["archived_by"] == "owner@acmecorp.io"
    assert item["counts"] == {"uploads": 1, "assets": 1, "findings": 3}
    archived_at = datetime.fromisoformat(item["archived_at"])
    assert datetime.fromisoformat(item["purge_at"]) - archived_at == timedelta(days=settings.ARCHIVE_RETENTION_DAYS)
    assert [u["filename"] for u in _get(client, admin, "/uploads")["items"]] == ["other.csv", "inv.csv"]


def test_archived_rows_are_left_out_everywhere(client, admin):
    _, findings, other = _setup(client, admin)
    own_01 = next(a for a in _get(client, admin, "/assets")["items"] if a["hostname"] == "own-01")
    _post(client, admin, f"/scans/{findings}/archive")

    assert _findings(client, admin, sort="created") == ["BKP"]
    assert _findings(client, admin, sort="asset", q="own") == ["BKP"]
    assert _findings(client, admin, severity="critical") == []
    assert _get(client, admin, "/findings/facets")["source"] == ["audit"]
    assert _get(client, admin, "/assets", q="own-01")["total"] == 0
    assert _get(client, admin, f"/assets/{own_01['id']}/findings") == []
    dashboard = _get(client, admin, "/dashboard")
    assert dashboard["findings_by_severity"] == {"critical": 0, "high": 0, "medium": 1, "low": 0}
    assert [f["category"] for f in dashboard["top_findings"]] == ["BKP"]
    assert dashboard["asset_count"] == 3
    assert findings not in [s["id"] for s in dashboard["recent_scans"]]
    assert findings not in [s["id"] for s in _get(client, admin, "/scans")]
    risk = client.post(_url(admin, "/risk/score"), headers=admin[0]).json()
    identity = next(d for d in risk["domains"] if d["dimension"] == "identity_access")
    assert identity["score"] == 100.0
    assert other in [s["id"] for s in _get(client, admin, "/scans")]


def test_imports_never_match_archived_assets_or_findings(client, admin):
    _, findings, _ = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")

    # The same findings again: own-01 is archived, so it's created afresh,
    # and none of the findings count as duplicates of archived ones.
    resp = upload(client, _url(admin, "/findings/import"), admin[0], "again.csv", FINDINGS)
    assert resp.json()["report"]["created"] == 3 and resp.json()["report"]["duplicates"] == 0
    assert _hosts(client, admin).count("own-01") == 1


def test_restore_brings_back_exactly_what_was_archived(client, admin):
    _, findings, _ = _setup(client, admin)
    before_hosts, before_findings = _hosts(client, admin), _findings(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    [item] = _archived(client, admin, "upload")

    resp = _post(client, admin, f"/archive/{item['id']}/restore")
    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"]["duplicates_purged"] == 0
    assert _hosts(client, admin) == before_hosts
    assert _findings(client, admin) == before_findings
    assert _archived(client, admin, "upload") == []
    # It can be archived again (a new batch).
    assert _post(client, admin, f"/scans/{findings}/archive").json()["summary"]["findings"] == 3


def test_a_restored_finding_that_duplicates_an_active_one_is_purged(client, admin):
    _, findings, _ = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    # Re-imported meanwhile: CVE-1 on shared-01 (still active) exists again.
    upload(client, _url(admin, "/findings/import"), admin[0], "again.csv", FINDINGS)
    [item] = _archived(client, admin, "upload")

    job = _post(client, admin, f"/archive/{item['id']}/restore").json()
    # CVE-1 (shared-01) and SMB (own-02) duplicate the re-imported ones on
    # the same assets. MFA was on own-01, archived with the upload and
    # re-created by the re-import, so the restored MFA is on the old own-01.
    assert job["summary"]["duplicates_purged"] == 2
    assert job["summary"]["findings"] == 1
    assert _findings(client, admin) == ["BKP", "CVE-1", "MFA", "MFA", "SMB"]
    [entry] = _get(client, admin, "/purge-log")["items"]
    assert entry["reason"] == "duplicate" and entry["counts"] == {"findings": 2}


def test_archiving_an_asset_takes_all_its_findings(client, admin):
    _setup(client, admin)
    own_02 = next(a for a in _get(client, admin, "/assets")["items"] if a["hostname"] == "own-02")

    job = _post(client, admin, f"/assets/{own_02['id']}/archive").json()
    assert job["summary"] == {"uploads": 0, "assets": 1, "findings": 2}
    assert "own-02" not in _hosts(client, admin)
    assert _findings(client, admin) == ["CVE-1", "MFA"]
    assert _post(client, admin, f"/assets/{own_02['id']}/archive").status_code == 409


def test_only_manual_findings_are_archived_one_by_one(client, admin):
    _setup(client, admin)
    imported = _get(client, admin, "/findings")["items"][0]
    resp = _post(client, admin, f"/findings/{imported['id']}/archive")
    assert resp.status_code == 422

    manual = client.post(
        _url(admin, "/findings"),
        headers=admin[0],
        json={"domain": "incident_response", "severity": "low", "category": "IR-plan"},
    ).json()
    job = _post(client, admin, f"/findings/{manual['id']}/archive").json()
    assert job["summary"] == {"uploads": 0, "assets": 0, "findings": 1}
    assert "IR-plan" not in _findings(client, admin)
    assert [i["label"] for i in _archived(client, admin, "finding")] == ["IR-plan"]


def test_purge_deletes_for_good_and_is_logged(client, admin, db_session):
    _, findings, _ = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    [item] = _archived(client, admin, "upload")

    job = _post(client, admin, f"/archive/{item['id']}/purge").json()
    assert job["summary"] == {"uploads": 1, "assets": 1, "findings": 3}
    assert _archived(client, admin, "upload") == []
    assert client.get(_url(admin, f"/scans/{findings}"), headers=admin[0]).status_code == 404
    [entry] = _get(client, admin, "/purge-log")["items"]
    assert entry["label"] == "findings.csv" and entry["reason"] == "manual"
    assert entry["purged_by"] == "owner@acmecorp.io" and entry["counts"] == job["summary"]
    # Purged: it can't be restored.
    assert _post(client, admin, f"/archive/{item['id']}/restore").status_code == 409


def test_roles(client, admin):
    _, findings, _ = _setup(client, admin)
    viewer = member(client, admin[0], admin[1], "viewer")
    auditor = member(client, admin[0], admin[1], "auditor")

    assert _post(client, admin, f"/scans/{findings}/archive", headers=viewer).status_code == 403
    assert _post(client, admin, f"/scans/{findings}/archive", headers=auditor).status_code == 200
    [item] = _archived(client, admin, "upload")
    assert client.get(_url(admin, "/archive"), headers=viewer, params={"item_type": "upload"}).status_code == 200
    assert _post(client, admin, f"/archive/{item['id']}/purge", headers=auditor).status_code == 403
    assert client.get(_url(admin, "/purge-log"), headers=auditor).status_code == 403
    assert _post(client, admin, f"/archive/{item['id']}/restore", headers=viewer).status_code == 403
    assert _post(client, admin, f"/archive/{item['id']}/restore", headers=auditor).status_code == 200
    other_org = register(client, "someone@else.io", org_name="Else")
    assert _post(client, admin, f"/scans/{findings}/archive", headers=other_org).status_code == 403


def test_auto_purge_after_the_orgs_retention(client, admin, db_session):
    _, findings, other = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    now = datetime.now(timezone.utc)

    assert archive_service.purge_expired(db_session, now + timedelta(days=179)) == 0
    # The org keeps archived items for a year instead.
    resp = client.patch(_url(admin, "/settings"), headers=admin[0], json={"archive_retention_days": 365})
    assert resp.json()["archive_retention_days"] == 365
    [item] = _archived(client, admin, "upload")
    assert datetime.fromisoformat(item["purge_at"]) - datetime.fromisoformat(item["archived_at"]) == timedelta(days=365)
    assert archive_service.purge_expired(db_session, now + timedelta(days=200)) == 0
    assert archive_service.purge_expired(db_session, now + timedelta(days=366)) == 1

    assert _archived(client, admin, "upload") == []
    [entry] = _get(client, admin, "/purge-log")["items"]
    assert entry["reason"] == "auto" and entry["purged_by"] is None


def test_large_jobs_run_in_the_background_a_chunk_at_a_time(client, admin, monkeypatch):
    _, findings, _ = _setup(client, admin)
    monkeypatch.setattr(settings, "ARCHIVE_SYNC_MAX_ROWS", 0)
    monkeypatch.setattr(archive_service, "CHUNK", 1)

    resp = _post(client, admin, f"/scans/{findings}/archive")
    assert resp.status_code == 202
    # (TestClient has run the background task by now.)
    [job] = _get(client, admin, "/archive-jobs", tracked="true")
    assert job["status"] == "completed" and job["summary"]["findings"] == 3
    assert _findings(client, admin) == ["BKP"]
    assert _post(client, admin, f"/archive-jobs/{job['id']}/dismiss").status_code == 200
    assert _get(client, admin, "/archive-jobs", tracked="true") == []


def test_a_job_that_stopped_half_way_carries_on_when_started_again(client, admin, db_session, monkeypatch):
    _, findings, _ = _setup(client, admin)
    monkeypatch.setattr(archive_service, "CHUNK", 1)
    in_chunks = archive_service._Runner._in_chunks
    calls = {"n": 0}

    def stop_after_first_step(self, phase, ids, sql):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("server stopped")
        return in_chunks(self, phase, ids, sql)

    monkeypatch.setattr(archive_service._Runner, "_in_chunks", stop_after_first_step)
    job = _post(client, admin, f"/scans/{findings}/archive").json()
    assert job["status"] == "failed"
    [batch] = db_session.query(ArchiveBatch).all()
    assert batch.state == ArchiveState.archiving
    assert _findings(client, admin) == ["BKP"]  # the findings step had finished
    # Not on the Archived page yet: still an upload, marked as stopped part-way.
    assert _archived(client, admin, "upload") == []
    [row] = [u for u in _get(client, admin, "/uploads")["items"] if u["id"] == findings]
    assert row["archiving"] == "stopped"

    monkeypatch.setattr(archive_service._Runner, "_in_chunks", in_chunks)
    job = _post(client, admin, f"/scans/{findings}/archive").json()
    assert job["status"] == "completed" and job["batch_id"] == str(batch.id)
    assert job["summary"] == {"uploads": 1, "assets": 1, "findings": 3}


def test_jobs_cut_off_by_a_restart_are_marked_failed(client, admin, db_session):
    _, findings, _ = _setup(client, admin)
    job = archive_service.start_archive(
        db_session, uuid.UUID(admin[1]), ArchiveItemType.upload, uuid.UUID(findings), None
    )
    assert archive_service.fail_interrupted_jobs(db_session) == 1
    assert db_session.get(ArchiveJob, job.id).status == ScanStatus.failed
    # ...so it can be started again.
    assert _post(client, admin, f"/scans/{findings}/archive").json()["status"] == "completed"


def test_an_upload_still_importing_cant_be_archived(client, admin, db_session):
    _, findings, _ = _setup(client, admin)
    db_session.get(Scan, uuid.UUID(findings)).status = ScanStatus.running
    db_session.commit()
    resp = _post(client, admin, f"/scans/{findings}/archive")
    assert resp.status_code == 409 and "still importing" in resp.json()["detail"]


def test_the_same_file_again_warns_until_confirmed(client, admin):
    _import(client, admin, "assets", INVENTORY, "inv.csv")

    resp = upload(client, _url(admin, "/assets/import"), admin[0], "copy.csv", INVENTORY, confirm=False)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    imported_at = datetime.fromisoformat(detail["imported_at"])
    assert abs(datetime.now(timezone.utc) - imported_at) < timedelta(minutes=1)
    assert detail["imported_by"] == "owner@acmecorp.io"
    assert detail["message"] == (
        f"This exact file was already imported on {imported_at:%d %b %Y %H:%M} UTC by owner@acmecorp.io."
    )
    assert len(_get(client, admin, "/uploads")["items"]) == 1

    assert _import(client, admin, "assets", INVENTORY, "copy.csv", confirm=True)
    # A different file is fine.
    assert _import(client, admin, "assets", INVENTORY + b"server,new-03\n", confirm=False)


def test_failed_and_archived_uploads_dont_count_as_already_imported(client, admin):
    bad = b"type,hostname\nnot-a-type,x\n"
    resp = upload(client, _url(admin, "/assets/import"), admin[0], "bad.csv", bad, confirm=False)
    assert resp.json()["status"] == "failed"
    assert upload(client, _url(admin, "/assets/import"), admin[0], "bad.csv", bad, confirm=False).status_code == 201

    scan_id = _import(client, admin, "findings", FINDINGS, confirm=False)
    _post(client, admin, f"/scans/{scan_id}/archive")
    assert _import(client, admin, "findings", FINDINGS, confirm=False)


def test_the_uploads_list_pages_sorts_and_searches(client, admin):
    _setup(client, admin)
    page = _get(client, admin, "/uploads", sort="filename", order="asc", limit=2)
    assert page["total"] == 3
    assert [u["filename"] for u in page["items"]] == ["findings.csv", "inv.csv"]
    assert page["items"][0]["uploaded_by"] == "owner@acmecorp.io"
    assert "errors" not in page["items"][0]["summary"]
    assert [u["filename"] for u in _get(client, admin, "/uploads", q="othe")["items"]] == ["other.csv"]


def test_lists_say_which_rows_are_being_archived(client, admin, db_session):
    _, findings, _ = _setup(client, admin)
    own_02 = next(a for a in _get(client, admin, "/assets")["items"] if a["hostname"] == "own-02")
    manual = client.post(
        _url(admin, "/findings"), headers=admin[0], json={"domain": "incident_response", "severity": "low", "category": "IR"}
    ).json()
    org_id = uuid.UUID(admin[1])
    for item_type, item_id in (
        (ArchiveItemType.upload, findings),
        (ArchiveItemType.asset, own_02["id"]),
        (ArchiveItemType.finding, manual["id"]),
    ):
        archive_service.start_archive(db_session, org_id, item_type, uuid.UUID(item_id), None)  # pending: running

    assert {u["id"]: u["archiving"] for u in _get(client, admin, "/uploads")["items"]}[findings] == "running"
    assert {a["id"]: a["archiving"] for a in _get(client, admin, "/assets")["items"]}[own_02["id"]] == "running"
    assert {f["id"]: f["archiving"] for f in _get(client, admin, "/findings")["items"]}[manual["id"]] == "running"
    archive_service.fail_interrupted_jobs(db_session)
    assert {a["id"]: a["archiving"] for a in _get(client, admin, "/assets")["items"]}[own_02["id"]] == "stopped"
    others = [a["archiving"] for a in _get(client, admin, "/assets")["items"] if a["id"] != own_02["id"]]
    assert set(others) == {None}


def test_the_archived_page_says_what_a_job_is_doing(client, admin, db_session):
    _, findings, _ = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    [item] = _archived(client, admin, "upload")
    assert item["running"] is None
    archive_service.start_batch_job(db_session, uuid.UUID(admin[1]), uuid.UUID(item["id"]), ArchiveAction.purge, None)
    [item] = _archived(client, admin, "upload")
    assert item["running"] == "purge"


def test_an_archive_that_stopped_part_way_can_be_undone(client, admin, monkeypatch):
    _, findings, _ = _setup(client, admin)
    before = _findings(client, admin)
    in_chunks = archive_service._Runner._in_chunks
    calls = {"n": 0}

    def stop_after_first_step(self, phase, ids, sql):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("server stopped")
        return in_chunks(self, phase, ids, sql)

    monkeypatch.setattr(archive_service._Runner, "_in_chunks", stop_after_first_step)
    _post(client, admin, f"/scans/{findings}/archive")
    monkeypatch.setattr(archive_service._Runner, "_in_chunks", in_chunks)
    [row] = [u for u in _get(client, admin, "/uploads")["items"] if u["id"] == findings]
    assert row["archiving"] == "stopped" and _findings(client, admin) == ["BKP"]

    job = _post(client, admin, f"/archive/{row['archiving_batch_id']}/restore").json()
    assert job["status"] == "completed" and job["summary"]["findings"] == 3
    assert _findings(client, admin) == before
    [row] = [u for u in _get(client, admin, "/uploads")["items"] if u["id"] == findings]
    assert row["archiving"] is None and row["archiving_batch_id"] is None
    assert _archived(client, admin, "upload") == []
    # Archiving it later starts afresh.
    job = _post(client, admin, f"/scans/{findings}/archive").json()
    assert job["summary"] == {"uploads": 1, "assets": 1, "findings": 3}


def test_links_record_which_upload_created_each_asset(client, admin, db_session):
    inventory, findings, other = _setup(client, admin)
    host_of = {uuid.UUID(a["id"]): a["hostname"] for a in _get(client, admin, "/assets")["items"]}
    created = {}
    for link in db_session.query(AssetScan):
        created.setdefault(str(link.scan_id), {})[host_of[link.asset_id]] = link.created
    assert created[inventory] == {"shared-01": True, "inv-02": True}
    # The findings upload created own-01 and own-02 and only matched shared-01.
    assert created[findings] == {"shared-01": False, "own-01": True, "own-02": True}
    assert created[other] == {"own-02": False}


def test_archiving_an_upload_never_takes_an_asset_it_only_matched(client, admin, db_session):
    """An asset added by hand while a large upload waited its turn, then
    matched by it: newer than the upload, but not created by it."""
    org_id = uuid.UUID(admin[1])
    started = datetime.now(timezone.utc)
    scan = Scan(
        org_id=org_id, scan_type="asset_import", source="upload", status=ScanStatus.completed,
        started_at=started, filename="queued.csv",
    )
    by_hand = Asset(org_id=org_id, type="server", hostname="by-hand", created_at=started + timedelta(seconds=30))
    db_session.add_all([scan, by_hand])
    db_session.flush()
    db_session.add(AssetScan(scan_id=scan.id, asset_id=by_hand.id, created=False))
    db_session.commit()

    job = _post(client, admin, f"/scans/{scan.id}/archive").json()
    assert job["summary"] == {"uploads": 1, "assets": 0, "findings": 0}
    assert "by-hand" in _hosts(client, admin)


def test_overlapping_requests_start_one_job_per_item(client, admin, db_session):
    """A double click, or a purge by hand while the daily purge runs: both
    requests check "nothing running" before either has saved its job."""
    _, findings, _ = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    [item] = _archived(client, admin, "upload")
    make = sessionmaker(bind=db_session.get_bind())
    both_checked = threading.Barrier(2, timeout=5)
    outcomes = []

    def request():
        db = make()
        real_scalars = db.scalars

        def scalars(*args, **kwargs):  # the busy check; then give the other request its turn
            first = real_scalars(*args, **kwargs).first()
            try:
                both_checked.wait()
            except threading.BrokenBarrierError:
                pass  # the other request is waiting for the lock: as it should
            return type("Result", (), {"first": lambda self: first})()

        db.scalars = scalars
        try:
            archive_service.start_batch_job(db, uuid.UUID(admin[1]), uuid.UUID(item["id"]), ArchiveAction.purge, None)
            outcomes.append("started")
        except archive_service.ArchiveError as exc:
            outcomes.append(str(exc))
        finally:
            db.close()

    threads = [threading.Thread(target=request) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["Another archive, restore or purge of this item is already running", "started"]


def test_purge_leaves_findings_restored_meanwhile(client, admin, db_session):
    _, findings, _ = _setup(client, admin)
    _post(client, admin, f"/scans/{findings}/archive")
    [item] = _archived(client, admin, "upload")
    job = archive_service.start_batch_job(
        db_session, uuid.UUID(admin[1]), uuid.UUID(item["id"]), ArchiveAction.purge, None
    )
    read_ids = archive_service._Runner._ids

    def ids_then_restore_one(self, sql):
        ids = read_ids(self, sql)
        if "FROM findings WHERE archive_batch_id" in sql:
            # CVE-1, on shared-01 (an asset that stayed active).
            self.db.execute(Finding.__table__.update().where(Finding.category == "CVE-1").values(archived_at=None))
            self.db.commit()
        return ids

    archive_service._Runner._ids = ids_then_restore_one
    try:
        archive_service.run_job(db_session, job.id)
    finally:
        archive_service._Runner._ids = read_ids
    assert _findings(client, admin) == ["BKP", "CVE-1"]


def test_undo_of_a_large_stopped_archive_runs_in_the_background(client, admin, db_session, monkeypatch):
    _, findings, _ = _setup(client, admin)
    monkeypatch.setattr(settings, "ARCHIVE_SYNC_MAX_ROWS", 2)
    in_chunks = archive_service._Runner._in_chunks
    calls = {"n": 0}

    def stop_after_first_step(self, phase, ids, sql):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("server stopped")
        return in_chunks(self, phase, ids, sql)

    monkeypatch.setattr(archive_service._Runner, "_in_chunks", stop_after_first_step)
    _post(client, admin, f"/scans/{findings}/archive")  # 1 row: runs in the request, then stops
    monkeypatch.setattr(archive_service._Runner, "_in_chunks", in_chunks)
    [row] = [u for u in _get(client, admin, "/uploads")["items"] if u["id"] == findings]

    # 3 findings archived before it stopped: more than the 2 run in the request.
    resp = _post(client, admin, f"/archive/{row['archiving_batch_id']}/restore")
    assert resp.status_code == 202
