"""Two distinct organization admins compete without sharing an ORM session."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from datetime import timedelta
from uuid import UUID, uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.api.deps import authorize_org_write
from app.models.enums import UserRole
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_observation import FindingObservation
from app.models.membership import OrgMembership
from app.services.org_lock import lock_org
from app.schemas.identity_binding import CanonicalSelection
from app.services.finding_canonical import save
from tests.conftest import requires_db
from tests.helpers import member
from tests.integration.test_identity_bindings import prepared  # noqa: F401
from tests.integration.test_identity_comparison import pair  # noqa: F401
from tests.integration.test_finding_canonical import conflict, payload, preview  # noqa: F401

pytestmark = requires_db


def test_two_independent_admins_record_one_canonical_decision(client, db_session, conflict):
    member(client, conflict[0], conflict[1], "admin")
    response = preview(client, conflict)
    assert response.status_code == 200, response.text
    request = payload(conflict, response.json())
    org_id, target_id = UUID(conflict[1]), conflict[4].id
    actors = list(db_session.scalars(select(OrgMembership.user_id).where(OrgMembership.org_id == org_id)))
    assert len(actors) == 2
    engine = db_session.get_bind()
    db_session.commit()
    barrier = Barrier(2)

    def submit(index):
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            barrier.wait(timeout=10)
            try:
                authorize_org_write(db, org_id, actors[index], (UserRole.admin,))
                save(db, org_id, db.get(FindingObservation, target_id), actors[index], CanonicalSelection(**request))
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [200, 409]
    decisions = db_session.scalars(select(FindingCanonicalDecision)).all()
    assert len(decisions) == 1 and decisions[0].actor_id in actors


def test_import_publishing_new_observation_serializes_with_canonical_save(client, db_session, conflict):
    preview_response = preview(client, conflict)
    assert preview_response.status_code == 200, preview_response.text
    request = payload(conflict, preview_response.json())
    org_id, target = UUID(conflict[1]), conflict[4]
    target_values = dict(finding_id=target.finding_id, scan_id=target.scan_id,
        source=target.source, scan_type=target.scan_type, profile=target.profile,
        observed_at=target.observed_at, recorded_at=target.recorded_at,
        asset_identity=target.asset_identity, source_identity=target.source_identity,
        payload=target.payload)
    actor_id = db_session.scalar(select(OrgMembership.user_id).where(
        OrgMembership.org_id == org_id, OrgMembership.role == UserRole.admin))
    engine = db_session.get_bind()
    db_session.commit()
    import_locked, allow_import_commit, save_started = Event(), Event(), Event()
    save_backend_pid = []

    def publish_observation():
        with Session(engine) as db:
            lock_org(db, org_id)
            db.add(FindingObservation(id=uuid4(), org_id=org_id,
                finding_id=target_values["finding_id"], import_id=uuid4(), scan_id=target_values["scan_id"],
                occurrence=1, source_row=1, source=target_values["source"], scan_type=target_values["scan_type"],
                profile=target_values["profile"], filename="concurrent-import.nessus",
                observed_at=target_values["observed_at"], recorded_at=target_values["recorded_at"] + timedelta(seconds=1),
                asset_identity=target_values["asset_identity"], source_identity=target_values["source_identity"],
                reconciliation_eligible=False, ineligibility_reasons=[], payload=target_values["payload"]))
            db.flush()
            import_locked.set()
            assert allow_import_commit.wait(timeout=10), "Timed out waiting to commit synthetic import"
            db.commit()

    def save_selection():
        with Session(engine) as db:
            authorize_org_write(db, org_id, actor_id, (UserRole.admin,))
            save_backend_pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            save_started.set()
            try:
                save(db, org_id, db.get(FindingObservation, target.id), actor_id, CanonicalSelection(**request))
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        importer = pool.submit(publish_observation)
        assert import_locked.wait(timeout=10)
        saver = pool.submit(save_selection)
        assert save_started.wait(timeout=10)
        try:
            # The save must wait on the import publication lock, then reject the
            # preview after the new observation becomes visible.
            with engine.connect() as observer:
                from time import monotonic, sleep
                deadline = monotonic() + 10
                blocked = False
                while monotonic() < deadline:
                    blocked = observer.execute(text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE pid=:pid AND datname=current_database() "
                        "AND wait_event_type='Lock' AND wait_event='advisory')"),
                        {"pid": save_backend_pid[0]}).scalar_one()
                    if blocked:
                        break
                    if saver.done():
                        break
                    sleep(0.02)
            assert blocked, "Canonical save did not wait for the active import publication"
        finally:
            allow_import_commit.set()
        importer.result(timeout=10)
        save_result = saver.result(timeout=10)
        assert blocked, f"Canonical save did not wait for import publication (result={save_result})"
        assert save_result == 409

    assert db_session.scalars(select(FindingCanonicalDecision)).all() == []
