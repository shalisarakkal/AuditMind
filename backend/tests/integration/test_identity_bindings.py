"""Reviewed namespace boundaries, lifecycle and optimistic decisions."""
from datetime import datetime, timezone
from uuid import UUID
import pytest
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_identity_binding import ObservationIdentityBinding
from app.models.finding_observation import FindingObservation
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member, upload

pytestmark = requires_db


@pytest.fixture
def prepared(client, db_session):
    headers = register(client, "binding-owner@example.io")
    org = first_org_id(client, headers)
    base = f"/api/v1/orgs/{org}"
    result = upload(client, base + "/findings/import", headers, "sample.nessus")
    assert result.status_code == 201, result.text
    obs = db_session.query(FindingObservation).filter(FindingObservation.org_id == UUID(org)).first()
    tool = client.post(base + "/identity-tools", headers=headers,
        json=dict(name="Reviewed Nessus instance", rationale="Configured scanner instance")).json()
    path = f"{base}/findings/{obs.finding_id}/observations/{obs.id}/identity-binding"
    payload = dict(expected_version=0, tool_id=tool["id"], expected_tool_version=1,
        canonical_asset_id=obs.asset_identity["asset_id"], confirm_mapping=True, rationale="Verified canonical host and scanner")
    return headers, org, base, obs.id, path, payload


def test_binding_is_a_candidate_only_and_revoke_is_versioned(client, db_session, prepared):
    h, org, base, obs_id, path, payload = prepared
    finding = db_session.get(Finding, db_session.get(FindingObservation, obs_id).finding_id)
    before = (finding.workflow_status, finding.workflow_version, finding.severity, finding.description, finding.archived_at)
    response = client.put(path, headers=h, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["identity_assessment"]["candidate_key"]
    assert body["identity_binding"]["current"] is True
    assert body["reconciliation_eligible"] is False
    page = client.get(f"{base}/findings/{finding.id}/observations", headers=h).json()
    assert next(x for x in page if x["id"] == str(obs_id))["identity_assessment"]["candidate_key"] == body["identity_assessment"]["candidate_key"]
    assert client.put(path, headers=h, json=payload).status_code == 409
    revoked = client.post(path + "/revoke", headers=h, json=dict(expected_version=1, rationale="Mapping withdrawn"))
    assert revoked.status_code == 200
    assert revoked.json()["identity_assessment"]["candidate_key"] is None
    assert revoked.json()["identity_binding"]["version"] == 2
    assert db_session.query(ObservationIdentityBinding).count() == 2
    db_session.refresh(finding)
    assert before == (finding.workflow_status, finding.workflow_version, finding.severity, finding.description, finding.archived_at)


@pytest.mark.parametrize("change", ["tool", "source", "canonical", "scan", "finding", "purge"])
def test_lifecycle_changes_withhold_candidates(client, db_session, prepared, change):
    h, org, base, obs_id, path, payload = prepared
    original_asset = db_session.get(FindingObservation, obs_id).asset_identity["asset_id"]
    if change == "canonical":
        canonical = Asset(org_id=UUID(org), type="server", hostname="canonical-host")
        db_session.add(canonical); db_session.commit()
        payload = {**payload, "canonical_asset_id": str(canonical.id)}
    bound = client.put(path, headers=h, json=payload)
    assert bound.status_code == 200
    obs = db_session.get(FindingObservation, obs_id)
    if change == "tool":
        retired = client.post(base + f"/identity-tools/{payload['tool_id']}/retire", headers=h,
            json=dict(expected_version=1, rationale="Scanner retired"))
        assert retired.status_code == 200
    elif change == "scan":
        db_session.get(Scan, obs.scan_id).archived_at = datetime.now(timezone.utc)
        db_session.commit()
    elif change == "finding":
        db_session.get(Finding, obs.finding_id).archived_at = datetime.now(timezone.utc)
        db_session.commit()
    elif change == "purge":
        scan_id = obs.scan_id
        db_session.get(Finding, obs.finding_id).scan_id = None
        db_session.flush()
        db_session.delete(db_session.get(Scan, scan_id)); db_session.commit()
    else:
        asset = db_session.get(Asset, UUID(original_asset if change == "source" else payload["canonical_asset_id"]))
        asset.hostname = "changed-identity"
        db_session.commit()
    page = client.get(f"{base}/findings/{obs.finding_id}/observations", headers=h).json()
    entry = next(x for x in page if x["id"] == str(obs_id))
    assert entry["identity_assessment"]["candidate_key"] is None
    assert entry["identity_binding"]["current"] is False


@pytest.mark.parametrize("role", ["auditor", "viewer"])
def test_only_org_admins_review_and_register(client, prepared, role):
    h, org, base, obs_id, path, payload = prepared
    other = member(client, h, org, role)
    assert client.put(path, headers=other, json=payload).status_code == 403
    assert client.post(base + "/identity-tools", headers=other,
        json=dict(name="Not allowed", rationale="Test")).status_code == 403
    assert client.get(base + "/identity-tools", headers=other).status_code == 200


def test_foreign_namespace_asset_and_false_confirmation_are_rejected(client, db_session, prepared):
    h, org, base, obs_id, path, payload = prepared
    foreign = register(client, "foreign-binding@example.io", "Other")
    other_org = first_org_id(client, foreign)
    other_base = f"/api/v1/orgs/{other_org}"
    tool = client.post(other_base + "/identity-tools", headers=foreign,
        json=dict(name="Foreign tool", rationale="Own namespace")).json()
    assert client.put(path, headers=h, json={**payload, "tool_id": tool["id"]}).status_code == 404
    foreign_upload = upload(client, other_base + "/findings/import", foreign, "sample.nessus")
    assert foreign_upload.status_code == 201
    foreign_observation = db_session.query(FindingObservation).filter(FindingObservation.org_id == UUID(other_org)).first()
    assert client.put(path, headers=h, json={**payload, "canonical_asset_id": foreign_observation.asset_identity["asset_id"]}).status_code == 404
    assert client.put(path, headers=foreign, json=payload).status_code == 403
    assert client.put(path, headers=h, json={**payload, "confirm_mapping": False}).status_code == 422
    assert client.put(path, headers=h, json={**payload, "canonical_asset_id": "11111111-1111-4111-8111-111111111111"}).status_code == 404
    assert db_session.query(ObservationIdentityBinding).count() == 0


def test_tool_names_are_not_reused_and_retired_versions_cannot_bind(client, prepared):
    h, org, base, obs_id, path, payload = prepared
    assert client.post(base + "/identity-tools", headers=h,
        json=dict(name="reviewed nessus instance", rationale="Duplicate label")).status_code == 409
    target = base + f"/identity-tools/{payload['tool_id']}/retire"
    assert client.post(target, headers=h, json=dict(expected_version=2, rationale="Stale")).status_code == 409
    assert client.post(target, headers=h, json=dict(expected_version=1, rationale="Retire")).status_code == 200
    assert client.put(path, headers=h, json=payload).status_code == 409


def test_concurrent_first_reviews_have_one_winner(client, db_session, prepared):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.api.deps import authorize_org_write
    from app.models.enums import UserRole
    from app.models.membership import OrgMembership
    from app.schemas.identity_binding import IdentityBind
    from app.services.identity_bindings import write_binding
    h, org, base, obs_id, path, payload = prepared
    actor_id = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == UUID(org)))
    engine = db_session.get_bind(); db_session.commit()
    barrier = Barrier(2)
    def review(_):
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            barrier.wait(timeout=10)
            try:
                authorize_org_write(db, UUID(org), actor_id, (UserRole.admin,))
                write_binding(db, UUID(org), db.get(FindingObservation, obs_id), actor_id, IdentityBind(**payload))
                return 200
            except HTTPException as exc:
                db.rollback(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(review, range(2))) == [200, 409]
    assert db_session.query(ObservationIdentityBinding).count() == 1


def test_generic_claims_cannot_be_promoted_by_review(client, db_session, prepared):
    import json
    h, org, base, obs_id, path, payload = prepared
    response = upload(client, base + "/findings/import", h, "claim.json", json.dumps([
        dict(hostname="untrusted-host", domain="network_config", severity="high", source="nessus",
             description="Unreviewed generic identity", plugin_id="123", port="443", protocol="tcp")]).encode())
    assert response.status_code == 201
    new_scan = UUID(response.json()["scan_id"])
    obs = db_session.query(FindingObservation).filter(FindingObservation.scan_id == new_scan).one()
    target = f"{base}/findings/{obs.finding_id}/observations/{obs.id}/identity-binding"
    assert client.put(target, headers=h, json={**payload, "canonical_asset_id": obs.asset_identity["asset_id"]}).status_code == 409
    assert db_session.query(ObservationIdentityBinding).count() == 0


def test_repeated_observations_require_review_and_only_then_share_identity(client, db_session, prepared):
    from tests.helpers import FIXTURES
    h, org, base, obs_id, path, payload = prepared
    first = client.put(path, headers=h, json=payload).json()
    original = db_session.get(FindingObservation, obs_id)
    finding_id = original.finding_id
    data = (FIXTURES / "sample.nessus").read_bytes() + b"\n<!-- separate import -->"
    response = upload(client, base + "/findings/import", h, "repeated.nessus", data)
    assert response.status_code == 201
    scan_id = UUID(response.json()["scan_id"])
    second = db_session.query(FindingObservation).filter(FindingObservation.finding_id == finding_id,
        FindingObservation.scan_id == scan_id).one()
    target = f"{base}/findings/{finding_id}/observations/{second.id}/identity-binding"
    unreviewed = client.get(target, headers=h).json()
    assert unreviewed["identity_assessment"]["candidate_key"] is None
    reviewed = client.put(target, headers=h, json=payload)
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["identity_assessment"]["candidate_key"] == first["identity_assessment"]["candidate_key"]
    assert reviewed.json()["reconciliation_eligible"] is False


@pytest.mark.parametrize("field,value", [("IDENTITY_VERSION", "finding-identity-v2"),
                                         ("NESSUS_MAPPING", "nessus-plugin-service-v2")])
def test_new_identity_contract_does_not_reuse_old_review(client, prepared, monkeypatch, field, value):
    from app.services import finding_identity
    h, org, base, obs_id, path, payload = prepared
    first = client.put(path, headers=h, json=payload)
    assert first.status_code == 200
    assert first.json()["identity_assessment"]["candidate_key"]
    monkeypatch.setattr(finding_identity, field, value)
    current = client.get(path, headers=h)
    assert current.status_code == 200
    assert current.json()["identity_assessment"]["candidate_key"] is None
    assert current.json()["identity_binding"]["current"] is False

    rereviewed = client.put(path, headers=h, json={**payload, "expected_version": 1,
        "rationale": "Reviewed the new identity contract"})
    assert rereviewed.status_code == 200
    assert rereviewed.json()["identity_assessment"]["candidate_key"]
    assert rereviewed.json()["identity_assessment"]["candidate_key"] != first.json()["identity_assessment"]["candidate_key"]
