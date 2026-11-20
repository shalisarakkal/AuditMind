"""Real PostgreSQL proof review: authority, retention, stale context and scoring separation."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from app.models.finding import Finding
from app.models.remediation_proof import RemediationProof
from app.models.event import Event
from app.models.membership import OrgMembership
from app.models.enums import UserRole
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member
from tests.integration.test_finding_consolidation_foundation import native

pytestmark = requires_db


@pytest.fixture
def proof(client):
    h = register(client, "proof@example.com")
    org = first_org_id(client, h)
    base = f"/api/v1/orgs/{org}/findings"
    response = client.post(base, headers=h, json=dict(domain="network_config", severity="high", description="Synthetic proof finding"))
    assert response.status_code == 201, response.text
    finding = response.json()["id"]
    return h, org, f"{base}/{finding}", f"{base}/{finding}/remediation-proof", finding


def submit(client, h, url, **fields):
    return client.post(url, headers=h, json=dict(expected_version=0, expected_workflow_version=0,
        source_reference="https://example.com/synthetic-retest", observed_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        note="Synthetic retest evidence", **fields))


def review(client, h, url, **fields):
    payload = dict(expected_version=1, expected_workflow_version=0, decision="approved",
        evidence_reviewed=True, self_review_acknowledged=True, note="Reviewed synthetic proof")
    payload.update(fields)
    return client.post(url + "/review", headers=h, json=payload)


def test_submit_review_retained_without_workflow_or_scoring_authority(client, db_session, proof):
    h, org, base, url, finding = proof
    initial = client.get(url, headers=h)
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json()["state"] == "not_submitted"
    data = submit(client, h, url)
    assert data.status_code == 200, data.text
    assert data.json()["state"] == "pending"
    assert data.json()["can_review"]
    approved = review(client, h, url)
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    assert not approved.json()["can_review"]
    assert [r["state"] for r in approved.json()["records"]] == ["approved", "pending"]
    assert approved.json()["records"][0]["source_reference"].startswith("https:")
    assert client.get(base + "/workflow", headers=h).json()["status"] == "open"
    risk = client.get(base + "/risk-verification", headers=h).json()
    assert risk["version"] == 0 and not risk["eligible_for_exclusion"]
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.org_id == UUID(org), Event.type == "remediation_proof_changed")) == 2
    assert review(client, h, url, expected_version=2).status_code == 409


def test_reject_reason_and_replacement_preserve_open_history(client, proof):
    h, _, base, url, _ = proof
    assert submit(client, h, url).status_code == 200
    rejected = review(client, h, url, decision="rejected", note="Retest still fails; patch the service and retest")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["state"] == "rejected"
    assert "patch the service" in rejected.json()["records"][0]["note"]
    assert client.get(base + "/workflow", headers=h).json()["status"] == "open"
    payload = dict(expected_version=2, expected_workflow_version=0, source_reference="https://example.com/new-retest",
        observed_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), note="New retest")
    replaced = client.post(url, headers=h, json=payload)
    assert replaced.status_code == 200, replaced.text
    assert [r["state"] for r in replaced.json()["records"]] == ["pending", "rejected", "pending"]
    page = client.get(url + "?limit=1", headers=h).json()
    assert page["next_before"] == 3
    older = client.get(url + "?limit=1&before=3", headers=h).json()
    assert older["records"][0]["state"] == "rejected" and older["version"] == 3


@pytest.mark.parametrize("role", ["viewer", "auditor"])
def test_roles_and_tenant_isolation(client, proof, role):
    h, org, _, url, _ = proof
    other = member(client, h, org, role)
    outsider = register(client, "outsider@example.com")
    assert client.get(url, headers=outsider).status_code == 403
    assert submit(client, outsider, url).status_code == 403
    assert client.get(url, headers=other).status_code == 200
    result = submit(client, other, url)
    assert result.status_code == (200 if role == "auditor" else 403)
    if role == "viewer":
        assert submit(client, h, url).status_code == 200
    assert review(client, other, url).status_code == 403
    assert review(client, h, url).status_code == 200


@pytest.mark.parametrize("ack", ["evidence_reviewed", "self_review_acknowledged"])
def test_acknowledgments_required_for_approval_and_rejection(client, proof, ack):
    h, _, _, url, _ = proof
    assert submit(client, h, url).status_code == 200
    assert review(client, h, url, **{ack: False}).status_code == 422
    assert review(client, h, url, decision="rejected", **{ack: False}).status_code == 422
    assert client.get(url, headers=h).json()["version"] == 1


@pytest.mark.parametrize("reference", ["http://example.com", "https://user:secret@example.com", "javascript:alert(1)", "document:nope", "document:" + str(uuid4())])
def test_invalid_or_unavailable_reference_rejected(client, proof, reference):
    h, _, _, url, _ = proof
    payload = dict(expected_version=0, expected_workflow_version=0, source_reference=reference,
        observed_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), note="Synthetic")
    assert client.post(url, headers=h, json=payload).status_code == 422
    assert client.get(url, headers=h).json()["version"] == 0


@pytest.mark.parametrize("age", [-1, 91])
def test_observation_age_bounds(client, proof, age):
    h, _, _, url, _ = proof
    payload = dict(expected_version=0, expected_workflow_version=0, source_reference="https://example.com/proof",
        observed_at=(datetime.now(timezone.utc) - timedelta(days=age)).isoformat(), note="Synthetic")
    assert client.post(url, headers=h, json=payload).status_code == 422


def test_stale_workflow_blocks_review_and_preserves_proof(client, proof):
    h, _, base, url, _ = proof
    assert submit(client, h, url).status_code == 200
    assert client.patch(base + "/workflow", headers=h, json=dict(expected_version=0, rationale="Changed assignment context")).status_code == 200
    state = client.get(url, headers=h).json()
    assert state["state"] == "stale" and not state["can_review"]
    assert review(client, h, url).status_code == 409
    assert review(client, h, url, expected_workflow_version=1).status_code == 409
    assert len(client.get(url, headers=h).json()["records"]) == 1


def test_stale_version_and_closed_workflow_do_not_write(client, proof):
    h, _, base, url, _ = proof
    assert submit(client, h, url).status_code == 200
    assert submit(client, h, url).status_code == 409
    assert client.patch(base + "/workflow", headers=h, json=dict(expected_version=0, status="resolved", rationale="Legacy closure", verification="User assertion")).status_code == 200
    data = client.get(url, headers=h).json()
    assert data["state"] == "stale" and not data["can_submit"]
    assert review(client, h, url, expected_workflow_version=1).status_code == 409


def test_database_immutability_owner_and_purge(client, db_session, proof):
    h, org, _, url, finding = proof
    assert submit(client, h, url).status_code == 200
    row = db_session.scalar(select(RemediationProof))
    for statement in (update(RemediationProof).values(note="Rewrite"), delete(RemediationProof)):
        with pytest.raises(IntegrityError, match="immutable"):
            db_session.execute(statement)
            db_session.commit()
        db_session.rollback()
    # Ownership enforced below the API as well as by tenant-scoped reads.
    with pytest.raises(IntegrityError, match="same-organization"):
        db_session.execute(text("INSERT INTO remediation_proofs SELECT gen_random_uuid(),:org,finding_id,version+1,workflow_version,state,source_reference,source_sha256,observed_at,submitter_id,submitter_label,actor_id,actor_label,note,created_at,context FROM remediation_proofs"), {"org": uuid4()})
        db_session.commit()
    db_session.rollback()
    assert db_session.get(RemediationProof, row.id) is not None
    db_session.execute(delete(Finding).where(Finding.id == UUID(finding)))
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(RemediationProof)) == 0


def test_role_rechecked_on_write(client, db_session, proof):
    h, org, _, url, _ = proof
    assert submit(client, h, url).status_code == 200
    membership = db_session.scalar(select(OrgMembership).where(OrgMembership.org_id == UUID(org)))
    membership.role = UserRole.viewer
    db_session.commit()
    assert review(client, h, url).status_code == 403


def test_document_version_tenant_and_retirement(client, db_session, proof):
    from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
    h, org, _, url, _ = proof
    document = KnowledgeDocument(org_id=UUID(org), title="Synthetic remediation proof")
    db_session.add(document)
    db_session.flush()
    version = KnowledgeVersion(document_id=document.id, number=1, edition="test", source="synthetic",
        content_kind="text", rights="Synthetic fixture", content="Synthetic retest", content_hash="a" * 64, current=True)
    db_session.add(version)
    db_session.commit()
    payload = dict(expected_version=0, expected_workflow_version=0, source_reference=f"document:{version.id}",
        observed_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), note="Current same-organization document")
    response = client.post(url, headers=h, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["records"][0]["source_sha256"] == "a" * 64
    version.retired_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.get(url, headers=h).json()["state"] == "stale"
    assert review(client, h, url).status_code == 409
    # Another organization's version cannot be substituted for this proof.
    outsider = register(client, "proof-document-outsider@example.com")
    document.org_id = UUID(first_org_id(client, outsider))
    version.retired_at = None
    db_session.commit()
    payload["expected_version"] = 1
    assert client.post(url, headers=h, json=payload).status_code == 422


def test_new_observation_invalidates_pending_proof(client, db_session, proof):
    from app.models.finding_observation import FindingObservation
    h, org, _, url, finding = proof
    assert submit(client, h, url).status_code == 200
    db_session.add(FindingObservation(id=uuid4(), org_id=UUID(org), finding_id=UUID(finding), import_id=uuid4(),
        occurrence=1, source_row=1, source="synthetic", scan_type="synthetic", recorded_at=datetime.now(timezone.utc),
        asset_identity={}, source_identity={}, reconciliation_eligible=False, ineligibility_reasons=["synthetic"], payload={}))
    db_session.commit()
    assert client.get(url, headers=h).json()["state"] == "stale"
    assert review(client, h, url).status_code == 409


def test_archive_fence_and_retained_history_on_restore(client, db_session, proof):
    from app.models.enums import ArchiveItemType
    from app.services.archive_service import start_archive
    from app.models.user import User
    h, org, _, url, finding = proof
    assert submit(client, h, url).status_code == 200
    actor = db_session.scalar(select(User).where(User.email == "proof@example.com"))
    start_archive(db_session, UUID(org), ArchiveItemType.finding, UUID(finding), actor.id)
    assert review(client, h, url).status_code == 409
    # Archived records have no new proof actions, but retained history survives.
    item = db_session.get(Finding, UUID(finding))
    item.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.get(url, headers=h).status_code == 404
    assert db_session.scalar(select(func.count()).select_from(RemediationProof)) == 1
    item.archived_at = None
    db_session.commit()
    assert len(client.get(url, headers=h).json()["records"]) == 1


def test_inventory_busy_refuses_without_waiting_or_writing(client, db_session, proof):
    from app.services.org_lock import lock_org
    h, org, _, url, _ = proof
    with db_session.get_bind().connect() as other:
        lock_org(other, UUID(org))
        response = submit(client, h, url)
        assert response.status_code == 409, response.text
        assert "Inventory is changing" in response.text
    assert db_session.scalar(select(func.count()).select_from(RemediationProof)) == 0


def test_activity_receipt_failure_rolls_back_proof(client, db_session, proof, monkeypatch):
    from fastapi import HTTPException
    from app.services import remediation_proof
    h, _, _, url, _ = proof
    def failed_receipt(*args, **kwargs):
        raise HTTPException(503, "Synthetic receipt failure")
    monkeypatch.setattr(remediation_proof, "record_event", failed_receipt)
    assert submit(client, h, url).status_code == 503
    db_session.rollback()  # Production dependency closes/rolls back the failed request.
    assert db_session.scalar(select(func.count()).select_from(RemediationProof)) == 0
    assert client.get(url, headers=h).json()["version"] == 0


def test_locked_reviewer_returns_conflict_without_partial_write(client, db_session, proof):
    from app.models.user import User
    h, _, _, url, _ = proof
    actor_id = db_session.scalar(select(User.id).where(User.email == "proof@example.com"))
    db_session.rollback()
    with db_session.get_bind().connect() as other:
        other.execute(select(User.id).where(User.id == actor_id).with_for_update())
        response = submit(client, h, url)
        assert response.status_code == 409, response.text
    assert db_session.scalar(select(func.count()).select_from(RemediationProof)) == 0


def test_readiness_requires_local_enabled_guard(client, db_session, proof):
    h, _, _, url, _ = proof
    db_session.execute(text("ALTER TABLE remediation_proofs DISABLE TRIGGER am_remediation_proof_guard"))
    db_session.commit()
    assert client.get(url, headers=h).status_code == 503
    assert submit(client, h, url).status_code == 503


def test_alias_proof_fences_even_prepared_consolidation(client, native):
    from tests.integration.test_consolidation_publication import enable, request
    n = native
    enable(client, n)
    prepared = request(client, n)
    url = n["base"] + f'/findings/{n["target"].finding_id}/remediation-proof'
    assert submit(client, n["headers"], url).status_code == 200
    preview = client.post(n["root"] + "/publication-preview", headers=n["headers"], json=dict(canonical_decision_id=n["decision"]))
    assert preview.status_code == 409, preview.text
    assert any(b["code"] == "alias_not_pristine" for b in preview.json()["detail"]["blockers"])
    assert client.post(n["root"] + "/apply", headers=n["headers"], json=prepared).status_code == 409


def test_canonical_proof_does_not_reactivate_after_group_undo(client, native):
    from tests.integration.test_consolidation_publication import publish, undo_request
    n = native
    url = n["base"] + f'/findings/{n["source"].finding_id}/remediation-proof'
    assert submit(client, n["headers"], url).status_code == 200
    _, applied = publish(client, n)
    state = client.get(url, headers=n["headers"]).json()
    assert state["state"] == "stale" and not state["can_submit"]
    assert review(client, n["headers"], url).status_code == 409
    endpoint, payload = undo_request(client, n, applied)
    assert client.post(endpoint + "/undo", headers=n["headers"], json=payload).status_code == 200
    state = client.get(url, headers=n["headers"]).json()
    assert state["state"] == "stale" and not state["can_review"]
