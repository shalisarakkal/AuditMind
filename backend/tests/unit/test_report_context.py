"""Byte-boundary, omission and no-provider-I/O regressions."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, settings
from app.services import claude_service, report_provider
from app.services.report_context import bounded_text, budget_context


@pytest.mark.parametrize('value,limit', [('short', 10), ('界😀é' * 20, 17), ('', 5), ('abc', 3)])
def test_text_prefix_is_utf8_safe_and_records_original_evidence(value, limit):
    text, metadata = bounded_text(value, limit)
    assert len(text.encode('utf-8')) <= limit
    assert value.startswith(text)
    if len(value.encode('utf-8')) > limit:
        assert metadata['original_sha256'] == hashlib.sha256(value.encode('utf-8')).hexdigest()
        assert metadata['original_bytes'] == len(value.encode('utf-8'))
        assert metadata['included_bytes'] == len(text.encode('utf-8'))
    else:
        assert metadata is None


def size(context):
    return len(json.dumps(context, ensure_ascii=False).encode('utf-8'))


def test_context_omissions_preserve_order_and_source_objects():
    context = {'total_findings': 30, 'sample_findings': [
        {'finding_id': str(i), 'description': '界' * 4000} for i in range(3)],
        'citations': [{'citation_id': 'source', 'content': 'complete evidence', 'excerpt_hash': 'unchanged'}]}
    original = deepcopy(context)
    result = budget_context(context, 15000, size)
    assert result == budget_context(context, 15000, size)
    assert context == original
    assert size(result) <= 15000
    assert [f['finding_id'] for f in result['sample_findings']] == ['0']
    assert result['input_budget']['omitted_finding_ids'] == ['1', '2']
    assert result['input_budget']['findings_not_sampled'] == 27
    assert result['citations'] == context['citations']


def test_citations_are_omitted_whole_not_modified():
    context = {'total_findings': 1, 'sample_findings': [{'finding_id': 'one', 'description': 'a' * 4000}],
               'citations': [{'citation_id': 'one', 'content': 'b' * 4000}, {'citation_id': 'two', 'content': 'c' * 4000}]}
    result = budget_context(context, 5000, size)
    assert size(result) <= 5000
    assert result['input_budget']['omitted_citation_ids'] == ['one', 'two']
    assert result['sample_findings'] == context['sample_findings']


def test_last_finding_can_be_omitted_but_instructions_never_truncated():
    context = {'total_findings': 1, 'sample_findings': [{'finding_id': 'one', 'description': 'a' * 5000}], 'citations': []}
    assert budget_context(context, 1200, size)['sample_findings'] == []
    with pytest.raises(ValueError, match='instructions and metadata exceed'):
        budget_context(context, 10, size)


class Answer(BaseModel):
    value: int


@pytest.mark.parametrize('prompt', ['hello', '界😀' * 200])
def test_final_request_guard_includes_schema_and_system_before_client_or_reservation(monkeypatch, prompt):
    client, reserve = Mock(), Mock()
    monkeypatch.setattr(claude_service, 'get_client', client)
    monkeypatch.setattr('app.services.ai_accounting.reserve', reserve)
    actual = claude_service.structured_input_bytes(prompt, Answer)
    with pytest.raises(ValueError, match='byte budget'):
        claude_service.ask_claude_structured(prompt, Answer, org_id=uuid4(), usage_bind=Mock(), max_input_bytes=actual - 1)
    client.assert_not_called()
    reserve.assert_not_called()


def test_exact_request_boundary_is_allowed(monkeypatch):
    monkeypatch.setattr(settings, 'REPORT_AI_PROVIDER', 'anthropic')
    create = Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text', text='{"value": 1}')],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    monkeypatch.setattr(claude_service, 'get_client', lambda: SimpleNamespace(messages=SimpleNamespace(create=create)))
    result = claude_service.ask_claude_structured('hello', Answer,
        max_input_bytes=claude_service.structured_input_bytes('hello', Answer))
    assert result.value == 1
    create.assert_called_once()


@pytest.mark.parametrize('provider', ['anthropic', 'openrouter'])
def test_budget_changes_invalidate_target(monkeypatch, provider):
    monkeypatch.setattr(settings, 'REPORT_AI_PROVIDER', provider)
    original = report_provider.target('test-version')
    monkeypatch.setattr(settings, 'REPORT_AI_MAX_INPUT_BYTES', 32768)
    assert report_provider.target('test-version') != original


@pytest.mark.parametrize('field,value', [('REPORT_AI_MAX_INPUT_BYTES', 100), ('REPORT_AI_MAX_INPUT_BYTES', 999999),
    ('REPORT_AI_FINDING_TEXT_BYTES', 0), ('REPORT_AI_FINDING_TEXT_BYTES', 999999)])
def test_budget_configuration_rejects_unsafe_limits(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SECRET_KEY='test-only-' * 8, **{field: value})
