"""Organization-scoped exact-file admission policy; real PostgreSQL locks."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
import uuid

import pytest
from fastapi import Response, UploadFile
from sqlalchemy.orm import sessionmaker

from app.api.uploads import start_import
from app.core.config import settings
from app.models.enums import ScanStatus
from app.models.event import Event
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import FIXTURES, first_org_id, member, register

pytestmark = requires_db
CONTENT = b"type,hostname,domain,severity,category,description\nserver,exact-host,network_config,high,EXACT,test\n"


@pytest.fixture
def owner(client):
    headers = register(client, "duplicate-owner@example.io")
    return headers, first_org_id(client, headers)


def policy(client, owner, value):
    headers, org = owner
    return client.patch(f"/api/v1/orgs/{org}/settings", headers=headers, json={"exact_duplicate_file_policy": value})


def send(client, owner, path="assets/import", content=CONTENT, confirm=False, fields=None):
    headers, org = owner
    return client.post(f"/api/v1/orgs/{org}/{path}", headers=headers,
                       files={"file": ("same.csv", content, "text/csv")},
                       data={"confirm": str(confirm).lower(), **(fields or {})})


@pytest.mark.parametrize("mode", ["ask", "skip", "reimport"])
def test_completed_duplicate_modes(client, owner, db_session, mode):
    assert policy(client, owner, mode).status_code == 200
    first = send(client, owner)
    assert first.status_code == 201, first.text
    second = send(client, owner)
    assert second.status_code == {"ask": 409, "skip": 200, "reimport": 201}[mode], second.text
    assert db_session.query(Scan).count() == (2 if mode == "reimport" else 1)
    if mode == "skip":
        assert second.json()["skipped"] is True
        assert second.json()["scan_id"] == first.json()["scan_id"]
        assert second.json()["report"] is None
        [event] = db_session.query(Event).filter_by(type="upload_skipped").all()
        assert event.details["matched_scan_id"] == first.json()["scan_id"]
    if mode == "ask":
        assert send(client, owner, confirm=True).status_code == 201


@pytest.mark.parametrize("path,fields,content", [
    ("assets/import", {}, CONTENT),
    ("findings/import", {}, CONTENT),
    ("imports", {"profile": "network_scan"}, (FIXTURES / "network_scan.csv").read_bytes()),
])
def test_skip_applies_to_all_import_endpoints_and_cannot_be_overridden_by_confirm(client, owner, path, fields, content):
    assert policy(client, owner, "skip").status_code == 200
    assert send(client, owner, path, content, fields=fields).status_code == 201
    response = send(client, owner, path, content, confirm=True, fields=fields)
    assert response.status_code == 200, response.text
    assert response.json()["skipped"] is True


@pytest.mark.parametrize("mode", ["ask", "skip", "reimport"])
def test_inflight_duplicate_never_creates_a_second_job(client, owner, db_session, monkeypatch, mode):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 1)
    policy(client, owner, mode)
    first = send(client, owner)
    assert first.status_code == 202
    for state in [ScanStatus.pending, ScanStatus.running]:
        scan = db_session.get(Scan, uuid.UUID(first.json()["scan_id"]))
        scan.status = state
        db_session.commit()
        second = send(client, owner, confirm=True)
        assert second.status_code == 200
        assert second.json()["skipped"] is True
    assert db_session.query(Scan).count() == 1
    assert len(list(settings.upload_dir.glob("*.upload"))) == 1


@pytest.mark.parametrize("state", ["failed", "archived"])
def test_failed_or_archived_import_does_not_prevent_a_new_attempt(client, owner, db_session, state):
    policy(client, owner, "skip")
    first = send(client, owner)
    scan = db_session.get(Scan, uuid.UUID(first.json()["scan_id"]))
    if state == "failed":
        scan.status = ScanStatus.failed
    else:
        from datetime import datetime, timezone
        scan.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert send(client, owner).status_code == 201


def test_policy_validation_reset_permissions_and_org_isolation(client, owner):
    assert policy(client, owner, "invalid").status_code == 422
    assert policy(client, owner, "skip").json()["exact_duplicate_file_policy"] == "skip"
    headers, org = owner
    viewer = member(client, headers, org, "viewer")
    assert client.patch(f"/api/v1/orgs/{org}/settings", headers=viewer, json={"exact_duplicate_file_policy": "reimport"}).status_code == 403
    assert send(client, owner).status_code == 201
    foreign = register(client, "other-duplicate-owner@example.io")
    other = (foreign, first_org_id(client, foreign))
    assert send(client, other).status_code == 201
    assert policy(client, owner, None).json()["exact_duplicate_file_policy"] == "ask"


def test_simultaneous_same_hash_admission_creates_one_job(client, owner, db_session, monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_SYNC_MAX_BYTES", 1)
    policy(client, owner, "reimport")
    org_id = uuid.UUID(owner[1])
    from app.models.user import User
    user_id = db_session.query(User).filter_by(email="duplicate-owner@example.io").one().id
    Session = sessionmaker(bind=db_session.get_bind())
    barrier = Barrier(2)

    def submit(_):
        with Session() as db:
            barrier.wait(timeout=10)
            response = Response()
            result = asyncio.run(start_import(db=db, response=response, org_id=org_id,
                file=UploadFile(file=BytesIO(CONTENT), filename="race.csv"), kind="assets", started_by=user_id))
            return response.status_code, result.skipped

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(results) == [(200, True), (202, False)]
    db_session.expire_all()
    assert db_session.query(Scan).filter_by(org_id=org_id).count() == 1
