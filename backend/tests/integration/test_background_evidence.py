"""Real PostgreSQL jobs and statement-trigger invalidation; no inference."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.models.asset import Asset
from app.models.evidence_evaluation import EvidenceEvaluation
from app.services import evidence_jobs
from app.worker.runner import run_once
from tests.conftest import requires_db
from tests.helpers import register, first_org_id
from tests.integration.test_scoring_qualification_reviews import reviewer, make_draft, approve  # noqa: F401

pytestmark = requires_db


@pytest.fixture
def owner(client, db_session):
    headers = register(client, "background-evidence@example.io")
    org = first_org_id(client, headers)
    return headers, org, f"/api/v1/orgs/{org}/scoring"


def test_bulk_invalidation_is_transactional_and_per_statement(client, owner, db_session):
    _, org, _ = owner
    org_id = uuid.UUID(org)
    before = evidence_jobs.revision(db_session, org_id)
    db_session.execute(text("""INSERT INTO assets (id,org_id,type,details,created_at)
        SELECT md5(n::text)::uuid,:org,'server','{}',now() FROM generate_series(1,100) n"""), {"org": org_id})
    assert evidence_jobs.revision(db_session, org_id) == before + 1
    db_session.rollback()
    assert evidence_jobs.revision(db_session, org_id) == before
    db_session.execute(text("UPDATE assets SET hostname='none' WHERE false"))
    assert evidence_jobs.revision(db_session, org_id) == before


def test_queue_deduplication_worker_result_and_invalidation(client, owner, db_session):
    headers, org, path = owner
    assert client.get(path + "/evaluations/current", headers=headers).json() is None
    first = client.post(path + "/evaluations", headers=headers)
    assert first.status_code == 202, first.text
    second = client.post(path + "/evaluations", headers=headers)
    assert second.json()["id"] == first.json()["id"]
    assert run_once(db_session)
    db_session.expire_all()
    result = client.get(path + "/evaluations/current", headers=headers).json()
    assert result["status"] == "completed", result
    assert result["is_current"] is True
    assert result["result"]["qualified_domain_count"] == 0
    assert result["progress"]["processed"] == result["progress"]["total"]
    db_session.add(Asset(org_id=uuid.UUID(org), type="server", hostname="new"))
    db_session.commit()
    result = client.get(path + "/evaluations/current", headers=headers).json()
    assert result["is_current"] is False and result["result"] is None


def test_pending_cancellation_never_publishes_a_result(client, owner, db_session):
    headers, org, path = owner
    job = client.post(path + "/evaluations", headers=headers).json()
    cancelled = client.post(path + f"/evaluations/{job['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["result"] is None
    assert not run_once(db_session)


def test_final_short_lifecycle_batch_is_not_throttled(client, owner, db_session, monkeypatch):
    from types import SimpleNamespace
    from app.services.events import record_event
    headers, org, path = owner
    for _ in range(44):
        record_event(db_session, "restore", org_id=uuid.UUID(org))
    db_session.commit()
    # Freeze only this service's clock reference, not the global clock used by
    # the HTTP/DB runtimes, so every within-phase update hits throttling.
    monkeypatch.setattr(evidence_jobs, "time", SimpleNamespace(monotonic=lambda: 10.0))
    job = run_evaluation(client, path, headers, db_session)
    assert job["status"] == "completed"
    assert job["progress"]["processed"] == job["progress"]["total"] == 44


def run_evaluation(client, path, headers, db):
    assert client.post(path + "/evaluations", headers=headers).status_code == 202
    assert run_once(db)
    db.expire_all()
    return client.get(path + "/evaluations/current", headers=headers).json()


def test_setting_gates_partial_scores_without_silent_fallback(client, reviewer, db_session, monkeypatch):
    from app.services import dashboard_evidence
    headers, org, path, _ = reviewer
    record = make_draft(client, reviewer)
    assert approve(client, reviewer, record).status_code == 200
    evaluated = run_evaluation(client, path, headers, db_session)
    assert evaluated["is_current"]
    assert evaluated["result"]["qualified_domain_count"] == 1
    baseline = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    assert baseline["scoring_mode"] == "findings_based" and baseline["overall_score"] == 100
    changed = client.patch(path + "/settings", headers=headers, json={"expected_version": 0, "evidence_qualified_enabled": True})
    assert changed.status_code == 200 and changed.json()["version"] == 1
    def no_scan(*args, **kwargs):
        raise AssertionError("Dashboard must never fingerprint the inventory")
    monkeypatch.setattr(dashboard_evidence, "inventory_scope", no_scan)
    monkeypatch.setattr(dashboard_evidence, "inventory_progress", no_scan)
    partial = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    assert partial["scoring_mode"] == "evidence_qualified"
    assert partial["assessment_status"] == "partial"
    assert partial["overall_score"] is None and partial["overall_tier"] is None
    assert partial["qualified_domain_count"] == 1
    network = next(d for d in partial["domains"] if d["domain"] == "network_config")
    assert network["score"] == 100 and network["evidence_reason"] == "qualified"
    assert network["qualification_scope"] and network["source_references"] and network["expires_at"]
    assert all(d["score"] is None for d in partial["domains"] if d["domain"] != "network_config")
    db_session.execute(text("UPDATE assets SET hostname='changed' WHERE org_id=:org"), {"org": uuid.UUID(org)})
    db_session.commit()
    stale = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    assert stale["qualified_domain_count"] == 0 and stale["overall_score"] is None
    assert all(d["score"] is None for d in stale["domains"])
    assert stale["evaluation_state"] == "not_current"
    assert client.patch(path + "/settings", headers=headers, json={"expected_version": 1, "evidence_qualified_enabled": False}).status_code == 200
    assert client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()["overall_score"] == baseline["overall_score"]


def test_publication_rejects_concurrent_inventory_change(client, reviewer, db_session, monkeypatch):
    from sqlalchemy.orm import Session
    from app.services import dashboard_evidence
    headers, org, path, _ = reviewer
    assert approve(client, reviewer, make_draft(client, reviewer)).status_code == 200
    original = dashboard_evidence.inventory_progress
    def concurrent(snapshot, org_id):
        for event in original(snapshot, org_id):
            if event["type"] == "result":
                with Session(db_session.get_bind()) as writer:
                    writer.add(Asset(org_id=org_id, type="server", hostname="concurrent"))
                    writer.commit()
            yield event
    monkeypatch.setattr(dashboard_evidence, "inventory_progress", concurrent)
    job = run_evaluation(client, path, headers, db_session)
    assert job["status"] == "superseded" and job["result"] is None and not job["is_current"]


def test_expired_or_wrong_policy_cache_cannot_authorize_scores(client, reviewer, db_session):
    headers, org, path, _ = reviewer
    assert approve(client, reviewer, make_draft(client, reviewer)).status_code == 200
    job = run_evaluation(client, path, headers, db_session)
    row = db_session.get(EvidenceEvaluation, uuid.UUID(job["id"]))
    row.valid_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert evidence_jobs.current_result(db_session, uuid.UUID(org)) is None
    row.valid_until, row.policy_identity = None, "0" * 64
    db_session.commit()
    assert evidence_jobs.current_result(db_session, uuid.UUID(org)) is None


def test_viewer_compute_deduplication_permissions_and_foreign_access(client, owner, db_session):
    from tests.helpers import member
    headers, org, path = owner
    viewer = member(client, headers, org, "viewer")
    auditor = member(client, headers, org, "auditor")
    job = client.post(path + "/evaluations", headers=viewer).json()
    assert client.get(path + f"/evaluations/{job['id']}", headers=auditor).status_code == 200
    assert client.post(path + "/evaluations", headers=auditor).json()["id"] == job["id"]
    assert client.post(path + f"/evaluations/{job['id']}/cancel", headers=auditor).status_code == 403
    assert client.post(path + f"/evaluations/{job['id']}/cancel", headers=headers).status_code == 200
    assert client.patch(path + "/settings", headers=viewer, json={"expected_version": 0, "evidence_qualified_enabled": True}).status_code == 403
    other = register(client, "foreign-background@example.io")
    assert client.post(path + "/evaluations", headers=other).status_code == 403
    assert client.get(path + "/evaluations/current", headers=other).status_code == 403
    assert client.get(path + f"/evaluations/{job['id']}", headers=other).status_code == 403
    other_org = first_org_id(client, other)
    assert client.get(f"/api/v1/orgs/{other_org}/scoring/evaluations/{job['id']}", headers=other).status_code == 404


@pytest.mark.parametrize("statement", [
    "UPDATE assets SET hostname='changed' WHERE org_id=:org",
    "DELETE FROM assets WHERE org_id=:org",
    "UPDATE knowledge_versions SET content='changed' WHERE id=:version",
    "UPDATE knowledge_versions SET current=false WHERE id=:version",
    "UPDATE knowledge_versions SET retired_at=now() WHERE id=:version",
    "UPDATE knowledge_versions SET purged_at=now() WHERE id=:version",
    "DELETE FROM knowledge_versions WHERE id=:version",
    "UPDATE knowledge_documents SET title='changed' WHERE org_id=:org",
    "DELETE FROM knowledge_documents WHERE org_id=:org",
    "UPDATE domain_evidence_qualifications SET status='revoked',version=version+1 WHERE org_id=:org",
    "DELETE FROM domain_evidence_qualifications WHERE org_id=:org",
    "UPDATE organizations SET archived_at=now() WHERE id=:org",
    "TRUNCATE assets CASCADE",
])
def test_database_inputs_invalidate_completed_result(client, reviewer, db_session, statement):
    headers, org, path, version = reviewer
    assert approve(client, reviewer, make_draft(client, reviewer)).status_code == 200
    assert run_evaluation(client, path, headers, db_session)["is_current"]
    db_session.execute(text(statement), {"org": uuid.UUID(org), "version": version})
    db_session.commit()
    assert evidence_jobs.current_result(db_session, uuid.UUID(org)) is None


def test_lifecycle_history_and_cascades_invalidate_but_login_does_not(client, reviewer, db_session):
    from app.models.event import Event
    from app.services.events import record_event
    headers, org, path, _ = reviewer
    org_id = uuid.UUID(org)
    assert approve(client, reviewer, make_draft(client, reviewer)).status_code == 200
    assert run_evaluation(client, path, headers, db_session)["is_current"]
    old_revision = evidence_jobs.revision(db_session, org_id)
    record_event(db_session, "login", org_id=org_id)
    db_session.commit()
    assert evidence_jobs.revision(db_session, org_id) == old_revision
    record_event(db_session, "restore", org_id=org_id)
    db_session.commit()
    assert evidence_jobs.current_result(db_session, org_id) is None
    event = db_session.scalar(select(Event).where(Event.org_id == org_id, Event.type == "restore"))
    before = evidence_jobs.revision(db_session, org_id)
    db_session.delete(event); db_session.commit()
    assert evidence_jobs.revision(db_session, org_id) > before
    from app.models.organization import Organization
    db_session.delete(db_session.get(Organization, org_id)); db_session.commit()
    assert db_session.query(EvidenceEvaluation).count() == 0


def test_complete_and_zero_scores_keep_existing_weights(client, reviewer, db_session):
    from app.models.enums import Domain, Severity
    from app.models.finding import Finding
    from app.services.scoring_service import overall_score, score_all_from_counts, count_org_findings
    headers, org, path, _ = reviewer
    db_session.add_all([Finding(org_id=uuid.UUID(org), domain=Domain.network_config, severity=Severity.critical) for _ in range(7)])
    db_session.commit()
    for domain in Domain:
        assert approve(client, reviewer, make_draft(client, reviewer, domain.value), domain.value).status_code == 200
    expected = overall_score(score_all_from_counts(count_org_findings(db_session, uuid.UUID(org))))[0]
    job = run_evaluation(client, path, headers, db_session)
    assert job["result"]["qualified_domain_count"] == 7
    assert client.patch(path + "/settings", headers=headers, json={"expected_version": 0, "evidence_qualified_enabled": True}).status_code == 200
    dashboard = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    assert dashboard["assessment_status"] == "complete"
    assert dashboard["overall_score"] == expected
    assert next(d for d in dashboard["domains"] if d["domain"] == "network_config")["score"] == 0
    assert next(d for d in dashboard["domains"] if d["domain"] == "backup_recovery")["score"] == 100

    # Individually eligible domains cannot establish a combined scope when their
    # declared scope differs. Never silently renormalize the overall score.
    db_session.execute(text("UPDATE domain_evidence_qualifications SET scope='Different scope',version=version+1 WHERE org_id=:org AND domain='network_config'"), {"org": uuid.UUID(org)})
    db_session.commit()
    result = run_evaluation(client, path, headers, db_session)
    assert result["result"]["qualified_domain_count"] == 7
    assert result["result"]["assessment_status"] == "partial"
    dashboard = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    assert dashboard["overall_score"] is None and dashboard["overall_tier"] is None
    assert all(d["score"] is not None for d in dashboard["domains"])


@pytest.mark.parametrize("operation", ["cancel", "failure"])
def test_running_cancel_or_failure_never_publishes_partial_output(client, reviewer, db_session, monkeypatch, operation):
    from app.services import dashboard_evidence
    headers, org, path, _ = reviewer
    original = dashboard_evidence.inventory_progress
    def interrupt(snapshot, org_id):
        for event in original(snapshot, org_id):
            if event["type"] == "progress" and event.get("processed", 0) > 0:
                if operation == "failure":
                    raise RuntimeError("private connection detail must not reach the client")
                from sqlalchemy.orm import Session
                with Session(db_session.get_bind()) as writer:
                    row = writer.scalar(select(EvidenceEvaluation).where(EvidenceEvaluation.org_id == org_id, EvidenceEvaluation.status == "running"))
                    row.cancel_requested_at = datetime.now(timezone.utc); writer.commit()
                # Bypass display throttling by moving to a distinct phase.
                event = {**event, "phase": "cancel-check"}
            yield event
    monkeypatch.setattr(dashboard_evidence, "inventory_progress", interrupt)
    result = run_evaluation(client, path, headers, db_session)
    assert result["status"] == ("cancelled" if operation == "cancel" else "failed")
    assert result["result"] is None and not result["is_current"]
    assert "private connection" not in str(result)


def test_worker_restarts_cut_off_evaluation_and_honors_cancel(client, owner, db_session):
    from app.worker.runner import claim_next, reap_stale
    headers, org, path = owner
    queued = client.post(path + "/evaluations", headers=headers).json()
    assert claim_next(db_session) == ("evidence", uuid.UUID(queued["id"]))
    reap_stale(db_session, now=datetime.now(timezone.utc) + timedelta(days=1))
    row = db_session.get(EvidenceEvaluation, uuid.UUID(queued["id"]), populate_existing=True)
    assert row.status == "pending" and row.retry_count == 1
    assert run_once(db_session)
    db_session.expire_all()
    assert client.get(path + "/evaluations/current", headers=headers).json()["is_current"]


@pytest.mark.parametrize("mutation", ["domain", "aggregate", "date"])
def test_malformed_cache_fails_closed(client, reviewer, db_session, mutation):
    headers, org, path, _ = reviewer
    assert approve(client, reviewer, make_draft(client, reviewer)).status_code == 200
    result = run_evaluation(client, path, headers, db_session)
    row = db_session.get(EvidenceEvaluation, uuid.UUID(result["id"]))
    import copy
    payload = copy.deepcopy(row.result)
    if mutation == "domain": payload["domains"][0]["domain"] = []
    elif mutation == "aggregate": payload["assessment_status"] = "complete"
    else: payload["evaluated_at"] = "invalid"
    row.result = payload; db_session.commit()
    assert evidence_jobs.current_result(db_session, uuid.UUID(org)) is None


def test_non_scoring_workflow_and_branding_changes_keep_current_evaluation(client, owner, db_session):
    from app.models.finding import Finding
    from app.models.enums import Domain, Severity
    headers, org, path = owner
    org_id = uuid.UUID(org)
    db_session.add(Finding(org_id=org_id, domain=Domain.network_config, severity=Severity.low))
    db_session.commit()
    assert run_evaluation(client, path, headers, db_session)["is_current"]
    before = evidence_jobs.revision(db_session, org_id)
    db_session.execute(text("UPDATE findings SET workflow_status='resolved', workflow_version=workflow_version+1 WHERE org_id=:org"), {"org": org_id})
    db_session.execute(text("UPDATE organizations SET name='Renamed', header_name_size='large' WHERE id=:org"), {"org": org_id})
    db_session.commit()
    assert evidence_jobs.revision(db_session, org_id) == before
    assert evidence_jobs.current_result(db_session, org_id) is not None
    db_session.execute(text("UPDATE findings SET id=:id WHERE org_id=:org"), {"id": uuid.uuid4(), "org": org_id})
    db_session.commit()
    assert evidence_jobs.current_result(db_session, org_id) is None
