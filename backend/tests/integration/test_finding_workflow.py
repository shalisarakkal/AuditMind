"""Phase 4 API contract on real PostgreSQL; never calls inference."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member
from app.models.finding import Finding
from app.models.finding_history import FindingHistory
from app.models.event import Event
from app.models.user import User
from app.models.organization import Organization
from app.services.workflow_deadlines import deadline_today

pytestmark = requires_db


@pytest.fixture
def setup(client):
    headers = register(client, "workflow@example.com")
    org = first_org_id(client, headers)
    base = f"/api/v1/orgs/{org}/findings"
    def create():
        response = client.post(base, headers=headers,
            json=dict(domain="network_config", severity="high", description="Synthetic workflow finding"))
        assert response.status_code == 201, response.text
        return response.json()["id"]
    finding = create()
    return headers, org, base, finding, create


def change(client, base, finding, headers, **fields):
    if any(fields.get(key) is not None for key in ("due_date", "risk_review_date")):
        fields.setdefault("deadline_timezone", "America/New_York")
    return client.patch(f"{base}/{finding}/workflow", headers=headers,
        json=dict(expected_version=0, rationale="Reviewed synthetic evidence", **fields))


def test_lifecycle_history_stale_and_scoring_unchanged(client, db_session, setup):
    h, org, base, f, _ = setup
    url = f"{base}/{f}/workflow"
    assert client.get(url, headers=h).json()["status"] == "open"
    from app.services.scoring_service import count_org_findings, score_all_from_counts, overall_score
    score_before = overall_score(score_all_from_counts(count_org_findings(db_session, org)))
    response = change(client, base, f, h, status="resolved", verification="Patch and retest observed")
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 1
    assert change(client, base, f, h, status="open").status_code == 409
    history = client.get(url + "/history", headers=h).json()
    assert len(history) == 1
    assert history[0]["before"]["status"] == "open"
    assert history[0]["after"]["status"] == "resolved"
    assert history[0]["verification"] == "Patch and retest observed"
    assert db_session.scalar(select(func.count()).select_from(Event).where(Event.type == "finding_workflow_changed")) == 1
    assert overall_score(score_all_from_counts(count_org_findings(db_session, org))) == score_before


@pytest.mark.parametrize("status", ["mitigated", "resolved", "false_positive"])
def test_verification_required(client, setup, status):
    h, _, base, f, _ = setup
    assert change(client, base, f, h, status=status).status_code == 422
    assert change(client, base, f, h, status=status, verification="Verified result").status_code == 200


def test_latest_notes_and_historical_assignee_labels(client, db_session, setup):
    h, org, base, f, _ = setup
    user = db_session.scalar(select(User).where(User.email == "workflow@example.com"))
    user.name = "Original owner"
    db_session.commit()
    first = change(client, base, f, h, assignee_id=str(user.id), status="resolved", verification="First verification")
    assert first.status_code == 200
    user.name = "Renamed owner"
    db_session.commit()
    response = client.patch(f"{base}/{f}/workflow", headers=h, json=dict(expected_version=1, rationale="Later note"))
    assert response.status_code == 200
    data = response.json()
    assert data["latest_rationale"]["text"] == "Later note"
    assert data["latest_verification"]["text"] == "First verification"
    history = client.get(f"{base}/{f}/workflow/history", headers=h).json()
    assert history[-1]["after_assignee_label"] == "Original owner"
    assert history[-1]["before_assignee_label"] is None
    # Legacy snapshots resolve only current same-organization membership.
    entry = db_session.scalar(select(FindingHistory).where(FindingHistory.finding_id == f, FindingHistory.version == 1))
    entry.after = {k: v for k, v in entry.after.items() if k != "assignee_label"}
    db_session.commit()
    assert client.get(f"{base}/{f}/workflow/history", headers=h).json()[-1]["after_assignee_label"] == "Renamed owner"
    user.name = " "
    db_session.commit()
    assert client.get(f"{base}/{f}/workflow/history", headers=h).json()[-1]["after_assignee_label"] == "workflow@example.com"
    entry.after = {**entry.after, "assignee_id": str(uuid4())}
    db_session.commit()
    assert client.get(f"{base}/{f}/workflow/history", headers=h).json()[-1]["after_assignee_label"] == "Former/unavailable assignee"


def test_author_zone_persists_through_notes_and_clear(client, setup):
    h, _, base, f, _ = setup
    url = f"{base}/{f}/workflow"
    r = change(client, base, f, h, due_date="2026-10-25", deadline_timezone="Asia/Kolkata")
    assert r.status_code == 200, r.text
    original = r.json()
    assert original["due_timezone"] == "Asia/Kolkata"
    assert datetime.fromisoformat(original["due_expires_at"].replace("Z", "+00:00")).isoformat() == "2026-10-25T18:30:00+00:00"
    note = client.patch(url, headers=h, json={"expected_version":1, "rationale":"Another viewer's note"})
    assert note.json()["due_expires_at"] == original["due_expires_at"]
    assert note.json()["due_timezone"] == "Asia/Kolkata"
    clear = client.patch(url, headers=h, json={"expected_version":2,"rationale":"Clear deadline","due_date":None})
    assert clear.status_code == 200
    assert clear.json()["due_date"] is None and clear.json()["due_timezone"] is None and clear.json()["due_expires_at"] is None
    assert client.patch(url, headers=h, json={"expected_version":3,"rationale":"Bad zone","due_date":"2026-10-25","deadline_timezone":"Bogus/Zone"}).status_code == 422


def test_overdue_is_same_instant_regardless_of_viewer(client, setup, monkeypatch):
    h, _, base, f, create = setup
    second = create()
    assert change(client, base, f, h, due_date="2026-10-25", deadline_timezone="Asia/Kolkata").status_code == 200
    assert change(client, base, second, h, due_date="2026-10-25", deadline_timezone="America/Los_Angeles").status_code == 200
    from app.api.routes import findings as routes
    monkeypatch.setattr(routes, "deadline_now", lambda: datetime.fromisoformat("2026-10-25T20:00:00+00:00"))
    response = client.get(base, headers=h, params={"overdue":"due"})
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [f]


def test_risk_acceptance_admin_and_review_date(client, setup):
    h, org, base, f, _ = setup
    auditor = member(client, h, org, "auditor")
    tomorrow = (deadline_today() + timedelta(days=1)).isoformat()
    assert change(client, base, f, auditor, status="accepted_risk", risk_review_date=tomorrow).status_code == 403
    assert change(client, base, f, h, status="accepted_risk").status_code == 422
    assert change(client, base, f, h, status="accepted_risk", risk_review_date=deadline_today().isoformat()).status_code == 422
    assert change(client, base, f, h, status="accepted_risk", risk_review_date=tomorrow).status_code == 200
    response = client.patch(f"{base}/{f}/workflow", headers=auditor,
        json=dict(expected_version=1, status="open", rationale="Reopen"))
    assert response.status_code == 403
    response = client.patch(f"{base}/{f}/workflow", headers=h,
        json=dict(expected_version=1, status="open", rationale="Reopen"))
    assert response.status_code == 200
    assert response.json()["risk_review_date"] is None


def test_roles_isolation_and_archive(client, db_session, setup):
    h, org, base, f, _ = setup
    viewer = member(client, h, org, "viewer")
    foreign = register(client, "foreign-workflow@example.com")
    assert client.get(f"{base}/{f}/workflow", headers=viewer).status_code == 200
    assert change(client, base, f, viewer, status="open").status_code == 403
    assert client.get(f"{base}/{f}/workflow", headers=foreign).status_code == 403
    from uuid import UUID
    finding = db_session.get(Finding, UUID(f))
    finding.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert change(client, base, f, h, status="open").status_code == 404
    finding.archived_at = None
    organization = db_session.get(Organization, UUID(org))
    organization.archived_at = datetime.now(timezone.utc)
    db_session.commit()
    assert change(client, base, f, h, status="open").status_code == 409


def test_bulk_atomic_stale_and_foreign_targets(client, db_session, setup):
    h, _, base, f, create = setup
    other = create()
    targets = [dict(finding_id=f, expected_version=0), dict(finding_id=other, expected_version=1)]
    def bulk():
        return client.post(base + "/workflow/bulk", headers=h, json=dict(targets=targets,
            patch=dict(status="resolved", rationale="Bulk verification", verification="Retested")))
    assert bulk().status_code == 409
    assert db_session.scalar(select(func.count()).select_from(FindingHistory)) == 0
    targets[1]["expected_version"] = 0
    assert bulk().status_code == 200
    assert db_session.scalar(select(func.count()).select_from(FindingHistory)) == 2
    targets[1]["finding_id"] = str(uuid4())
    assert bulk().status_code == 404


def test_assignment_clear_notes_noop_and_limits(client, db_session, setup):
    h, org, base, f, _ = setup
    user = db_session.scalar(select(User).where(User.email == "workflow@example.com"))
    response = change(client, base, f, h, assignee_id=str(user.id), due_date="2020-01-01")
    assert response.status_code == 200
    assert response.json()["assignee_available"] is True
    response = client.patch(f"{base}/{f}/workflow", headers=h,
        json=dict(expected_version=1, assignee_id=None, rationale="Unassign"))
    assert response.status_code == 200
    assert response.json()["assignee_id"] is None
    # Explicit no-op does not fabricate history; rationale-only appends a note.
    response = client.patch(f"{base}/{f}/workflow", headers=h,
        json=dict(expected_version=2, status="open", rationale="No change"))
    assert response.json()["version"] == 2
    response = client.patch(f"{base}/{f}/workflow", headers=h,
        json=dict(expected_version=2, rationale="Additional verification context"))
    assert response.json()["version"] == 3
    assert change(client, base, f, h, assignee_id=str(uuid4())).status_code == 422
    assert change(client, base, f, h, status=None).status_code == 422
    response = client.post(base + "/workflow/bulk", headers=h,
        json=dict(targets=[dict(finding_id=f, expected_version=3)] * 2, patch=dict(rationale="Duplicate targets")))
    assert response.status_code == 422


def test_concurrent_edits_one_wins(db_session, client, setup):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    from uuid import UUID
    from fastapi import HTTPException
    from app.models.membership import OrgMembership
    from app.schemas.finding_workflow import WorkflowPatch, WorkflowTarget
    from app.services.finding_workflow import update_workflows
    h, org, base, f, _ = setup
    actor = db_session.scalar(select(User).where(User.email == "workflow@example.com")).id
    engine = db_session.get_bind()
    db_session.commit()
    def edit(day):
        with Session(engine) as db:
            membership = db.get(OrgMembership, (actor, UUID(org)))
            try:
                update_workflows(db, UUID(org), membership,
                    [WorkflowTarget(finding_id=f, expected_version=0)],
                    WorkflowPatch(due_date=day, deadline_timezone="America/New_York", rationale="Concurrent edit"))
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit, ["2026-11-01", "2026-11-02"])) == [200, 409]
    assert db_session.scalar(select(func.count()).select_from(FindingHistory)) == 1


def test_assignment_deactivated_or_membership_removed(client, db_session, setup):
    from uuid import UUID
    from app.models.membership import OrgMembership
    h, org, base, f, _ = setup
    member(client, h, org, "viewer")
    viewer = db_session.scalar(select(User).where(User.email == f"viewer-{org[:8]}@example.io"))
    assert change(client, base, f, h, assignee_id=str(viewer.id)).status_code == 200
    viewer.is_active = False
    db_session.commit()
    assert client.get(f"{base}/{f}/workflow", headers=h).json()["assignee_available"] is False
    response = client.patch(f"{base}/{f}/workflow", headers=h,
        json=dict(expected_version=1, assignee_id=str(viewer.id), rationale="Reassign"))
    assert response.status_code == 422
    viewer.is_active = True
    db_session.delete(db_session.get(OrgMembership, (viewer.id, UUID(org))))
    db_session.commit()
    assert client.get(f"{base}/{f}/workflow", headers=h).json()["assignee_available"] is False
    assert client.get(f"{base}/{f}/workflow/history?limit=101", headers=h).status_code == 422
