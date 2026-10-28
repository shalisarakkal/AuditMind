"""Operational document reviews, scope integrity and fail-closed live evaluation."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.asset import Asset
from app.models.enums import Domain
from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
from app.models.scoring_qualification import DomainEvidenceQualification
from app.services.dashboard_evidence import evaluate_org
from app.services.evidence_policy import PROFILES
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register

pytestmark = requires_db


@pytest.mark.parametrize("spec_version", ["2.0", "2.4"])
def test_progress_disconnect_releases_snapshot_connection(reviewer, db_session, spec_version):
    import anyio
    import json
    from starlette.requests import ClientDisconnect
    from app.api.routes.scoring_qualifications import scoring_progress

    engine = db_session.get_bind()
    # Route authorization is already covered by HTTP tests. Here we force the
    # actual ASGI disconnect/send-failure branches after a real DB batch, which
    # TestClient's buffered response consumption does not simulate.
    baseline = engine.pool.checkedout()
    response = scoring_progress(uuid.UUID(reviewer[1]), "evaluation", db_session, None)
    disconnected = anyio.Event()

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            event = json.loads(message["body"])
            if event.get("processed", 0) > 0:
                disconnected.set()
                if spec_version == "2.4":
                    raise OSError("Synthetic disconnected client")
                await anyio.sleep_forever()

    async def exercise():
        # The route releases its authorization transaction before streaming.
        streaming_baseline = engine.pool.checkedout()
        if spec_version == "2.4":
            with pytest.raises(ClientDisconnect):
                await response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send)
        else:
            await response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send)
        assert engine.pool.checkedout() == streaming_baseline

    anyio.run(exercise)
    assert engine.pool.checkedout() <= baseline


def test_progress_matches_regular_evaluation_and_counts(client, reviewer):
    import json
    headers, org, path, _ = reviewer
    response = client.get(path + "/progress/evaluation", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["phase"] == "counting"
    assert all(event["type"] != "error" for event in events)
    result = events[-1]["data"]
    assert result["inventory"]["binding_version"] == "dashboard-organization-inventory-v2"
    assert result["inventory"] == client.get(path + "/inventory-scope", headers=headers).json()
    progress = [e for e in events if e.get("total") is not None]
    assert progress[-1]["processed"] == progress[-1]["total"]
    assert result["inventory"]["asset_count"] == 1
    assert result["qualified_domain_count"] == 0
    assert client.get(path + "/progress/evaluation").status_code == 401
    assert client.get(path + "/progress/unknown", headers=headers).status_code == 404
    outsider = register(client, "stream-outsider@example.io")
    assert client.get(path + "/progress/evaluation", headers=outsider).status_code == 403


def test_database_fingerprint_tracks_nested_payload_changes(client, reviewer, db_session):
    from sqlalchemy import select
    headers, org, path, _ = reviewer
    before = client.get(path + "/inventory-scope", headers=headers).json()
    asset = db_session.scalar(select(Asset).where(Asset.org_id == uuid.UUID(org)))
    asset.details = {"nested": {"z": "Unicode Ω", "a": [1, None, "test"]}}
    db_session.commit()
    changed = client.get(path + "/inventory-scope", headers=headers).json()
    assert changed["inventory_sha256"] != before["inventory_sha256"]
    asset.details = {"nested": {"a": [1, None, "test"], "z": "Unicode Ω"}}
    db_session.commit()
    assert client.get(path + "/inventory-scope", headers=headers).json() == changed


def test_stream_failure_is_explicit_and_does_not_expose_exception(client, reviewer, monkeypatch):
    from app.services import dashboard_evidence
    def failed(db, org):
        yield {"type": "progress", "phase": "counting"}
        raise RuntimeError("private database connection details")
    monkeypatch.setattr(dashboard_evidence, "inventory_progress", failed)
    response = client.get(reviewer[2] + "/progress/evaluation", headers=reviewer[0])
    assert '"type": "error"' in response.text
    assert '"type": "result"' not in response.text
    assert "private database" not in response.text


def test_previous_inventory_binding_version_requires_new_review(client, reviewer, db_session):
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    row = db_session.get(DomainEvidenceQualification, uuid.UUID(record["id"]))
    attestation = dict(row.review_attestation)
    attestation["inventory"] = {**attestation["inventory"], "binding_version": "dashboard-organization-inventory-v1"}
    row.review_attestation = attestation
    db_session.commit()
    response = client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()
    assert response["qualified_domain_count"] == 0
    assert any(d["reason_code"] == "scope_binding_invalid" for d in response["domains"])


def test_stream_evaluation_preserves_one_snapshot(client, reviewer, db_session, monkeypatch):
    import json
    from app.services import dashboard_evidence
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    original = dashboard_evidence.inventory_progress
    def changed(db, org):
        for event in original(db, org):
            if event["type"] == "result":
                version = db_session.get(KnowledgeVersion, reviewer[3])
                version.content = "Concurrent document update during streamed evaluation"
                version.content_hash = hashlib.sha256(version.content.encode()).hexdigest()
                db_session.commit()
            yield event
    monkeypatch.setattr(dashboard_evidence, "inventory_progress", changed)
    events = [json.loads(line) for line in client.get(reviewer[2] + "/progress/evaluation", headers=reviewer[0]).text.splitlines()]
    assert events[-1]["data"]["qualified_domain_count"] == 1
    monkeypatch.setattr(dashboard_evidence, "inventory_progress", original)
    assert client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()["qualified_domain_count"] == 0


@pytest.fixture
def reviewer(client, db_session):
    headers = register(client, "live-reviewer@example.io")
    org = first_org_id(client, headers)
    db_session.add(Asset(org_id=uuid.UUID(org), type="server", hostname="reviewed-host"))
    document = KnowledgeDocument(org_id=uuid.UUID(org), title="Synthetic operational observations")
    db_session.add(document)
    db_session.flush()
    content = "Synthetic scoped operational observations for reviewer tests, not a real audit."
    version = KnowledgeVersion(document_id=document.id, number=1, edition="test", source="synthetic",
        content_kind="organization_policy", rights="synthetic test data", content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(), current=True)
    db_session.add(version)
    db_session.commit()
    return headers, org, f"/api/v1/orgs/{org}/scoring", version.id


def make_draft(client, reviewer, domain="network_config", *, observed_at=None, scope="All active organization inventory", objectives=None):
    headers, _, path, version_id = reviewer
    source = client.get(path + f"/source-documents/{version_id}", headers=headers).json()
    inventory = client.get(path + "/inventory-scope", headers=headers).json()
    observations = [{"objective": objective, "source_type": source["source_type"], "source_id": source["source_id"],
        "source_sha256": source["source_sha256"], "observed_at": (observed_at or datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}
        for objective in (objectives if objectives is not None else PROFILES[domain])]
    payload = {"expected_version": 0, "scope": scope, "rationale": "Actual synthetic observations reviewed per objective",
               "observations": observations, "inventory_sha256": inventory["inventory_sha256"]}
    response = client.put(path + f"/qualifications/{domain}", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def review_payload(record, **overrides):
    return {"expected_version": record["version"], "inventory_sha256": record["inventory_sha256"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "note": "Reviewer confirms operational observations cover all required objectives and current inventory",
            "operational_review": True, "covers_entire_inventory": True, "conflicts_reviewed": True, **overrides}


def approve(client, reviewer, record, domain="network_config", **overrides):
    return client.post(reviewer[2] + f"/qualifications/{domain}/review", headers=reviewer[0], json=review_payload(record, **overrides))


def test_review_is_audited_partial_and_does_not_enable_dashboard(client, reviewer):
    record = make_draft(client, reviewer)
    response = approve(client, reviewer, record)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["status"] == "approved" and reviewed["version"] == 2
    assert reviewed["reviewed_by"] == reviewed["updated_by"]
    assert reviewed["review_attestation"]["covers_entire_inventory"] is True
    result = client.get(reviewer[2] + "/evaluation", headers=reviewer[0])
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["qualified_domain_count"] == 1
    assert result.json()["assessment_status"] == "partial"
    mode = client.get(reviewer[2] + "/settings", headers=reviewer[0]).json()
    assert mode["available"] is True and mode["evidence_qualified_enabled"] is False


@pytest.mark.parametrize("field", ["operational_review", "covers_entire_inventory", "conflicts_reviewed"])
def test_review_requires_explicit_attestations(client, reviewer, field):
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record, **{field: False}).status_code == 422


def test_missing_objective_or_unbound_inventory_cannot_be_approved(client, reviewer):
    record = make_draft(client, reviewer, objectives=[PROFILES["network_config"][0]])
    assert approve(client, reviewer, record).status_code == 409
    assert approve(client, reviewer, record, inventory_sha256="0" * 64).status_code == 409


@pytest.mark.parametrize("delta", [-1, 91])
def test_expiry_must_be_future_and_within_ninety_days(client, reviewer, delta):
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record, expires_at=(datetime.now(timezone.utc) + timedelta(days=delta)).isoformat()).status_code == 422


def test_old_observations_cannot_grant_fresh_qualification(client, reviewer):
    record = make_draft(client, reviewer, observed_at=datetime.now(timezone.utc) - timedelta(days=91))
    assert approve(client, reviewer, record).status_code == 409


@pytest.mark.parametrize("role", ["viewer", "auditor"])
def test_only_admin_can_review_and_revoke(client, reviewer, role):
    record = make_draft(client, reviewer)
    other = member(client, reviewer[0], reviewer[1], role)
    path = reviewer[2] + "/qualifications/network_config"
    assert client.post(path + "/review", headers=other, json=review_payload(record)).status_code == 403
    assert client.post(path + "/revoke", headers=other, json={"expected_version": 1, "note": "Not permitted"}).status_code == 403


def test_stale_reviews_and_revocations_cannot_overwrite_newer_state(client, reviewer):
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    assert approve(client, reviewer, record).status_code == 409
    path = reviewer[2] + "/qualifications/network_config/revoke"
    assert client.post(path, headers=reviewer[0], json={"expected_version": 1, "note": "stale"}).status_code == 409
    revoked = client.post(path, headers=reviewer[0], json={"expected_version": 2, "note": "Evidence requires re-review"})
    assert revoked.json()["status"] == "revoked" and revoked.json()["version"] == 3
    result = client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()
    assert result["qualified_domain_count"] == 0
    assert next(d for d in result["domains"] if d["domain"] == "network_config")["reason_code"] == "revoked"


def test_inventory_growth_invalidates_approval_and_prevents_stale_review(client, reviewer, db_session):
    record = make_draft(client, reviewer)
    db_session.add(Asset(org_id=uuid.UUID(reviewer[1]), type="server", hostname="new-unreviewed-host"))
    db_session.commit()
    assert approve(client, reviewer, record).status_code == 409


@pytest.mark.parametrize("change", ["inventory", "content", "retire", "expiry", "policy"])
def test_approved_records_are_revalidated_not_blindly_trusted(client, reviewer, db_session, change):
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    if change == "inventory":
        db_session.query(Asset).filter_by(org_id=uuid.UUID(reviewer[1])).one().hostname = "changed-host"
    elif change == "content":
        version = db_session.get(KnowledgeVersion, reviewer[3])
        version.content = "Materially changed observations"
        version.content_hash = hashlib.sha256(version.content.encode()).hexdigest()
    elif change == "retire":
        db_session.get(KnowledgeVersion, reviewer[3]).retired_at = datetime.now(timezone.utc)
    elif change == "policy":
        db_session.query(DomainEvidenceQualification).one().policy_version = "unknown-policy"
    db_session.commit()
    result = evaluate_org(db_session, uuid.UUID(reviewer[1]), now=datetime.now(timezone.utc) + (timedelta(days=8) if change == "expiry" else timedelta()))
    assert result["qualified_domain_count"] == 0
    assert next(d for d in result["domains"] if d["domain"] == "network_config")["eligible"] is False


def test_all_domains_require_compatible_scope_before_complete(client, reviewer):
    for domain in Domain:
        record = make_draft(client, reviewer, domain.value)
        assert approve(client, reviewer, record, domain.value).status_code == 200
    result = client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()
    assert result["qualified_domain_count"] == 7 and result["assessment_status"] == "complete"


def test_shared_reference_and_unpublished_documents_cannot_qualify(client, reviewer, db_session):
    version = db_session.get(KnowledgeVersion, reviewer[3])
    document = db_session.get(KnowledgeDocument, version.document_id)
    document.org_id = None
    db_session.commit()
    assert client.get(reviewer[2] + f"/source-documents/{version.id}", headers=reviewer[0]).status_code == 404
    document.org_id = uuid.UUID(reviewer[1])
    version.current = False
    db_session.commit()
    assert client.get(reviewer[2] + f"/source-documents/{version.id}", headers=reviewer[0]).status_code == 404


def test_material_conflict_requires_two_references(client, reviewer):
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record, decision="conflicting").status_code == 422


def test_two_source_conflict_is_unscored_and_can_be_revoked(client, reviewer, db_session):
    doc = KnowledgeDocument(org_id=uuid.UUID(reviewer[1]), title="Contradictory operational observation")
    db_session.add(doc)
    db_session.flush()
    content = "Synthetic contradictory observation on the same inventory."
    version = KnowledgeVersion(document_id=doc.id, number=1, edition="test", source="synthetic",
        content_kind="organization_policy", rights="synthetic", content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(), current=True)
    db_session.add(version)
    db_session.commit()
    record = make_draft(client, reviewer)
    second = client.get(reviewer[2] + f"/source-documents/{version.id}", headers=reviewer[0]).json()
    observations = record["observations"] + [{**record["observations"][0], "source_id": second["source_id"], "source_sha256": second["source_sha256"]}]
    record = client.put(reviewer[2] + "/qualifications/network_config", headers=reviewer[0], json={
        "expected_version": 1, "scope": record["scope"], "rationale": "Material contradiction in two operational sources",
        "inventory_sha256": record["inventory_sha256"], "observations": observations}).json()
    response = approve(client, reviewer, record, decision="conflicting", note="Same-scope observations materially contradict one another")
    assert response.status_code == 200, response.text
    result = client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()
    domain = next(d for d in result["domains"] if d["domain"] == "network_config")
    assert domain["evidence_status"] == "conflicting" and domain["eligible"] is False
    assert client.post(reviewer[2] + "/qualifications/network_config/revoke", headers=reviewer[0],
        json={"expected_version": response.json()["version"], "note": "Revoke pending reconciliation"}).status_code == 200


def test_lifecycle_history_prevents_approval_resurrection(client, reviewer, db_session):
    from app.services.events import record_event
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    # Same final content/IDs, but retired then reactivated in the meantime.
    record_event(db_session, "document_retired", org_id=uuid.UUID(reviewer[1]), item=str(reviewer[3]))
    record_event(db_session, "document_reactivation_queued", org_id=uuid.UUID(reviewer[1]), item=str(reviewer[3]))
    db_session.commit()
    result = client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()
    assert result["qualified_domain_count"] == 0
    assert next(d for d in result["domains"] if d["domain"] == "network_config")["reason_code"] == "inventory_changed"


def test_evaluation_uses_one_database_snapshot(client, reviewer, db_session, monkeypatch):
    from app.services import dashboard_evidence
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    original = dashboard_evidence.inventory_scope

    def change_after_scope(snapshot, org):
        scope = original(snapshot, org)
        version = db_session.get(KnowledgeVersion, reviewer[3])
        version.content = "Changed after the read snapshot was established"
        version.content_hash = hashlib.sha256(version.content.encode()).hexdigest()
        db_session.commit()
        return scope

    monkeypatch.setattr(dashboard_evidence, "inventory_scope", change_after_scope)
    assert client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()["qualified_domain_count"] == 1
    monkeypatch.setattr(dashboard_evidence, "inventory_scope", original)
    assert client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()["qualified_domain_count"] == 0


def test_different_scope_labels_prevent_complete_overall(client, reviewer):
    for index, domain in enumerate(Domain):
        record = make_draft(client, reviewer, domain.value, scope="Different declared scope" if index == 0 else "Common scope")
        assert approve(client, reviewer, record, domain.value).status_code == 200
    result = client.get(reviewer[2] + "/evaluation", headers=reviewer[0]).json()
    assert result["qualified_domain_count"] == 7
    assert result["assessment_status"] == "partial" and result["overall_reason"] == "scope_mismatch"


def test_empty_inventory_cannot_be_qualified_by_a_document_alone(client, reviewer, db_session):
    db_session.query(Asset).filter_by(org_id=uuid.UUID(reviewer[1])).delete()
    db_session.commit()
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 409


@pytest.mark.parametrize("kind", ["standard", "guideline"])
def test_reference_content_kind_cannot_qualify_operations(client, reviewer, db_session, kind):
    db_session.get(KnowledgeVersion, reviewer[3]).content_kind = kind
    db_session.commit()
    assert client.get(reviewer[2] + f"/source-documents/{reviewer[3]}", headers=reviewer[0]).status_code == 404


@pytest.mark.parametrize("operation", ["review", "revoke"])
def test_concurrent_review_writes_have_one_winner(client, reviewer, db_session, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException, Response
    from sqlalchemy.orm import sessionmaker
    from app.api.deps import authorize_org_write
    from app.api.routes.scoring_qualifications import review, revoke
    from app.models.enums import UserRole
    from app.models.user import User
    from app.schemas.scoring_qualification import QualificationReview, QualificationRevocation

    record = make_draft(client, reviewer)
    if operation == "revoke":
        record = approve(client, reviewer, record).json()
    expected = record["version"]
    actor_id = db_session.query(User).filter_by(email="live-reviewer@example.io").one().id
    sessions = sessionmaker(bind=db_session.get_bind())
    barrier = Barrier(2)

    def submit(_):
        with sessions() as session:
            barrier.wait(timeout=10)
            admin = authorize_org_write(session, uuid.UUID(reviewer[1]), actor_id, (UserRole.admin,))
            try:
                payload = QualificationReview(**review_payload(record)) if operation == "review" else QualificationRevocation(expected_version=expected, note="Concurrent revoke")
                action = review if operation == "review" else revoke
                result = action(uuid.UUID(reviewer[1]), Domain.network_config, payload, Response(), session, admin)
                return result.version
            except HTTPException as exc:
                session.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [expected + 1, 409]


def test_database_expiry_limit_is_elapsed_time_across_dst(client, reviewer, db_session):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    record = make_draft(client, reviewer)
    row = db_session.get(DomainEvidenceQualification, uuid.UUID(record["id"]))
    db_session.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
    row.reviewed_at = datetime(2027, 3, 1, tzinfo=timezone.utc)
    row.expires_at = row.reviewed_at + timedelta(days=90)
    db_session.commit()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            row.expires_at = row.expires_at + timedelta(seconds=1)
            db_session.flush()


def test_document_review_locks_parent_before_version(client, reviewer, db_session):
    from sqlalchemy import event
    record = make_draft(client, reviewer)
    statements = []
    engine = db_session.get_bind()

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FOR SHARE" in statement and "knowledge_" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert approve(client, reviewer, record).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) == 2
    assert "FROM knowledge_documents" in statements[0]
    assert "FROM knowledge_versions" in statements[1]
