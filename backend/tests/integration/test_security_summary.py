from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.event import Event
from app.models.enums import Criticality
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member

pytestmark = requires_db


def test_summary_exact_window_and_matching_activity(client, db_session, monkeypatch):
    from app.api.routes import dashboard
    now = datetime.now(timezone.utc)
    class Clock:
        @staticmethod
        def now(_):
            return now
    monkeypatch.setattr(dashboard, "datetime", Clock)
    headers = register(client, "summary@example.io")
    org = first_org_id(client, headers)
    viewer = member(client, headers, org, "viewer")
    start = now - timedelta(days=7)
    for kind in ("member_added", "role_changed", "purge"):
        for at, outcome, scope in ((start, "completed", org),
                (start - timedelta(microseconds=1), "completed", org),
                (now, "completed", org), (now - timedelta(seconds=1), "failed", org),
                (now - timedelta(seconds=1), "completed", None)):
            db_session.add(Event(type=kind, org_id=scope, actor_label="Synthetic actor",
                started_at=at, ended_at=at, outcome=outcome, criticality=Criticality.info))
    db_session.commit()
    base = f"/api/v1/orgs/{org}"
    response = client.get(base + "/dashboard/security-summary", headers=viewer)
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {"member_added": 1, "role_changed": 1, "purge": 1}
    for kind, count in body["counts"].items():
        events = client.get(base + "/events", headers=viewer, params={
            "type": kind, "result": "completed", "window_start": body["window_start"], "window_end": body["window_end"]})
        assert events.status_code == 200, events.text
        assert events.json()["total"] == count
    foreign = register(client, "summary-foreign@example.io")
    assert client.get(base + "/dashboard/security-summary", headers=foreign).status_code == 403
    assert client.get(f"/api/v1/orgs/{uuid4()}/dashboard/security-summary", headers=headers).status_code in (403, 404)


@pytest.mark.parametrize("params", [
    {"window_start": "2026-10-25T00:00:00Z"},
    {"window_end": "2026-10-26T00:00:00Z"},
    {"window_start": "2026-10-25T00:00:00", "window_end": "2026-10-26T00:00:00Z"},
    {"window_start": "2026-10-26T00:00:00Z", "window_end": "2026-10-25T00:00:00Z"},
    {"window_start": "2026-10-26T00:00:00Z", "window_end": "2026-10-26T00:00:00Z"},
])
def test_invalid_exact_activity_windows(client, params):
    headers = register(client, "window@example.io")
    org = first_org_id(client, headers)
    assert client.get(f"/api/v1/orgs/{org}/events", headers=headers, params=params).status_code == 422
