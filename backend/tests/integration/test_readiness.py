from datetime import datetime, timedelta, timezone

import pytest

from app.models.event import WorkerStatus
from app.services.readiness import inspect_readiness
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.mark.parametrize("age,expected", [(0, True), (3600, False), (-60, False)])
def test_readiness_worker_and_storage(db_session, tmp_path, age, expected):
    now = datetime.now(timezone.utc)
    db_session.add(WorkerStatus(id=1, started_at=now, heartbeat_at=now - timedelta(seconds=age)))
    db_session.commit()
    checks = inspect_readiness(db_session.get_bind(), tmp_path)
    assert checks == {"database": True, "uploads": True, "worker": expected}
    assert inspect_readiness(db_session.get_bind(), tmp_path / "absent")["uploads"] is False


def test_readiness_missing_worker(db_session, tmp_path):
    assert inspect_readiness(db_session.get_bind(), tmp_path) == {"database": True, "uploads": True, "worker": False}
