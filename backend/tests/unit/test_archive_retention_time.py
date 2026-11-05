from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from app.models.organization import Organization
from app.services.archive_service import purge_at


@pytest.mark.parametrize("archived", [datetime(2026,11,4,12,tzinfo=ZoneInfo("America/New_York")),
    datetime(2026,6,4,12,tzinfo=ZoneInfo("America/New_York"))])
@pytest.mark.parametrize("days", [180,365])
def test_retention_is_elapsed_days_across_daylight_saving_changes(archived, days):
    org = Organization(name="Retention test", ingestion_overrides={"archive_retention_days":days})
    due = purge_at(org, archived)
    assert due-archived.astimezone(timezone.utc) == timedelta(days=days)
    assert due == purge_at(org, archived.astimezone(timezone.utc))
