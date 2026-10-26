"""Workflow filters share list/search/count/paging scope on PostgreSQL."""
from datetime import datetime, timedelta, timezone
from uuid import UUID
import pytest
from sqlalchemy import select
from app.models.finding import Finding
from app.models.user import User
from tests.conftest import requires_db
from tests.helpers import register, first_org_id
from app.services.workflow_deadlines import deadline_today

pytestmark = requires_db


@pytest.fixture
def data(client, db_session):
    h = register(client, "filters@example.com")
    org = first_org_id(client, h)
    base = f"/api/v1/orgs/{org}/findings"
    owner = db_session.scalar(select(User).where(User.email == "filters@example.com"))
    today = deadline_today()
    for i, status in enumerate(["open", "accepted_risk", "resolved", "mitigated"]):
        db_session.add(Finding(org_id=UUID(org), domain="network_config" if i % 2 else "identity_access",
            severity="high", description=f"Example {i}", workflow_status=status,
            assignee_id=owner.id if i < 2 else None, due_date=today if i == 3 else today - timedelta(days=1),
            risk_review_date=today - timedelta(days=1) if status == "accepted_risk" else None))
    db_session.commit()
    return h, base, str(owner.id)


@pytest.mark.parametrize("params,count", [({"workflow_status": "resolved"}, 1),
    ({"assignee": "unassigned"}, 2), ({"overdue": "due"}, 2),
    ({"overdue": "risk_review"}, 1), ({"workflow_status": "open", "overdue": "risk_review"}, 0)])
def test_filters_and_counts(client, data, params, count):
    h, base, owner = data
    r = client.get(base, headers=h, params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == len(body["items"]) == count
    assert sum(body["domain_counts"].values()) == count


def test_search_assignee_facets_sort_and_validation(client, data):
    h, base, owner = data
    r = client.get(base, headers=h, params={"assignee": owner, "sort": "due_date"})
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert all(item["assignee_label"] == "filters@example.com" for item in r.json()["items"])
    for query, count in [("Accepted risk", 1), ("filters@example.com", 2), ("Example", 4)]:
        response = client.get(base, headers=h, params={"q": query})
        assert response.status_code == 200, response.text
        assert response.json()["total"] == count
    facets = client.get(base + "/facets", headers=h).json()
    assert set(facets["workflow_status"]) == {"open", "accepted_risk", "resolved", "mitigated"}
    assert facets["has_manual_findings"] is True
    assert {item["value"] for item in facets["assignee"]} == {owner, "unassigned"}
    assert client.get(base, headers=h, params={"assignee": "invalid"}).status_code == 422
    assert client.get(base, headers=h, params={"workflow_status": "invalid"}).status_code == 422
    for sort in ["workflow_status", "assignee", "due_date", "risk_review_date"]:
        response = client.get(base, headers=h, params={"sort": sort, "order": "desc", "limit": 2})
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2


def test_union_search_deduplicates_and_keeps_literal_and_date_semantics(client, db_session, data):
    from datetime import date
    h, base, owner = data
    row = db_session.scalar(select(Finding).order_by(Finding.id))
    row.description = r"literal_%\marker"
    row.category = row.source = "literal_%"
    row.due_date = date(2027, 12, 31)
    row.risk_review_date = date(2027, 12, 31)
    db_session.commit()
    for query in ("literal", "_%", r"\marker", "2027-12-31", "12-31"):
        response = client.get(base, headers=h, params={"q": query, "limit": 1})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == sum(body["domain_counts"].values()) == 1
        assert [item["id"] for item in body["items"]] == [str(row.id)]
    assert client.get(base, headers=h, params={"q": "   "}).json()["total"] == 4
    assert client.get(base, headers=h, params={"q": "literal", "domain": "backup_recovery"}).json()["total"] == 0


def test_exact_finding_identity_search_filter_counts_and_tenant_boundary(client, db_session, data):
    h, base, _ = data
    target = client.get(base, headers=h).json()["items"][0]["id"]
    # A UUID in another description must not turn exact-ID lookup into text search.
    other = db_session.scalar(select(Finding).where(Finding.id != UUID(target)))
    other.description = f"Mentions finding {target}"
    db_session.commit()
    for params in ({"q": target.upper()}, {"finding_id": target}):
        response = client.get(base, headers=h, params=params)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == sum(body["domain_counts"].values()) == 1
        assert [item["id"] for item in body["items"]] == [target]
    assert client.get(base, headers=h, params={"q": target[:12]}).json()["items"][0]["id"] != target
    assert client.get(base, headers=h, params={"finding_id": "bad"}).status_code == 422
    foreign = register(client, "foreign-lookup@example.com", "Other")
    foreign_base = f"/api/v1/orgs/{first_org_id(client, foreign)}/findings"
    assert client.get(foreign_base, headers=foreign, params={"finding_id": target}).json()["total"] == 0
    assert client.get(base, headers=foreign, params={"finding_id": target}).status_code == 403
    finding = db_session.get(Finding, UUID(target))
    finding.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert client.get(base, headers=h, params={"finding_id": target}).json()["total"] == 0


def test_unavailable_owner_does_not_leak_label(client, db_session, data):
    h, base, owner = data
    finding = db_session.scalar(select(Finding).where(Finding.assignee_id == UUID(owner)))
    # Preserve the admin's membership for authentication; deactivate a foreign owner
    # would end access. Instead give the finding a real user outside the tenant.
    foreign = User(email="foreign-owner@example.test", name="Do not disclose")
    db_session.add(foreign); db_session.flush()
    finding.assignee_id = foreign.id
    db_session.commit()
    response = client.get(base, headers=h, params={"assignee": str(foreign.id)})
    assert response.status_code == 200
    assert response.json()["items"][0]["assignee_label"] is None
    assert "Do not disclose" not in str(client.get(base + "/facets", headers=h).json())


def test_overdue_uses_eastern_day_not_utc_day(client, db_session, data, monkeypatch):
    h, base, _ = data
    from datetime import date
    from app.api.routes import findings as routes
    for finding in db_session.scalars(select(Finding)).all():
        finding.due_date = date(2026, 10, 25)
    db_session.commit()
    # 03:59 UTC on Oct 26 is still Oct 25 Eastern; midnight Eastern is 04:00 UTC.
    monkeypatch.setattr(routes, "deadline_now", lambda: datetime.fromisoformat("2026-10-26T03:59:59+00:00"))
    assert client.get(base, headers=h, params={"overdue":"due"}).json()["total"] == 0
    monkeypatch.setattr(routes, "deadline_now", lambda: datetime.fromisoformat("2026-10-26T04:00:00+00:00"))
    assert client.get(base, headers=h, params={"overdue":"due"}).json()["total"] == 3
