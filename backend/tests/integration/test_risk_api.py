from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.enums import Domain, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from tests.conftest import requires_db


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
