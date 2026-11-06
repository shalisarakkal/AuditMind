"""History COPY batches must not multiply existing-asset rewrites."""
from collections import Counter

import pytest
from sqlalchemy import event
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.services import ingestion_service
from tests.conftest import requires_db
from tests.helpers import first_org_id, register

pytestmark = requires_db


@pytest.fixture
def owner(client):
    headers = register(client, "batching@example.io")
    return headers, first_org_id(client, headers)


def directory_file(rows, hosts):
    return ("Hostname,Type,Owner,Status\n" + "".join(
        f"repeat-{i % hosts},Server,owner-{i},Disabled\n" for i in range(rows))).encode()


def upload_directory(client, owner, rows, hosts):
    response = client.post(f"/api/v1/orgs/{owner[1]}/imports", headers=owner[0],
        files={"file": ("repeated-directory.csv", directory_file(rows, hosts))},
        data={"profile":"directory","confirm":"true"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed", response.text
    return response.json()


def count_updates(engine):
    counts = Counter()
    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lower().startswith("update assets as target set"):
            counts["bulk"] += 1
    return counts, record


def test_duplicate_history_batches_retain_per_asset_coalescing_and_last_values(client, owner, db_session, monkeypatch):
    hosts, rows = 100, 2000
    upload_directory(client,owner,hosts,hosts)
    monkeypatch.setattr(ingestion_service,"WRITE_BATCH",10)
    counts, record = count_updates(db_session.get_bind())
    copied = []
    original_copy = ingestion_service._copy_rows
    def copying(db, table, values):
        if table == "finding_observations": copied.append(len(values))
        return original_copy(db,table,values)
    monkeypatch.setattr(ingestion_service,"_copy_rows",copying)
    event.listen(db_session.get_bind(),"before_cursor_execute",record)
    try:
        result = upload_directory(client,owner,rows,hosts)
    finally:
        event.remove(db_session.get_bind(),"before_cursor_execute",record)
    assert sum(copied) == rows and max(copied) <= 10 and len(copied) > 1
    assert counts == {"bulk":1}
    assert result["report"]["duplicates"] == rows
    assert result["report"]["updated"] == hosts
    assert db_session.query(Finding).count() == hosts
    assert db_session.query(FindingObservation).count() == hosts + rows
    db_session.expire_all()
    assets = {a.hostname:a for a in db_session.query(Asset)}
    assert assets["repeat-99"].details["owner"] == "owner-1999"
    assert assets["repeat-0"].details["owner"] == "owner-1900"


def test_observation_batches_insert_pending_parents_before_children(client,owner,db_session,monkeypatch):
    monkeypatch.setattr(ingestion_service,"WRITE_BATCH",3)
    upload_directory(client,owner,25,5)
    assert db_session.query(Asset).count()==5
    assert db_session.query(Finding).count()==5
    assert db_session.query(FindingObservation).count()==25
    db_session.expire_all()
    assert db_session.query(Asset).filter_by(hostname="repeat-4").one().details["owner"]=="owner-24"


def test_failure_after_observation_only_copy_rolls_back_everything(client,owner,db_session,monkeypatch):
    upload_directory(client,owner,10,10)
    monkeypatch.setattr(ingestion_service,"WRITE_BATCH",3)
    original = ingestion_service._PendingWrites._flush_inserts
    def interrupted(writes):
        original(writes)
        raise RuntimeError("Synthetic interruption after history COPY")
    monkeypatch.setattr(ingestion_service._PendingWrites,"_flush_inserts",interrupted)
    with pytest.raises(RuntimeError,match="Synthetic interruption"):
        upload_directory(client,owner,30,10)
    db_session.rollback();db_session.expire_all()
    assert db_session.query(Asset).count()==10
    assert db_session.query(Finding).count()==10
    assert db_session.query(FindingObservation).count()==10
    assert db_session.query(Asset).filter_by(hostname="repeat-0").one().details["owner"]=="owner-0"


def test_existing_asset_update_bound_still_flushes(client,owner,db_session,monkeypatch):
    upload_directory(client,owner,100,100)
    monkeypatch.setattr(ingestion_service,"WRITE_BATCH",7)
    monkeypatch.setattr(ingestion_service,"UPDATE_BATCH",20)
    pending=[]
    original=ingestion_service._PendingWrites.flush
    def full_flush(writes):
        pending.append(max(len(writes.asset_updates),len(writes.details)))
        return original(writes)
    monkeypatch.setattr(ingestion_service._PendingWrites,"flush",full_flush)
    upload_directory(client,owner,100,100)
    assert max(pending)==20
    assert all(size<=20 for size in pending)
