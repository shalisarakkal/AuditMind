"""Ledger foundation: no public disposition writes or finding-state changes."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from app.models.finding import Finding
from app.models.finding_suppression import FindingSuppression as Registry, FindingSuppressionDecision as Decision
from app.models.user import User
from app.models.membership import OrgMembership
from app.services.finding_suppressions import append_transition
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member, upload

pytestmark = requires_db


@pytest.fixture
def owner(client):
    headers = register(client, "suppression-ledger@example.io")
    return headers, uuid.UUID(first_org_id(client, headers))


def registry(db, owner, **changes):
    values = dict(org_id=owner[1], identity_version="finding-identity-v1",
        candidate_key="finding-identity-v1:" + "a" * 64, identity={"contract": "synthetic fixture"},
        finding_id=uuid.uuid4(), version=1, state="suppressed")
    values.update(changes)
    row = Registry(**values)
    db.add(row)
    db.flush()
    return row


def append(db, owner, row, **changes):
    actor_id = db.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == owner[1]))
    values = dict(org_id=owner[1], suppression_id=row.id, request_id=uuid.uuid4(), expected_version=0,
        state="suppressed", rationale="Reviewed fixture only", actor_id=actor_id,
        actor_label="Ledger test administrator", context={"preview": "retained synthetic context"})
    values.update(changes)
    return append_transition(db, **values)


def path(owner):
    return f"/api/v1/orgs/{owner[1]}/finding-suppressions"


def test_read_api_is_explicitly_not_available_for_mutation(client, owner, db_session):
    before = db_session.scalar(select(func.count(Finding.id)))
    response = client.get(path(owner), headers=owner[0])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == dict(items=[], has_more=False, limit=50, offset=0,
        mutations_available=True,
        availability_reason="Only current reviewed native Nessus identities are eligible. New uploads require identity review.")
    assert client.post(path(owner), headers=owner[0], json={}).status_code == 405
    assert db_session.scalar(select(func.count(Finding.id))) == before
    assert db_session.scalar(select(func.count(Registry.id))) == 0


def test_paged_read_and_history_are_tenant_scoped_and_bounded(client, owner, db_session):
    row = registry(db_session, owner)
    first = append(db_session, owner, row)
    append(db_session, owner, row, expected_version=1, state="cleared", rationale="Cleared by reviewer")
    for i in range(2):
        registry(db_session, owner, candidate_key=f"finding-identity-v1:{i:064x}")
    db_session.commit()
    response = client.get(path(owner), headers=owner[0], params=dict(state="all", limit=2))
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 2 and body["has_more"] is True
    assert all("identity" not in item for item in body["items"])
    assert len(client.get(path(owner), headers=owner[0], params=dict(state="all", limit=2, offset=2)).json()["items"]) == 1
    assert len(client.get(path(owner), headers=owner[0], params=dict(state="cleared")).json()["items"]) == 1
    route = f"{path(owner)}/{row.id}/history"
    history = client.get(route, headers=owner[0], params=dict(limit=1))
    assert history.status_code == 200 and history.json()["has_more"] is True
    assert history.headers["cache-control"] == "no-store"
    assert history.json()["items"][0]["version"] == 2
    assert "context" not in history.json()["items"][0]
    history = client.get(route, headers=owner[0], params=dict(limit=1, before_version=2))
    assert history.json()["items"][0]["id"] == str(first.id)
    assert history.json()["has_more"] is False
    foreign = register(client, "suppression-foreign@example.io")
    assert client.get(route, headers=foreign).status_code == 403
    foreign_org = first_org_id(client, foreign)
    assert client.get(f"/api/v1/orgs/{foreign_org}/finding-suppressions/{row.id}/history", headers=foreign).status_code == 404
    assert client.get(path(owner)).status_code == 401
    assert client.get(f"{path(owner)}/{uuid.uuid4()}/history", headers=owner[0]).status_code == 404


@pytest.mark.parametrize("role", ["viewer", "admin", "auditor"])
def test_members_can_read_without_mutation_authority(client, owner, role):
    headers = member(client, owner[0], str(owner[1]), role)
    assert client.get(path(owner), headers=headers).status_code == 200
    assert client.post(path(owner), headers=headers, json={}).status_code == 405


@pytest.mark.parametrize("params", [dict(limit=0), dict(limit=101), dict(offset=-1), dict(state="invalid")])
def test_invalid_read_bounds(client, owner, params):
    assert client.get(path(owner), headers=owner[0], params=params).status_code == 422


def test_append_is_versioned_idempotent_and_never_commits(db_session, owner):
    row = registry(db_session, owner)
    request = uuid.uuid4()
    first = append(db_session, owner, row, request_id=request)
    repeated = append(db_session, owner, row, request_id=request)
    assert repeated.id == first.id
    with pytest.raises(HTTPException) as conflict:
        append(db_session, owner, row, request_id=request, rationale="Different request")
    assert conflict.value.status_code == 409
    second = append(db_session, owner, row, expected_version=1, state="cleared")
    assert second.version == 2
    db_session.refresh(row)
    assert row.state == "cleared" and row.version == 2
    with pytest.raises(HTTPException):
        append(db_session, owner, row, expected_version=1, state="suppressed")
    with pytest.raises(HTTPException):
        append(db_session, owner, row, expected_version=2, state="cleared")
    assert db_session.scalar(select(func.count(Decision.id))) == 2
    db_session.rollback()
    assert db_session.get(Registry, row.id) is None
    assert db_session.scalar(select(func.count(Decision.id))) == 0


@pytest.mark.parametrize("changes", [dict(rationale=" "), dict(rationale="x" * 2001), dict(state="resolved"), dict(expected_version=-1), dict(actor_label=" ")])
def test_repository_rejects_invalid_transition(db_session, owner, changes):
    row = registry(db_session, owner)
    with pytest.raises(ValueError):
        append(db_session, owner, row, **changes)
    assert db_session.scalar(select(func.count(Decision.id))) == 0


def test_failed_append_does_not_advance_registry(db_session, owner):
    row = registry(db_session, owner)
    append(db_session, owner, row)
    db_session.commit()
    # Invalid actor FK makes the decision fail after registry UPDATE. The local
    # savepoint must roll back both, allowing the caller to continue safely.
    with pytest.raises(IntegrityError):
        append(db_session, owner, row, expected_version=1, state="cleared", actor_id=uuid.uuid4())
    db_session.refresh(row)
    assert row.state == "suppressed" and row.version == 1
    assert db_session.scalar(select(func.count(Decision.id))) == 1
    db_session.commit()


def test_source_purge_and_actor_deletion_retain_minimal_ledger(client, owner, db_session):
    response = upload(client, f"/api/v1/orgs/{owner[1]}/findings/import", owner[0], "retention.json",
        b'[{"hostname":"retained-ledger-host","domain":"network_config","severity":"high","description":"Synthetic retention fixture"}]')
    assert response.status_code == 201, response.text
    finding = db_session.scalar(select(Finding).where(Finding.org_id == owner[1]))
    row = registry(db_session, owner, finding_id=finding.id)
    decision = append(db_session, owner, row)
    actor_id = decision.actor_id
    db_session.commit()
    db_session.delete(finding)
    db_session.commit()
    db_session.refresh(row)
    assert row.finding_id and row.state == "suppressed"
    # Remove membership first to keep organization lifecycle independent of actor.
    db_session.execute(delete(OrgMembership).where(OrgMembership.user_id == actor_id))
    db_session.execute(delete(User).where(User.id == actor_id))
    db_session.commit()
    db_session.refresh(decision)
    assert decision.actor_id is None and decision.actor_label == "Ledger test administrator"
    assert decision.rationale == "Reviewed fixture only"


def test_database_enforces_registry_identity_and_cross_tenant_owner(client, owner, db_session):
    row = registry(db_session, owner)
    append(db_session, owner, row)
    db_session.commit()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        registry(db_session, owner)
    other_headers = register(client, "suppression-owner@example.io")
    other_org = uuid.UUID(first_org_id(client, other_headers))
    # Same native key is legal in a different organization.
    registry(db_session, (other_headers, other_org))
    db_session.commit()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(Decision(org_id=other_org, suppression_id=row.id, request_id=uuid.uuid4(),
            request_hash="b"*64, version=2, state="cleared", context={}, rationale="Foreign owner", actor_label="Other"))
        db_session.flush()


@pytest.mark.parametrize("same_request", [False, True])
def test_independent_writers_do_not_overwrite_or_duplicate(db_session, owner, same_request):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    row = registry(db_session, owner)
    append(db_session, owner, row)
    db_session.commit()
    row_id = row.id
    actor = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == owner[1]))
    db_session.rollback()
    barrier = Barrier(2)
    common_request = uuid.uuid4()
    engine = db_session.get_bind()

    def decide(index):
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                decision = append_transition(independent, org_id=owner[1], suppression_id=row_id,
                    request_id=common_request if same_request else uuid.uuid4(), expected_version=1,
                    state="cleared", rationale="Independent reviewer", actor_id=actor,
                    actor_label="Reviewer", context={"synthetic": True})
                identifier = decision.id
                independent.commit()
                return "ok", identifier
            except HTTPException as exc:
                independent.rollback()
                return exc.status_code, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, range(2)))
    assert sum(result[0] == "ok" for result in results) == (2 if same_request else 1)
    if same_request:
        assert results[0][1] == results[1][1]
    else:
        assert any(result[0] == 409 for result in results)
    db_session.expire_all()
    saved = db_session.get(Registry, row_id)
    assert saved.version == 2 and saved.state == "cleared"
    assert db_session.scalar(select(func.count(Decision.id))) == 2


def test_read_queries_remain_bounded_without_payload_or_exact_count(db_session, owner):
    from sqlalchemy import event
    from app.services.finding_suppressions import page, history
    row = registry(db_session, owner)
    append(db_session, owner, row)
    for index in range(15):
        registry(db_session, owner, candidate_key=f"finding-identity-v1:{index:064x}")
    db_session.commit()
    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    row_id = row.id
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", observe)
    try:
        assert len(page(db_session, owner[1], state="all", limit=10, offset=0).items) == 10
        assert len(history(db_session, owner[1], row_id, limit=10, before_version=None).items) == 1
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert len(statements) == 3
    assert all("count(" not in statement.lower() for statement in statements)
    assert all(".identity," not in statement and ".context" not in statement for statement in statements)


def test_concurrent_request_reuse_across_targets_is_a_clean_conflict(db_session, owner):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    targets = [registry(db_session, owner, candidate_key=f"finding-identity-v1:{i:064x}") for i in (7, 8)]
    for row in targets:
        append(db_session, owner, row)
    db_session.commit()
    ids = [row.id for row in targets]
    actor = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == owner[1]))
    db_session.rollback()
    request = uuid.uuid4()
    barrier = Barrier(2)
    engine = db_session.get_bind()

    def decide(identifier):
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                append_transition(independent, org_id=owner[1], suppression_id=identifier,
                    request_id=request, expected_version=1, state="cleared", rationale="Concurrent reuse",
                    actor_id=actor, actor_label="Reviewer", context={})
                independent.commit()
                return 200
            except HTTPException as exc:
                independent.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(decide, ids)) == [200, 409]
    db_session.expire_all()
    assert sorted(db_session.scalars(select(Registry.version)).all()) == [1, 2]
    assert db_session.scalar(select(func.count(Decision.id))) == 3


def test_request_fence_is_independent_of_platform_scoring_lock(db_session, owner, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app.services import finding_suppressions as service
    row = registry(db_session, owner)
    append(db_session, owner, row)
    db_session.commit()
    request = uuid.uuid4()
    request_material = f"{owner[1]}:{request}".encode()
    original_hash = service.hashlib.sha256

    class ForcedZeroKey:
        def digest(self):
            return bytes(32)

    def hash_with_zero_key(material):
        return ForcedZeroKey() if material == request_material else original_hash(material)

    monkeypatch.setattr(service.hashlib, "sha256", hash_with_zero_key)
    with Session(db_session.get_bind()) as platform:
        platform.execute(select(func.pg_advisory_xact_lock(15, 0)))
        try:
            db_session.execute(text("SET LOCAL lock_timeout='500ms'"))
            decision = append(db_session, owner, row, request_id=request, expected_version=1, state="cleared")
            assert decision.version == 2
            db_session.commit()
        finally:
            platform.rollback()
