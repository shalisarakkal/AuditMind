"""Operational contracts against PostgreSQL, without external provider calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from anthropic import APITimeoutError
import httpx

from app.core.config import settings
from app.models.ai_usage import AIUsage
from app.models.report import Report
from app.models.enums import ReportStatus
from app.services import ai_accounting, claude_service, report_service
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, approve_reports

pytestmark = requires_db


@pytest.fixture
def org(client):
    headers = register(client, "report-ops@example.com")
    org_id = first_org_id(client, headers)
    approve_reports(client, headers, org_id)
    return headers, UUID(org_id)


def test_idempotency_replays_and_rejects_changed_payload(client, org, db_session):
    headers, org_id = org
    endpoint = f"/api/v1/orgs/{org_id}/reports/generate"
    keyed = {**headers, "Idempotency-Key": "quarterly-2026"}
    first = client.post(endpoint, headers=keyed, json={"title": "Quarterly"})
    replay = client.post(endpoint, headers=keyed, json={"title": "Quarterly"})
    assert first.status_code == replay.status_code == 202
    assert first.json()["id"] == replay.json()["id"]
    changed = client.post(endpoint, headers=keyed, json={"title": "Other"})
    assert changed.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Report)) == 1
    assert client.post(endpoint, headers=headers, json={"title": "Quarterly"}).status_code == 202
    assert db_session.scalar(select(func.count()).select_from(Report)) == 2


def test_idempotency_concurrent_sessions_create_one_report(client, org, db_session):
    _, org_id = org
    bind = db_session.get_bind()
    def queue(_):
        with Session(bind) as db:
            return report_service.queue_report_generation(db, org_id, "Concurrent", idempotency_key="same").id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(queue, range(2)))
    assert ids[0] == ids[1]


def test_quota_is_atomic_persistent_and_org_scoped(client, org, db_session, monkeypatch):
    _, org_id = org
    bind = db_session.get_bind()
    monkeypatch.setattr(settings, "CLAUDE_ORG_CALLS_PER_HOUR", 1)
    def reserve(_):
        try:
            return ai_accounting.reserve(bind, org_id, "test-model", .01)
        except claude_service.ClaudeOperationalError as exc:
            assert exc.status_code == 429
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(reserve, range(2)))
    assert sum(item is not None for item in ids) == 1
    claude_service.reset_call_stats()  # Restarting process metrics cannot reset admission.
    assert reserve(0) is None
    other = register(client, "other-ops@example.com")
    other_id = UUID(first_org_id(client, other))
    assert ai_accounting.reserve(bind, other_id, "test-model", .01)
    with Session(bind) as db, db.begin():
        row = db.scalar(select(AIUsage).where(AIUsage.org_id == org_id))
        row.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert reserve(0) is not None


def test_cost_reservations_and_confirmed_usage(client, org, db_session, monkeypatch):
    _, org_id = org
    bind = db_session.get_bind()
    monkeypatch.setattr(settings, "CLAUDE_ORG_MAX_COST_PER_HOUR_USD", 1.5)
    first = ai_accounting.reserve(bind, org_id, "test-model", .01)
    with pytest.raises(claude_service.ClaudeOperationalError):
        ai_accounting.reserve(bind, org_id, "test-model", .01)
    ai_accounting.finish(bind, first, input_tokens=10, output_tokens=20, cost_usd=.1, success=True)
    second = ai_accounting.reserve(bind, org_id, "test-model", .01)
    ai_accounting.finish(bind, second)  # Unknown/failed outcomes retain reserved cost.
    with pytest.raises(claude_service.ClaudeOperationalError):
        ai_accounting.reserve(bind, org_id, "test-model", .01)
    with Session(bind) as db:
        row = db.get(AIUsage, first)
        assert (row.input_tokens, row.output_tokens, row.cost_usd, row.status) == (10, 20, .1, "succeeded")


def test_provider_timeouts_are_persisted_per_attempt(client, org, db_session, monkeypatch):
    _, org_id = org
    provider = Mock()
    provider.messages.create.side_effect = APITimeoutError(request=httpx.Request("POST", "https://provider.invalid"))
    monkeypatch.setattr(claude_service, "get_client", lambda: provider)
    monkeypatch.setattr(claude_service.time, "sleep", lambda _: None)
    with pytest.raises(claude_service.ClaudeOperationalError):
        claude_service.ask_claude("Evidence", org_id=org_id, usage_bind=db_session.get_bind())
    rows = db_session.scalars(select(AIUsage)).all()
    assert len(rows) == 3 and all(row.status == "failed" for row in rows)


def test_provider_success_records_tokens_and_quota_blocks_network(client, org, db_session, monkeypatch):
    _, org_id = org
    provider = Mock()
    provider.messages.create.return_value = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        content=[SimpleNamespace(type="text", text="Assessment")])
    monkeypatch.setattr(claude_service, "get_client", lambda: provider)
    monkeypatch.setattr(settings, "CLAUDE_ORG_CALLS_PER_HOUR", 1)
    bind = db_session.get_bind()
    assert claude_service.ask_claude("Evidence", org_id=org_id, usage_bind=bind) == "Assessment"
    row = db_session.scalar(select(AIUsage))
    assert (row.input_tokens, row.output_tokens, row.status) == (100, 20, "succeeded")
    assert row.cost_usd == pytest.approx(claude_service.estimate_cost_usd(100, 20))
    with pytest.raises(claude_service.ClaudeOperationalError) as failure:
        claude_service.ask_claude("Evidence", org_id=org_id, usage_bind=bind)
    assert failure.value.status_code == 429
    assert provider.messages.create.call_count == 1


def test_idempotency_keys_are_org_scoped(client, org):
    headers, org_id = org
    other = register(client, "idempotency-other@example.com")
    other_id = first_org_id(client, other)
    approve_reports(client, other, other_id)
    ids = []
    for credentials, tenant in [(headers, org_id), (other, other_id)]:
        result = client.post(f"/api/v1/orgs/{tenant}/reports/generate",
            headers={**credentials, "Idempotency-Key": "shared-key"}, json={"title": "Audit"})
        assert result.status_code == 202
        ids.append(result.json()["id"])
    assert ids[0] != ids[1]


def test_retention_removes_only_expired_terminal_reports(client, org, db_session, monkeypatch):
    _, org_id = org
    monkeypatch.setattr(settings, "REPORT_RETENTION_DAYS", 30)
    old = datetime.now(timezone.utc) - timedelta(days=31)
    rows = [Report(org_id=org_id, title=status.value, status=status, created_at=old)
        for status in (ReportStatus.completed, ReportStatus.failed, ReportStatus.pending, ReportStatus.running)]
    recent = Report(org_id=org_id, title="Recently completed", status=ReportStatus.completed,
        created_at=old, generated_at=datetime.now(timezone.utc))
    db_session.add_all([*rows, recent])
    db_session.commit()
    assert report_service.purge_expired_reports(db_session) == 2
    remaining = db_session.scalars(select(Report)).all()
    assert {row.title for row in remaining} == {"pending", "running", "Recently completed"}
    assert report_service.purge_expired_reports(db_session) == 0
