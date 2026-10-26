from datetime import date, datetime
import pytest
from app.services.workflow_deadlines import deadline_today
from app.services.workflow_deadlines import deadline_expiry, validate_deadline_zone


@pytest.mark.parametrize("instant,expected", [
    ("2026-10-26T03:59:59+00:00", date(2026, 10, 25)),
    ("2026-10-26T04:00:00+00:00", date(2026, 10, 26)),
    ("2026-01-26T04:59:59+00:00", date(2026, 1, 25)),
    ("2026-01-26T05:00:00+00:00", date(2026, 1, 26)),
    ("2026-03-09T03:59:59+00:00", date(2026, 3, 8)),
    ("2026-03-09T04:00:00+00:00", date(2026, 3, 9)),
    ("2026-11-02T04:59:59+00:00", date(2026, 11, 1)),
    ("2026-11-02T05:00:00+00:00", date(2026, 11, 2)),
])
def test_eastern_calendar_boundary_including_dst(instant, expected):
    assert deadline_today(datetime.fromisoformat(instant)) == expected


def test_refuses_ambiguous_naive_instants():
    with pytest.raises(ValueError):
        deadline_today(datetime(2026, 10, 26))


@pytest.mark.parametrize("day,zone,expected", [
    ("2026-10-25", "Asia/Kolkata", "2026-10-25T18:30:00+00:00"),
    ("2026-10-25", "America/Los_Angeles", "2026-10-26T07:00:00+00:00"),
    ("2026-03-08", "America/New_York", "2026-03-09T04:00:00+00:00"),
    ("2026-11-01", "America/New_York", "2026-11-02T05:00:00+00:00"),
    ("2026-10-25", "UTC", "2026-10-26T00:00:00+00:00"),
])
def test_fixed_expiry(day, zone, expected):
    assert deadline_expiry(date.fromisoformat(day), zone).isoformat() == expected


def test_invalid_zones_and_nonexistent_days_are_rejected():
    with pytest.raises(ValueError):
        validate_deadline_zone("Not/A_Timezone")
    with pytest.raises(ValueError):
        deadline_expiry(date(2011, 12, 30), "Pacific/Apia")


def test_setting_deadline_never_silently_assumes_server_timezone():
    from app.schemas.finding_workflow import WorkflowPatch
    with pytest.raises(ValueError):
        WorkflowPatch(due_date=date(2026, 10, 25), rationale="Missing author timezone")
    with pytest.raises(ValueError):
        WorkflowPatch(deadline_timezone="UTC", rationale="Cannot silently reinterpret an unchanged date")
