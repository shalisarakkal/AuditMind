"""Explicit cross-import review boundaries; no merge or workflow side effects."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.models.asset import Asset
from app.models.finding import Finding
from app.models.finding_identity_binding import IdentityTool, ObservationIdentityBinding
from app.models.finding_observation import FindingObservation
from app.models.scan import Scan
from tests.conftest import requires_db
from tests.helpers import FIXTURES, first_org_id, member, register, upload
from tests.integration.test_identity_bindings import prepared  # noqa: F401

pytestmark = requires_db


@pytest.fixture
def pair(client, db_session, prepared):
    h, org, base, obs_id, path, binding = prepared
    assert client.put(path, headers=h, json=binding).status_code == 200
    source = db_session.get(FindingObservation, obs_id)
    result = upload(client, base + "/findings/import", h, "later.nessus",
        (FIXTURES / "sample.nessus").read_bytes() + b"\n<!-- later import -->")
    assert result.status_code == 201, result.text
    target = db_session.query(FindingObservation).filter(
        FindingObservation.scan_id == UUID(result.json()["scan_id"]),
        FindingObservation.finding_id == source.finding_id).one()
    endpoint = f"{base}/findings/{target.finding_id}/observations/{target.id}/identity-binding"
    return h, org, base, source, target, endpoint, binding


def preview(client, pair):
    h, _, _, source, _, endpoint, _ = pair
    return client.post(endpoint + "/compare", headers=h, json=dict(source_observation_id=str(source.id)))


def payload(pair, body):
    return dict(source_observation_id=str(pair[3].id), expected_version=body["target_version"],
        review_token=body["review_token"], confirm_mapping=True, rationale="Reviewed later scanner and canonical host")


def test_explicit_carry_forward_pins_lineage_without_changing_finding(client, db_session, pair):
    h, _, base, source, target, endpoint, _ = pair
    finding = db_session.get(Finding, target.finding_id)
    before = (finding.workflow_status, finding.workflow_version, finding.description, finding.severity, finding.scan_id)
    result = preview(client, pair)
    assert result.status_code == 200, result.text
    body = result.json()
    assert "binding_context" not in body  # server-only final-write fence
    assert body["result"] == "same_finding"
    assert body["already_reviewed"] is False
    assert db_session.query(ObservationIdentityBinding).count() == 1  # preview is read-only
    applied = client.post(endpoint + "/carry-forward", headers=h, json=payload(pair, body))
    assert applied.status_code == 200, applied.text
    assert applied.json()["identity_binding"]["current"] is True
    assert applied.json()["identity_assessment"]["candidate_key"] == body["candidate_key"]
    assert applied.json()["reconciliation_eligible"] is False
    assert applied.json()["identity_binding"]["reviewed_from"] == dict(observation_id=str(source.id), version=1)
    decision = db_session.query(ObservationIdentityBinding).filter_by(observation_id=target.id).one()
    assert decision.context["reviewed_from"] == dict(observation_id=str(source.id), version=1)
    db_session.refresh(finding)
    assert before == (finding.workflow_status, finding.workflow_version, finding.description, finding.severity, finding.scan_id)
    # Independent review survives reference withdrawal; not a transitive grant.
    reference = f"{base}/findings/{source.finding_id}/observations/{source.id}/identity-binding"
    assert client.post(reference + "/revoke", headers=h, json=dict(expected_version=1, rationale="Withdraw reference")).status_code == 200
    assert client.get(endpoint, headers=h).json()["identity_binding"]["current"] is True
    assert client.post(endpoint + "/carry-forward", headers=h, json=payload(pair, body)).status_code == 409


@pytest.mark.parametrize("field,value", [("port", 12345), ("protocol", "udp"), ("plugin_id", "9999999"),
                                         ("port", None), ("protocol", "bogus")])
def test_changed_or_missing_native_identity_never_inherits(client, db_session, pair, field, value):
    target = pair[4]
    target.source_identity = {**target.source_identity, field: value}
    db_session.commit()
    assert preview(client, pair).status_code == 409
    assert db_session.query(ObservationIdentityBinding).count() == 1


@pytest.mark.parametrize("change", ["source_revoke", "tool", "target_asset", "canonical_asset", "target_scan",
                                     "source_scan", "target_finding", "target_review", "contract"])
def test_preview_is_invalidated_before_apply(client, db_session, pair, change, monkeypatch):
    h, _, base, source, target, endpoint, binding = pair
    result = preview(client, pair)
    assert result.status_code == 200, result.text
    body = result.json()
    if change == "source_revoke":
        ref = f"{base}/findings/{source.finding_id}/observations/{source.id}/identity-binding/revoke"
        assert client.post(ref, headers=h, json=dict(expected_version=1, rationale="Revoked before apply")).status_code == 200
    elif change == "tool":
        db_session.get(IdentityTool, UUID(binding["tool_id"])).active = False
    elif change in {"target_asset", "canonical_asset"}:
        asset_id = target.asset_identity["asset_id"] if change == "target_asset" else binding["canonical_asset_id"]
        db_session.get(Asset, UUID(asset_id)).hostname = "changed-after-preview"
    elif change in {"target_scan", "source_scan"}:
        db_session.get(Scan, (target if change == "target_scan" else source).scan_id).archived_at = datetime.now(timezone.utc)
    elif change == "target_finding":
        db_session.get(Finding, target.finding_id).archived_at = datetime.now(timezone.utc)
    elif change == "target_review":
        assert client.put(endpoint, headers=h, json=binding).status_code == 200
    elif change == "contract":
        from app.services import finding_identity
        monkeypatch.setattr(finding_identity, "IDENTITY_VERSION", "finding-identity-vNext")
    db_session.commit()
    applied = client.post(endpoint + "/carry-forward", headers=h, json=payload(pair, body))
    assert applied.status_code == 409, applied.text


def test_canonical_conflict_is_exposed_and_never_silently_merges(client, db_session, pair):
    h, org, _, _, target, _, _ = pair
    finding = Finding(org_id=UUID(org), severity="high", domain="network_config", description="Conflicting reviewed finding")
    db_session.add(finding); db_session.flush()
    target.finding_id = finding.id
    db_session.commit()
    pair = (*pair[:5], f"{pair[2]}/findings/{finding.id}/observations/{target.id}/identity-binding", pair[6])
    result = preview(client, pair)
    assert result.status_code == 200, result.text
    assert result.json()["result"] == "canonical_conflict"
    assert client.post(pair[5] + "/carry-forward", headers=h, json=payload(pair, result.json())).status_code == 409
    db_session.refresh(target)
    assert target.finding_id == finding.id
    assert db_session.query(ObservationIdentityBinding).count() == 1


@pytest.mark.parametrize("role", ["viewer", "auditor"])
def test_readonly_roles_can_compare_but_not_apply(client, pair, role):
    h, org, _, _, _, endpoint, _ = pair
    other = member(client, h, org, role)
    result = client.post(endpoint + "/compare", headers=other, json=dict(source_observation_id=str(pair[3].id)))
    assert result.status_code == 200
    assert client.post(endpoint + "/carry-forward", headers=other, json=payload(pair, result.json())).status_code == 403


def test_reference_is_tenant_scoped_and_must_be_from_earlier_import(client, pair):
    h, _, _, source, target, endpoint, _ = pair
    for source_id in (target.id, source.id):
        reference_endpoint = endpoint if source_id == target.id else f"{pair[2]}/findings/{source.finding_id}/observations/{source.id}/identity-binding"
        assert client.post(reference_endpoint + "/compare", headers=h,
            json=dict(source_observation_id=str(target.id))).status_code == 409
    assert client.post(endpoint + "/compare", headers=h, json=dict(source_observation_id=str(uuid4()))).status_code == 404
    foreign = register(client, "comparison-other@example.io")
    foreign_org = first_org_id(client, foreign)
    assert foreign_org != pair[1]
    assert client.post(endpoint + "/compare", headers=foreign,
        json=dict(source_observation_id=str(source.id))).status_code == 403


def test_confirmation_and_token_are_required(client, db_session, pair):
    result = preview(client, pair).json()
    for updates, expected in [({"confirm_mapping": False}, 422), ({"review_token": "0" * 64}, 409),
                              ({"review_token": "invalid"}, 422), ({"expected_version": 1}, 409)]:
        response = client.post(pair[5] + "/carry-forward", headers=pair[0], json={**payload(pair, result), **updates})
        assert response.status_code == expected, response.text
    assert db_session.query(ObservationIdentityBinding).count() == 1


@pytest.mark.parametrize("change", ["generic", "profile", "unreviewed", "same_import", "same_time"])
def test_unsupported_or_non_prior_observations_are_blocked(client, db_session, pair, change):
    source, target = pair[3:5]
    if change == "generic":
        target.scan_type = "findings"
    elif change == "profile":
        target.profile = "generated-rules"
    elif change == "unreviewed":
        db_session.query(ObservationIdentityBinding).delete()
    elif change == "same_import":
        target.import_id = source.import_id
        target.occurrence = 100000  # retain unique import/occurrence contract
    else:
        target.recorded_at = source.recorded_at
    db_session.commit()
    assert preview(client, pair).status_code == 409


def test_same_native_material_in_a_different_tool_is_a_conflicting_review(client, db_session, pair):
    h, _, base, _, _, endpoint, binding = pair
    other = client.post(base + "/identity-tools", headers=h,
        json=dict(name="Different scanner", rationale="Independent tool namespace")).json()
    assert client.put(endpoint, headers=h, json={**binding, "tool_id": other["id"]}).status_code == 200
    assert preview(client, pair).status_code == 409


def test_noop_and_replayed_reviews_never_append_duplicate_decisions(client, db_session, pair):
    h, _, _, _, _, endpoint, _ = pair
    first = preview(client, pair).json()
    assert client.post(endpoint + "/carry-forward", headers=h, json=payload(pair, first)).status_code == 200
    current = preview(client, pair).json()
    assert current["already_reviewed"] is True
    assert client.post(endpoint + "/carry-forward", headers=h, json=payload(pair, current)).status_code == 409
    assert db_session.query(ObservationIdentityBinding).count() == 2


def test_changed_payload_matches_identity_but_never_overwrites_workflow_or_details(client, db_session, pair):
    target = pair[4]
    finding = db_session.get(Finding, target.finding_id)
    before = (finding.description, finding.severity, finding.workflow_status, finding.workflow_version)
    target.payload = {**target.payload, "description": "New source details", "severity": "critical"}
    db_session.commit()
    result = preview(client, pair)
    assert result.status_code == 200
    applied = client.post(pair[5] + "/carry-forward", headers=pair[0], json=payload(pair, result.json()))
    assert applied.status_code == 200
    db_session.refresh(finding)
    assert before == (finding.description, finding.severity, finding.workflow_status, finding.workflow_version)


def test_token_pins_target_host_even_when_reference_is_unchanged(client, db_session, pair):
    h, org, _, _, target, endpoint, _ = pair
    captured = Asset(org_id=UUID(org), type="server", hostname="separately-imported-host")
    db_session.add(captured); db_session.flush()
    target.asset_identity = {**target.asset_identity, "asset_id": str(captured.id)}
    db_session.commit()
    result = preview(client, pair)
    assert result.status_code == 200
    captured.hostname = "edited-after-preview"
    db_session.commit()
    applied = client.post(endpoint + "/carry-forward", headers=h, json=payload(pair, result.json()))
    assert applied.status_code == 409
    assert "compare again" in applied.text
    assert db_session.query(ObservationIdentityBinding).count() == 1


def test_concurrent_carry_forward_has_one_winner(client, db_session, pair):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from app.api.deps import authorize_org_write
    from app.models.enums import UserRole
    from app.models.membership import OrgMembership
    from app.schemas.identity_binding import IdentityCarryForward
    from app.services.identity_comparison import carry_forward
    body = preview(client, pair).json()
    org_id, target_id = UUID(pair[1]), pair[4].id
    actor_id = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == org_id))
    engine = db_session.get_bind(); db_session.commit()
    barrier = Barrier(2)
    def review(_):
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            barrier.wait(timeout=10)
            try:
                authorize_org_write(db, org_id, actor_id, (UserRole.admin,))
                carry_forward(db, org_id, db.get(FindingObservation, target_id), actor_id,
                    IdentityCarryForward(**payload(pair, body)))
                return 200
            except HTTPException as exc:
                db.rollback(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(review, range(2))) == [200, 409]
    assert db_session.query(ObservationIdentityBinding).count() == 2


def test_review_created_during_readonly_comparison_returns_conflict_not_500(client, db_session, pair, monkeypatch):
    from sqlalchemy import select
    from app.models.membership import OrgMembership
    from app.schemas.identity_binding import IdentityBind
    from app.services import identity_comparison
    from app.services.identity_bindings import write_binding
    actor_id = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == UUID(pair[1])))
    original = identity_comparison.read_observations
    def raced(db, org_id, observations):
        result = original(db, org_id, observations)
        write_binding(db, org_id, observations[1], actor_id, IdentityBind(**pair[6]))
        return result
    monkeypatch.setattr(identity_comparison, "read_observations", raced)
    response = preview(client, pair)
    assert response.status_code == 409, response.text


def test_asset_edit_between_token_check_and_binding_write_is_rejected(client, db_session, pair, monkeypatch):
    from sqlalchemy import update
    from app.services import identity_comparison
    body = preview(client, pair).json()
    original = identity_comparison.write_binding
    def raced(db, org_id, target, actor_id, binding, **kwargs):
        # Simulate a concurrently committed importer asset edit after the save's
        # token validation but before its binding context is captured.
        db.execute(update(Asset).where(Asset.id == UUID(target.asset_identity["asset_id"])).values(hostname="edited-mid-save"))
        return original(db, org_id, target, actor_id, binding, **kwargs)
    monkeypatch.setattr(identity_comparison, "write_binding", raced)
    response = client.post(pair[5] + "/carry-forward", headers=pair[0], json=payload(pair, body))
    assert response.status_code == 409, response.text
    assert db_session.query(ObservationIdentityBinding).count() == 1
