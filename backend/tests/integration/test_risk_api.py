from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.enums import Domain, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from tests.conftest import requires_db
import pytest


@requires_db
def test_risk_score_reflects_seeded_findings(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    try:
        register_resp = client.post(
            "/api/v1/auth/register",
            json={"org_name": "Acme Corp", "email": "risk@acmecorp.io", "password": "Sup3rSecret!"},
        )
        token = register_resp.json()["access_token"]

        org = db_session.query(Organization).filter(Organization.name == "Acme Corp").one()
        db_session.add(
            Finding(
                org_id=org.id,
                domain=Domain.identity_access,
                severity=Severity.critical,
                description="No MFA enforced",
            )
        )
        db_session.commit()

        resp = client.post(
            f"/api/v1/orgs/{org.id}/risk/score",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()

        identity_domain = next(d for d in body["domains"] if d["dimension"] == "identity_access")
        assert identity_domain["score"] == 85.0
        assert identity_domain["tier"] == "low"
        assert body["overall_score"] < 100.0
    finally:
        app.dependency_overrides.clear()


@requires_db
@pytest.mark.parametrize("change,expected", [("demote", 403), ("deactivate", 403), ("archive", 409)])
def test_risk_snapshot_rechecks_authorization_before_publishing(client, db_session, monkeypatch, change, expected):
    from datetime import datetime, timezone
    from uuid import UUID
    from sqlalchemy import select, func
    from sqlalchemy.orm import Session
    from app.models.membership import OrgMembership
    from app.models.enums import UserRole
    from app.models.user import User
    from app.models.risk_score import RiskScore
    from app.services import status_scoring
    from tests.helpers import register, first_org_id
    headers = register(client, "risk-admission@example.com")
    org_id = UUID(first_org_id(client, headers))
    actor_id = db_session.scalar(select(User.id).where(User.email == "risk-admission@example.com"))
    original = status_scoring.apply_policy

    def capture_then_change(*args, **kwargs):
        captured = original(*args, **kwargs)
        # The snapshot must release its earlier permission fence. An edit
        # committed during that interval must prevent publishing new scores.
        with Session(db_session.get_bind()) as editor:
            if change == "demote":
                editor.get(OrgMembership, (actor_id, org_id)).role = UserRole.viewer
            elif change == "deactivate":
                editor.get(User, actor_id).is_active = False
            else:
                editor.get(Organization, org_id).archived_at = datetime.now(timezone.utc)
            editor.commit()
        return captured

    monkeypatch.setattr(status_scoring, "apply_policy", capture_then_change)
    response = client.post(f"/api/v1/orgs/{org_id}/risk/score", headers=headers)
    assert response.status_code == expected, response.text
    assert db_session.scalar(select(func.count()).select_from(RiskScore)) == 0
