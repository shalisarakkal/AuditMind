"""No-network OpenRouter transport, admission, retry and boundary regressions."""
import copy
import json
import uuid
from unittest.mock import Mock

import httpx
import pytest

from app.core.config import settings
from app.services import claude_service, report_provider as provider, ai_accounting
from app.services.knowledge_service import report_target, KnowledgeError


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setattr(settings, "REPORT_AI_PROVIDER", "openrouter")
    monkeypatch.setattr(settings, "OPENROUTER_INFERENCE_ENABLED", True)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "secret-mocked-key")
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "anthropic/claude-test-version")
    monkeypatch.setattr(settings, "OPENROUTER_INPUT_USD_PER_MILLION", 3.0)
    monkeypatch.setattr(settings, "OPENROUTER_OUTPUT_USD_PER_MILLION", 15.0)
    monkeypatch.setattr(claude_service.time, "sleep", Mock())
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", Mock(side_effect=AssertionError("Network forbidden")))
    return dict(model=settings.OPENROUTER_MODEL, provider="Anthropic", choices=[
        {"finish_reason": "stop", "message": {"role": "assistant", "content": '{"count":1}'}}],
        usage={"prompt_tokens": 20, "completion_tokens": 10, "cost": 0.0042})


@pytest.fixture
def transport(router, monkeypatch):
    original = httpx.Client
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=copy.deepcopy(router))
    factory = Mock(side_effect=lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(provider.httpx, "Client", factory)
    return factory, seen


def complete():
    return provider.complete(model=settings.OPENROUTER_MODEL, max_tokens=100, system="System",
                             messages=[{"role": "user", "content": "Synthetic evidence"}])


def test_fixed_endpoint_routing_no_fallback_and_actual_cost(router, transport):
    response = complete()
    factory, seen = transport
    factory.assert_called_once_with(timeout=settings.CLAUDE_TIMEOUT_SECONDS, follow_redirects=False, trust_env=False)
    assert str(seen[0].url) == provider.ENDPOINT
    assert seen[0].headers['authorization']=='Bearer secret-mocked-key'
    assert 'x-api-key' not in seen[0].headers
    body = json.loads(seen[0].content)
    assert body["model"] == settings.OPENROUTER_MODEL and body["stream"] is False
    assert body["provider"] == {**provider.ROUTING, "max_price": {"prompt": 3.0, "completion": 15.0}}
    assert "models" not in body and "plugins" not in body
    assert response.usage.actual_cost_usd == 0.0042
    assert response.content[0].text == '{"count":1}'


@pytest.mark.parametrize("field,value", [
    ("OPENROUTER_INFERENCE_ENABLED", False), ("OPENROUTER_API_KEY", ""),
    ("REPORT_AI_PROVIDER", "anthropic"),
    ("OPENROUTER_MODEL", "openrouter/auto"), ("OPENROUTER_MODEL", "anthropic/claude-test:free"),
    ("OPENROUTER_INPUT_USD_PER_MILLION", None), ("OPENROUTER_OUTPUT_USD_PER_MILLION", float('nan')),
])
def test_disabled_or_incomplete_configuration_never_constructs_client(router, transport, monkeypatch, field, value):
    monkeypatch.setattr(settings, field, value)
    with pytest.raises(ValueError):
        complete()
    transport[0].assert_not_called()


@pytest.mark.parametrize("change", ["model", "provider", "missing-usage", "missing-cost", "negative-cost", "nan-cost",
    "bool-cost", "bool-tokens", "negative-tokens", "length", "tool_calls", "empty", "extra-choice", "error",
    "wrong-role", "bad-usage", "bad-choices", "bad-message"])
def test_bad_envelopes_fail_without_repair_or_provider_details(router, transport, change):
    if change == "model": router['model'] = 'other-model'
    elif change == "provider": router['provider'] = 'OtherProvider'
    elif change == "missing-usage": del router['usage']
    elif change == "missing-cost": del router['usage']['cost']
    elif change == "negative-cost": router['usage']['cost'] = -1
    elif change == "nan-cost": router['usage']['cost'] = float('nan')
    elif change == "bool-cost": router['usage']['cost'] = True
    elif change == "bool-tokens": router['usage']['prompt_tokens'] = True
    elif change == "negative-tokens": router['usage']['completion_tokens'] = -1
    elif change in ('length', 'tool_calls'): router['choices'][0]['finish_reason'] = change
    elif change == "empty": router['choices'][0]['message']['content'] = ''
    elif change == "extra-choice": router['choices'].append(copy.deepcopy(router['choices'][0]))
    elif change == "wrong-role": router['choices'][0]['message']['role']='tool'
    elif change == "bad-usage": router['usage']=None
    elif change == "bad-choices": router['choices']=[None]
    elif change == "bad-message": router['choices'][0]['message']=None
    else: router['error'] = {'message': 'secret-private-provider-data'}
    with pytest.raises(provider.OpenRouterError) as failure:
        complete()
    assert failure.value.status_code == 502
    assert 'secret' not in str(failure.value)


@pytest.mark.parametrize("status,attempts", [(301,1),(401,1),(402,1),(403,1),(429,3),(500,3),(503,3),(504,3),(529,3)])
def test_http_errors_bounded_no_redirects_or_secret_logs(router, monkeypatch, status, attempts, caplog):
    original = httpx.Client
    handler = Mock(return_value=httpx.Response(status, json={'error': 'secret-private-provider-data'},
        headers={'Location':'https://unapproved.invalid'}))
    monkeypatch.setattr(provider.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(claude_service.ClaudeOperationalError) as failure:
        claude_service.ask_claude('secret-prompt')
    assert handler.call_count == attempts
    assert 'secret' not in str(failure.value) and 'secret' not in caplog.text


@pytest.mark.parametrize('error,status', [(httpx.ReadTimeout,504),(httpx.ConnectError,503)])
def test_transport_failure_mapping(router, monkeypatch, error, status):
    original=httpx.Client
    handler=Mock(side_effect=error('private'))
    monkeypatch.setattr(provider.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(claude_service.ClaudeOperationalError) as failure:
        claude_service.ask_claude('Evidence')
    assert failure.value.status_code == status and handler.call_count == 3


def test_actual_cost_and_distinct_route_are_recorded(router, transport, monkeypatch):
    reserve=Mock(return_value=uuid.uuid4()); finish=Mock()
    monkeypatch.setattr(ai_accounting,'reserve',reserve); monkeypatch.setattr(ai_accounting,'finish',finish)
    claude_service.ask_claude('Evidence',org_id=uuid.uuid4(),usage_bind=object())
    assert reserve.call_args.args[2]=='openrouter:'+settings.OPENROUTER_MODEL
    assert finish.call_args.kwargs['cost_usd']==0.0042 and finish.call_args.kwargs['success'] is True


def test_target_changes_for_route_model_and_price_policy(router, monkeypatch):
    initial=report_target()
    assert initial.startswith('openrouter:') and 'anthropic-only:zdr' in initial
    monkeypatch.setattr(settings,'OPENROUTER_INPUT_USD_PER_MILLION',4.0)
    assert report_target()!=initial
    monkeypatch.setattr(settings,'REPORT_AI_PROVIDER','anthropic')
    assert report_target().startswith('anthropic:') and report_target()!=initial


def test_denied_authorization_or_configuration_change_prevents_admission(router, transport, monkeypatch):
    reserve=Mock(); monkeypatch.setattr(ai_accounting,'reserve',reserve)
    def deny(): raise KnowledgeError('Consent revoked')
    with pytest.raises(KnowledgeError):
        claude_service.ask_claude('Evidence',org_id=uuid.uuid4(),usage_bind=object(),before_attempt=deny)
    def change(): monkeypatch.setattr(settings,'OPENROUTER_MODEL','anthropic/claude-other')
    with pytest.raises(claude_service.ClaudeOperationalError,match='configuration changed'):
        claude_service.ask_claude('Evidence',org_id=uuid.uuid4(),usage_bind=object(),before_attempt=change)
    reserve.assert_not_called(); transport[0].assert_not_called()


def test_revocation_stops_second_attempt_and_retains_unknown_reservation(router, monkeypatch):
    original=httpx.Client
    handler=Mock(return_value=httpx.Response(503))
    monkeypatch.setattr(provider.httpx,'Client',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    reserve=Mock(return_value=uuid.uuid4()); finish=Mock()
    monkeypatch.setattr(ai_accounting,'reserve',reserve); monkeypatch.setattr(ai_accounting,'finish',finish)
    authorize=Mock(side_effect=[None,KnowledgeError('revoked')])
    with pytest.raises(KnowledgeError):
        claude_service.ask_claude('Evidence',org_id=uuid.uuid4(),usage_bind=object(),before_attempt=authorize)
    assert handler.call_count==reserve.call_count==finish.call_count==1
    assert finish.call_args.kwargs=={}


def test_structured_response_still_uses_schema_validation(router, transport):
    from pydantic import BaseModel
    class Result(BaseModel):
        count:int
    assert claude_service.ask_claude_structured('Evidence',Result).count==1
    router['choices'][0]['message']['content']='{"count":"private"}'
    with pytest.raises(ValueError,match='Invalid structured response'):
        claude_service.ask_claude_structured('Evidence',Result)


@pytest.mark.parametrize('body',[b'not-json',b'[]',b'null'])
def test_malformed_or_non_object_envelope_is_sanitized(router,monkeypatch,body):
    original=httpx.Client
    monkeypatch.setattr(provider.httpx,'Client',lambda **kw:original(
        transport=httpx.MockTransport(lambda _:httpx.Response(200,content=body)),**kw))
    with pytest.raises(provider.OpenRouterError) as failure:
        complete()
    assert failure.value.status_code==502


@pytest.mark.parametrize('data',[None,{'_processing_target':'openrouter:synthetic'},{'overall_score':60}])
def test_internal_job_marker_is_not_exposed_as_a_report_snapshot(data):
    from datetime import datetime,timezone
    from app.schemas.report import ReportDetail
    report=ReportDetail(id=uuid.uuid4(),org_id=uuid.uuid4(),title='Synthetic',status='pending',
        created_at=datetime.now(timezone.utc),data=data)
    assert report.data==(None if data is None or '_processing_target' in data else data)


def test_route_is_disabled_by_default():
    from app.core.config import Settings
    assert Settings.model_fields['OPENROUTER_INFERENCE_ENABLED'].default is False
    assert Settings.model_fields['REPORT_AI_PROVIDER'].default=='anthropic'
