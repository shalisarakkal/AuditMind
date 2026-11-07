"""Status assertions alone never authorize a risk exclusion."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from app.models.finding import Finding
from app.services import status_scoring
from app.services.scoring_service import count_org_findings
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member

pytestmark = requires_db


@pytest.fixture
def prepared(client):
    headers = register(client, "status-policy@example.com")
    org = first_org_id(client, headers)
    base = f"/api/v1/orgs/{org}"
    result = client.post(base + "/findings", headers=headers,
        json=dict(domain="network_config", severity="high", description="Status policy fixture"))
    assert result.status_code == 201, result.text
    return headers, org, base, result.json()["id"]


def approve(client, prepared, status="resolved"):
    headers, org, base, identifier = prepared
    response = client.patch(f"{base}/findings/{identifier}/workflow", headers=headers,
        json=dict(expected_version=0, status=status, rationale="Reviewed", verification="Old note"))
    assert response.status_code == 200, response.text
    endpoint = f"{base}/findings/{identifier}/risk-verification"
    instant = datetime.now(timezone.utc)
    response = client.post(endpoint, headers=headers, json=dict(expected_version=0,
        expected_workflow_version=1, source_reference="https://evidence.example/closure/1",
        observed_at=(instant-timedelta(hours=1)).isoformat(), note="Retest evidence"))
    assert response.status_code == 200, response.text
    payload = dict(expected_version=1, expected_workflow_version=1, decision="approved",
        expires_at=(instant+timedelta(days=7)).isoformat(), note="Reviewed retest",
        evidence_reviewed=True, self_review_acknowledged=True)
    response = client.post(endpoint + "/review", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return endpoint, payload, response.json()


def test_inherit_and_explicit_override(client, prepared):
    headers, _, base, _ = prepared
    endpoint = base + "/status-scoring"
    value = client.get(endpoint, headers=headers).json()
    assert value["enabled"] is True and value["enabled_override"] is None
    response = client.patch(endpoint, headers=headers, json=dict(expected_version=0, enabled_override=False))
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert client.patch(endpoint, headers=headers, json=dict(expected_version=0, enabled_override=True)).status_code == 409
    assert client.patch(endpoint, headers=headers, json=dict(expected_version=1, enabled_override=None)).json()["enabled"] is True


def test_platform_default_updates_inherited_organizations_only(client, db_session, prepared):
    from sqlalchemy import select
    from app.models.user import User
    headers, _, base, _ = prepared
    path = "/api/v1/platform/status-scoring"
    assert client.get(path, headers=headers).status_code == 403
    user = db_session.scalar(select(User).where(User.email == "status-policy@example.com"))
    user.is_sysadmin = True
    db_session.commit()
    response = client.patch(path, headers=headers, json=dict(expected_version=0, enabled=False))
    assert response.status_code == 200, response.text
    assert client.get(base+"/status-scoring", headers=headers).json()["enabled"] is False
    response = client.patch(base+"/status-scoring", headers=headers, json=dict(expected_version=0, enabled_override=True))
    assert response.json()["enabled"] is True
    assert client.patch(path, headers=headers, json=dict(expected_version=0, enabled=True)).status_code == 409
    assert client.patch(path, headers=headers, json=dict(expected_version=1, enabled=True)).status_code == 200
    assert client.get(base+"/status-scoring", headers=headers).json()["enabled_override"] is True


@pytest.mark.parametrize("status,excluded", [("resolved", True), ("false_positive", True), ("mitigated", False)])
def test_admin_review_changes_risk_only(client, db_session, prepared, status, excluded):
    endpoint, payload, result = approve(client, prepared, status)
    headers, org, base, identifier = prepared
    assert result["eligible_for_exclusion"] is excluded
    raw = count_org_findings(db_session, org)
    _, policy = status_scoring.apply_policy(db_session, UUID(org), raw, capture_basis=True)
    assert policy["recorded_findings"] == 1
    assert policy["excluded_findings"] == int(excluded)
    assert len(policy["verification_basis"]) == int(excluded)
    if excluded:
        assert policy["verification_basis"][0]["finding_id"] == identifier
        assert policy["verification_basis"][0]["decision_id"]
    assert client.post(endpoint+"/review", headers=headers, json=payload).status_code == 409
    dashboard = client.get(base+"/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    if excluded:
        assert dashboard.json()["overall_score"] is None
        assert dashboard.json()["findings_baseline"]["overall_score"] is None
        assert dashboard.json()["status_scoring"]["excluded_findings"] == 1
    finding = db_session.get(Finding, UUID(identifier), populate_existing=True)
    finding.risk_verification_expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    db_session.commit()
    assert client.get(endpoint, headers=headers).json()["eligible_for_exclusion"] is False


def test_notes_are_not_approval(client, prepared):
    headers, _, base, identifier = prepared
    response = client.patch(f"{base}/findings/{identifier}/workflow", headers=headers,
        json=dict(expected_version=0, status="resolved", rationale="Reviewed", verification="Free text"))
    assert response.status_code == 200
    dashboard = client.get(base+"/dashboard", headers=headers).json()
    assert dashboard["status_scoring"]["excluded_findings"] == 0


def test_roles_and_tenant_isolation(client, prepared):
    headers, org, base, identifier = prepared
    endpoint, payload, _ = approve(client, prepared)
    auditor = member(client, headers, org, "auditor")
    viewer = member(client, headers, org, "viewer")
    for role_headers in (auditor, viewer):
        assert client.post(endpoint+"/review", headers=role_headers, json=payload).status_code == 403
        assert client.patch(base+"/status-scoring", headers=role_headers,
            json=dict(expected_version=0, enabled_override=False)).status_code == 403
    other = register(client, "other-policy@example.com")
    assert client.get(endpoint, headers=other).status_code == 403


def test_nonstatus_edit_preserves_but_reopening_invalidates(client, prepared):
    headers, _, base, identifier = prepared
    endpoint, _, _ = approve(client, prepared)
    workflow = f"{base}/findings/{identifier}/workflow"
    response = client.patch(workflow, headers=headers, json=dict(expected_version=1, rationale="Assignment review"))
    assert response.status_code == 200
    assert client.get(endpoint, headers=headers).json()["eligible_for_exclusion"]
    for version, status in ((2, "open"), (3, "resolved")):
        response = client.patch(workflow, headers=headers,
            json=dict(expected_version=version, status=status, rationale="Status changed", verification="New review"))
        assert response.status_code == 200, response.text
    assert client.get(endpoint, headers=headers).json()["eligible_for_exclusion"] is False


def test_later_source_observation_invalidates_old_approval(client, db_session, prepared):
    from uuid import uuid4
    from app.models.finding_observation import FindingObservation
    headers, org, _, identifier = prepared
    endpoint, _, _ = approve(client, prepared)
    db_session.add(FindingObservation(id=uuid4(), org_id=UUID(org), finding_id=UUID(identifier),
        import_id=uuid4(), scan_id=None, occurrence=1, source_row=1, source="manual",
        scan_type="findings", recorded_at=datetime.now(timezone.utc)-timedelta(days=1),
        asset_identity={}, source_identity={}, reconciliation_eligible=False,
        ineligibility_reasons=[], payload={}))
    db_session.commit()
    assert client.get(endpoint, headers=headers).json()["eligible_for_exclusion"] is False


def test_approval_requires_attestation_and_revoke_restores_risk(client, prepared):
    headers, _, base, _ = prepared
    endpoint, payload, _ = approve(client, prepared)
    response = client.post(endpoint+"/review", headers=headers, json={**payload,
        "expected_version": 2, "decision": "revoked", "note": "Evidence withdrawn"})
    assert response.status_code == 200, response.text
    assert not response.json()["eligible_for_exclusion"]
    assert client.get(base+"/dashboard", headers=headers).json()["status_scoring"]["current_risk_findings"] == 1


def test_numeric_assessment_refuses_fabricated_perfect_score(client, prepared):
    headers, _, base, _ = prepared
    approve(client, prepared)
    result = client.post(base+"/risk/score", headers=headers)
    assert result.status_code == 409, result.text


def test_explicit_review_and_self_review_acknowledgment_required(client, prepared):
    headers, _, _, _ = prepared
    endpoint, payload, _ = approve(client, prepared)
    instant = datetime.now(timezone.utc)
    submission = dict(expected_version=2, expected_workflow_version=1,
        source_reference="https://evidence.example/current", observed_at=instant.isoformat(), note="Replacement")
    assert client.post(endpoint, headers=headers, json=submission).status_code == 200
    current = {**payload, "expected_version": 3}
    for missing in ("evidence_reviewed", "self_review_acknowledged"):
        response = client.post(endpoint+"/review", headers=headers, json={**current, missing: False})
        assert response.status_code == 422, response.text
    assert client.post(endpoint+"/review", headers=headers, json=current).status_code == 200


def test_saved_dashboard_rechecks_policy_and_proof(client, db_session, prepared):
    from app.models.session import PlatformSetting
    from app.services import dashboard_snapshots
    from app.worker import runner
    headers, org, base, _ = prepared
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY,
        value={"enabled": True, "refresh_interval_seconds": 3600, "version": 1}))
    db_session.commit()
    assert client.get(base+"/dashboard", headers=headers).status_code == 202
    assert runner.run_once(db_session)
    endpoint, payload, _ = approve(client, prepared)
    value = client.get(base+"/dashboard", headers=headers).json()
    assert value["status_scoring"]["excluded_findings"] == 1
    assert value["risk_top_stale"]
    assert runner.run_once(db_session)
    value = client.get(base+"/dashboard", headers=headers).json()
    assert not value["risk_top_stale"] and value["overall_score"] is None
    assert client.patch(base+"/status-scoring", headers=headers,
        json=dict(expected_version=0, enabled_override=False)).status_code == 200
    value = client.get(base+"/dashboard", headers=headers).json()
    assert value["status_scoring"]["excluded_findings"] == 0
    assert value["overall_score"] is not None


def test_document_source_retirement_invalidates_approval(client, db_session, prepared):
    from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
    headers, org, base, identifier = prepared
    endpoint, payload, _ = approve(client, prepared)
    document = KnowledgeDocument(org_id=UUID(org), title="Retest")
    db_session.add(document); db_session.flush()
    version = KnowledgeVersion(document_id=document.id, number=1, edition="1", source="test",
        content_kind="policy", rights="test", content="Synthetic", content_hash="a"*64, current=True)
    db_session.add(version); db_session.commit()
    response = client.post(endpoint, headers=headers, json=dict(expected_version=2, expected_workflow_version=1,
        source_reference=f"document:{version.id}", observed_at=datetime.now(timezone.utc).isoformat(), note="Document retest"))
    assert response.status_code == 200, response.text
    assert client.post(endpoint+"/review", headers=headers, json={**payload,"expected_version":3}).json()["eligible_for_exclusion"]
    version.retired_at = datetime.now(timezone.utc)
    db_session.commit()
    assert not client.get(endpoint, headers=headers).json()["eligible_for_exclusion"]


def test_evidence_submission_does_not_wait_for_import_fk_or_source_revision(client, db_session, prepared):
    from uuid import uuid4
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app.models.finding_observation import FindingObservation
    headers, org, base, identifier = prepared
    response = client.patch(f"{base}/findings/{identifier}/workflow", headers=headers,
        json=dict(expected_version=0, status="resolved", rationale="Retest", verification="Retest"))
    assert response.status_code == 200
    endpoint = f"{base}/findings/{identifier}/risk-verification"
    with Session(db_session.get_bind()) as importing:
        importing.add(FindingObservation(id=uuid4(), org_id=UUID(org), finding_id=UUID(identifier),
            import_id=uuid4(), scan_id=None, occurrence=1, source_row=1, source="manual", scan_type="findings",
            recorded_at=datetime.now(timezone.utc)-timedelta(days=1), asset_identity={}, source_identity={},
            reconciliation_eligible=False, ineligibility_reasons=[], payload={}))
        importing.flush()  # Holds a finding FK KEY SHARE until publication.
        importing.execute(text("UPDATE organization_list_revisions SET finding_revision=finding_revision+1 WHERE org_id=:org"), {"org":org})
        db_session.execute(text("SET LOCAL statement_timeout='1500ms'"))
        response = client.post(endpoint, headers=headers, json=dict(expected_version=0, expected_workflow_version=1,
            source_reference="https://evidence.example/concurrent", observed_at=datetime.now(timezone.utc).isoformat(), note="During import"))
        assert response.status_code == 200, response.text
        importing.commit()
    response = client.post(endpoint+"/review", headers=headers, json=dict(expected_version=1, expected_workflow_version=1,
        decision="approved", expires_at=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),
        note="Must detect late publication", evidence_reviewed=True, self_review_acknowledged=True))
    assert response.status_code == 409, response.text
