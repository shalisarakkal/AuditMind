"""Stage-one registry: real PostgreSQL, no approval or scoring activation."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest

from app.models.enums import Domain, Severity
from app.models.event import Event
from app.models.finding import Finding
from app.models.scoring_qualification import DomainEvidenceQualification
from tests.conftest import requires_db
from tests.helpers import first_org_id, member, register

pytestmark = requires_db


@pytest.fixture
def owner(client):
    headers = register(client, "qualification-owner@example.io")
    org = first_org_id(client, headers)
    return headers, org, f"/api/v1/orgs/{org}/scoring"


def draft(**overrides):
    return {"expected_version": 0, "scope": "All active organization assets", "rationale": "Draft only; operational review pending", **overrides}


def test_settings_default_off_and_toggle_is_versioned(client, owner):
    headers, _, path = owner
    response = client.get(path + "/settings", headers=headers)
    assert response.json() == {"evidence_qualified_enabled": False, "version": 0, "available": True}
    assert response.headers["cache-control"] == "no-store"
    saved = client.patch(path + "/settings", headers=headers, json={"expected_version": 0, "evidence_qualified_enabled": False})
    assert saved.json()["version"] == 1
    assert client.patch(path + "/settings", headers=headers, json={"expected_version": 0, "evidence_qualified_enabled": False}).status_code == 409
    assert client.patch(path + "/settings", headers=headers, json={"expected_version": 1, "evidence_qualified_enabled": "false"}).status_code == 422
    enabled = client.patch(path + "/settings", headers=headers, json={"expected_version": 1, "evidence_qualified_enabled": True})
    assert enabled.json() == {"evidence_qualified_enabled": True, "version": 2, "available": True}


def test_disable_can_roll_back_a_preexisting_enabled_row(client, owner, db_session):
    from app.models.scoring_qualification import OrganizationScoringSettings
    headers, org, path = owner
    db_session.add(OrganizationScoringSettings(org_id=uuid.UUID(org), evidence_qualified_enabled=True, version=3))
    db_session.commit()
    response = client.patch(path + "/settings", headers=headers, json={"expected_version": 3, "evidence_qualified_enabled": False})
    assert response.json() == {"evidence_qualified_enabled": False, "version": 4, "available": True}
    db_session.expire_all()
    assert db_session.get(OrganizationScoringSettings, uuid.UUID(org)).evidence_qualified_enabled is False


def test_admin_drafts_are_versioned_audited_and_do_not_affect_scores(client, owner, db_session):
    headers, org, path = owner
    before = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    first = client.put(path + "/qualifications/network_config", headers=headers, json=draft())
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["status"] == "draft" and data["version"] == 1
    assert data["policy_version"] == "domain-evidence-v1"
    assert data["updated_by"] is not None
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft()).status_code == 409
    second = client.put(path + "/qualifications/network_config", headers=headers, json=draft(expected_version=1, rationale="Changed draft"))
    assert second.json()["version"] == 2
    assert client.get(path + "/qualifications", headers=headers).json() == [second.json()]
    after = client.get(f"/api/v1/orgs/{org}/dashboard", headers=headers).json()
    assert after.pop("evidence_revision") > before.pop("evidence_revision")
    assert after == before
    events = db_session.query(Event).filter_by(item="Evidence qualification draft").all()
    assert len(events) == 2
    assert events[-1].details["after"]["version"] == 2


@pytest.mark.parametrize("role", ["viewer", "auditor"])
def test_member_reads_but_only_admin_writes(client, owner, role):
    headers, org, path = owner
    other = member(client, headers, org, role)
    assert client.get(path + "/qualifications", headers=other).status_code == 200
    assert client.put(path + "/qualifications/network_config", headers=other, json=draft()).status_code == 403
    assert client.patch(path + "/settings", headers=other, json={"expected_version": 0, "evidence_qualified_enabled": False}).status_code == 403


def test_foreign_and_archived_organizations_are_protected(client, owner, db_session):
    from app.models.organization import Organization
    headers, org, path = owner
    outsider = register(client, "qualification-outsider@example.io")
    for suffix in ["/settings", "/qualifications"]:
        assert client.get(path + suffix, headers=outsider).status_code == 403
    assert client.put(path + "/qualifications/network_config", headers=outsider, json=draft()).status_code == 403
    db_session.get(Organization, uuid.UUID(org)).archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft()).status_code == 409


def test_bound_sources_reject_changes_foreign_domain_archive_and_future_dates(client, owner, db_session):
    headers, org, path = owner
    finding = Finding(org_id=uuid.UUID(org), domain=Domain.network_config, severity=Severity.high, description="Observed exposure")
    db_session.add(finding)
    db_session.commit()
    bound = client.get(path + f"/source-findings/{finding.id}", headers=headers).json()
    observation = {k: bound[k] for k in ("source_type", "source_id", "source_sha256")}
    observation.update(objective="exposure_inventory", observed_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft(observations=[observation])).status_code == 200
    payload = draft(expected_version=1, observations=[observation])
    future = {**observation, "observed_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft(expected_version=1, observations=[future])).status_code == 422
    wrong = {**observation, "objective": "restore_test"}
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft(expected_version=1, observations=[wrong])).status_code == 422
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft(expected_version=1, observations=[observation, observation])).status_code == 422
    finding.description = "Materially changed evidence"
    db_session.commit()
    assert client.put(path + "/qualifications/network_config", headers=headers, json=payload).status_code == 409
    finding.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.put(path + "/qualifications/network_config", headers=headers, json=payload).status_code == 404
    assert client.get(path + f"/source-findings/{finding.id}", headers=headers).status_code == 404
    assert db_session.query(DomainEvidenceQualification).one().version == 1


def test_foreign_source_ids_cannot_be_bound(client, owner, db_session):
    headers, org, path = owner
    other = register(client, "foreign-evidence@example.io")
    finding = Finding(org_id=uuid.UUID(first_org_id(client, other)), domain=Domain.network_config, severity=Severity.high)
    db_session.add(finding)
    db_session.commit()
    assert client.get(path + f"/source-findings/{finding.id}", headers=headers).status_code == 404
    observation = {"objective": "exposure_inventory", "source_id": str(finding.id), "source_sha256": "0" * 64,
                   "observed_at": datetime.now(timezone.utc).isoformat()}
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft(observations=[observation])).status_code == 404
    assert db_session.query(DomainEvidenceQualification).count() == 0


def test_simultaneous_draft_creation_requires_reload(client, owner, db_session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException, Response
    from sqlalchemy.orm import sessionmaker
    from app.api.deps import authorize_org_write
    from app.api.routes.scoring_qualifications import save_draft
    from app.models.enums import UserRole
    from app.models.user import User
    from app.schemas.scoring_qualification import QualificationDraftUpdate

    _, org, _ = owner
    user_id = db_session.query(User).filter_by(email="qualification-owner@example.io").one().id
    sessions = sessionmaker(bind=db_session.get_bind())
    barrier = Barrier(2)

    def submit(_):
        with sessions() as session:
            barrier.wait(timeout=10)
            admin = authorize_org_write(session, uuid.UUID(org), user_id, (UserRole.admin,))
            try:
                result = save_draft(uuid.UUID(org), Domain.network_config,
                    QualificationDraftUpdate(**draft()), Response(), session, admin)
                return result.version
            except HTTPException as exc:
                session.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == [1, 409]
    db_session.expire_all()
    assert db_session.query(DomainEvidenceQualification).one().version == 1


@pytest.mark.parametrize("extra", [{"status": "approved"}, {"policy_version": "fake"}, {"updated_by": str(uuid.uuid4())}, {"scope": " "}])
def test_draft_cannot_assign_approval_or_identity(client, owner, extra):
    headers, _, path = owner
    assert client.put(path + "/qualifications/network_config", headers=headers, json=draft(**extra)).status_code == 422
