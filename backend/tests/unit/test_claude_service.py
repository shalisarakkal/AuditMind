"""Exercise client creation and provider handling without external requests."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from anthropic import APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel

from app.services import claude_service as service


@pytest.fixture
def provider(monkeypatch):
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Assessment")],
        usage=SimpleNamespace(input_tokens=20, output_tokens=10),
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr(service, "Anthropic", factory)
    monkeypatch.setattr(service, "_client", None)
    monkeypatch.setattr(service.settings, "ANTHROPIC_API_KEY", "unit-test-key")
    monkeypatch.setattr(service.settings, "CLAUDE_TIMEOUT_SECONDS", 7.0)
    monkeypatch.setattr(service, "_claude_call_stats", {
        "calls_total": 0, "calls_successful": 0, "calls_failed": 0,
        "total_tokens_input": 0, "total_tokens_output": 0, "estimated_cost_usd": 0.0,
        "errors_by_type": {}, "last_error_at": None,
    })
    monkeypatch.setattr(service.time, "sleep", Mock())
    return client, factory


def test_lazy_client_is_shared_and_sdk_retries_do_not_multiply_attempts(provider):
    client, factory = provider
    with ThreadPoolExecutor(max_workers=4) as pool:
        clients = list(pool.map(lambda _: service.get_client(), range(8)))
    assert all(item is client for item in clients)
    factory.assert_called_once_with(api_key="unit-test-key", timeout=7.0, max_retries=0)


def test_missing_credentials_refuses_cached_client(provider, monkeypatch):
    service.get_client()
    monkeypatch.setattr(service.settings, "ANTHROPIC_API_KEY", "")
    with pytest.raises(service.ClaudeOperationalError) as failure:
        service.get_client()
    assert failure.value.status_code == 503
    provider[0].messages.create.assert_not_called()


def test_actual_service_path_initializes_client_and_records_unscoped_usage(provider):
    assert service.ask_claude("Evidence") == "Assessment"
    assert provider[0].messages.create.call_args.kwargs["max_tokens"] == 2048
    stats = service.get_call_stats()
    assert stats["calls_total"] == stats["calls_successful"] == 1
    assert stats["calls_failed"] == 0
    assert stats["total_tokens_input"] == 20 and stats["total_tokens_output"] == 10


@pytest.mark.parametrize("kind,status,attempts", [
    ("timeout", 504, 3), ("connection", 503, 3), (401, 503, 1), (429, 503, 3), (500, 502, 1),
])
def test_failures_are_bounded_mapped_and_counted_once(provider, kind, status, attempts, caplog):
    request = httpx.Request("POST", "https://provider.invalid/messages")
    if kind == "timeout":
        error = APITimeoutError(request=request)
    elif kind == "connection":
        error = APIConnectionError(message="private-provider-evidence", request=request)
    else:
        error = APIStatusError("private-provider-evidence", response=httpx.Response(kind, request=request), body=None)
    provider[0].messages.create.side_effect = error
    with pytest.raises(service.ClaudeOperationalError) as failure:
        service.ask_claude("private-prompt")
    assert failure.value.status_code == status
    assert provider[0].messages.create.call_count == attempts
    assert service.get_call_stats()["calls_total"] == attempts
    assert service.get_call_stats()["calls_failed"] == attempts
    assert "private-provider-evidence" not in caplog.text
    assert "private-prompt" not in caplog.text


def test_transient_failure_then_success_is_not_double_counted(provider):
    success = provider[0].messages.create.return_value
    provider[0].messages.create.side_effect = [
        APITimeoutError(request=httpx.Request("POST", "https://provider.invalid")), success,
    ]
    assert service.ask_claude("Evidence") == "Assessment"
    stats = service.get_call_stats()
    assert (stats["calls_total"], stats["calls_failed"], stats["calls_successful"]) == (2, 1, 1)


def test_invalid_structured_output_does_not_log_evidence(provider, caplog):
    class Result(BaseModel):
        count: int
    provider[0].messages.create.return_value.content[0].text = '{"count":"private-evidence"}'
    with pytest.raises(ValueError, match="Invalid structured response") as failure:
        service.ask_claude_structured("Evidence", Result)
    assert "private-evidence" not in str(failure.value)
    assert "private-evidence" not in caplog.text


def test_revoked_authorization_stops_retry_before_second_request(provider):
    from app.services.knowledge_service import KnowledgeError

    provider[0].messages.create.side_effect = APITimeoutError(
        request=httpx.Request("POST", "https://provider.invalid"))
    authorize = Mock(side_effect=[None, KnowledgeError("Consent revoked")])
    with pytest.raises(KnowledgeError, match="Consent revoked"):
        service.ask_claude("Evidence", before_attempt=authorize)
    assert authorize.call_count == 2
    provider[0].messages.create.assert_called_once()
    assert service.get_call_stats()["calls_total"] == 1


def test_denied_initial_authorization_prevents_provider_request(provider):
    from app.services.knowledge_service import KnowledgeError

    authorize = Mock(side_effect=KnowledgeError("Consent denied"))
    with pytest.raises(KnowledgeError, match="Consent denied"):
        service.ask_claude("Evidence", before_attempt=authorize)
    provider[0].messages.create.assert_not_called()
    assert service.get_call_stats()["calls_total"] == 0


def test_structured_call_forwards_attempt_authorization(provider):
    class Result(BaseModel):
        count: int

    provider[0].messages.create.return_value.content[0].text = '{"count":1}'
    authorize = Mock()
    assert service.ask_claude_structured("Evidence", Result, before_attempt=authorize).count == 1
    authorize.assert_called_once()


def test_report_pipeline_rechecks_consent_after_provider_timeout(provider, monkeypatch):
    import uuid
    from app.services import ai_accounting, knowledge_service, report_ai_service

    approved = [True]
    def check(*args):
        if not approved[0]:
            raise knowledge_service.KnowledgeError("Consent revoked")

    def fail(**kwargs):
        approved[0] = False
        raise APITimeoutError(request=httpx.Request("POST", "https://provider.invalid"))

    context = dict(total_assets=0, assets_by_category={}, total_findings=0,
        findings_by_severity={}, sample_findings=[], citations=[], period_start=None, period_end=None)
    monkeypatch.setattr(report_ai_service, "_gather_org_audit_context", Mock(return_value=context))
    monkeypatch.setattr(knowledge_service, "require_report_consent", check)
    reserve = Mock(return_value=uuid.uuid4())
    monkeypatch.setattr(ai_accounting, "reserve", reserve)
    monkeypatch.setattr(ai_accounting, "finish", Mock())
    provider[0].messages.create.side_effect = fail
    db = Mock()
    with pytest.raises(knowledge_service.KnowledgeError, match="Consent revoked"):
        report_ai_service.generate_ai_audit_snapshot(db, uuid.uuid4(), "Synthetic audit")
    provider[0].messages.create.assert_called_once()
    reserve.assert_called_once()
    assert db.rollback.call_count == 2  # End both authorization read transactions.
