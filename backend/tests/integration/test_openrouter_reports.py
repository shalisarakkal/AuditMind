"""Real API/worker/database pipeline with an entirely mocked HTTP boundary."""
import copy
import json
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.ai_usage import AIUsage
from app.models.enums import Domain
from app.services import report_provider, knowledge_service
from app.worker.runner import drain
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, approve_reports

pytestmark=requires_db


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setattr(settings,'REPORT_AI_PROVIDER','openrouter')
    monkeypatch.setattr(settings,'OPENROUTER_INFERENCE_ENABLED',True)
    monkeypatch.setattr(settings,'OPENROUTER_API_KEY','mock-only')
    monkeypatch.setattr(settings,'OPENROUTER_MODEL','anthropic/claude-mocked-version')
    monkeypatch.setattr(settings,'OPENROUTER_INPUT_USD_PER_MILLION',3.0)
    monkeypatch.setattr(settings,'OPENROUTER_OUTPUT_USD_PER_MILLION',15.0)
    original=httpx.Client
    payload={'title':'Synthetic audit','executive_summary':'Synthetic evidence only',
        'resilience_summary':'No independently verified evidence supplied','overall_score':60,'overall_tier':'medium',
        'domains':[{'domain':d.value,'score':60,'tier':'medium','justification':'Synthetic evidence limits'} for d in Domain],
        'remediations':[]}
    state={'payload':payload,'requests':[], 'after_request':lambda:None}
    def respond(request):
        state['requests'].append(request)
        state['after_request']()
        return httpx.Response(200,json={'model':settings.OPENROUTER_MODEL,'provider':'Anthropic',
            'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(state['payload'])}}],
            'usage':{'prompt_tokens':50,'completion_tokens':100,'cost':0.00123}})
    monkeypatch.setattr(report_provider.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',lambda *a,**kw:pytest.fail('Network forbidden'))
    return state


def owner(client):
    headers=register(client,'openrouter-owner@example.com')
    org=first_org_id(client,headers)
    approve_reports(client,headers,org)
    return headers,org


@pytest.mark.parametrize('case',['valid','foreign-reference','invented-citation','invalid-schema','disabled','revoked','changed-before-run','changed-before-publication','cancelled','revoked-before-publication'])
def test_api_worker_validation_accounting_and_exports(client,db_session,router,monkeypatch,case):
    headers,org=owner(client)
    queued=client.post(f'/api/v1/orgs/{org}/reports/generate',headers=headers,json={'title':'OpenRouter synthetic audit'})
    assert queued.status_code==202
    if case=='foreign-reference':
        router['payload']['remediations']=[dict(title='Review',description='Synthetic action',priority='High',
            domain=Domain.identity_access.value,estimated_effort='Moderate',expected_impact='Improve control',
            confidence=.5,affected_finding_ids=[str(uuid4())],affected_asset_ids=[])]
    elif case=='invented-citation':router['payload']['domains'][0]['citation_ids']=['not-captured']
    elif case=='invalid-schema':router['payload']['overall_score']='not-a-number'
    elif case=='disabled':monkeypatch.setattr(settings,'OPENROUTER_INFERENCE_ENABLED',False)
    elif case=='revoked':
        from app.models.knowledge import KnowledgeConsent
        row=db_session.get(KnowledgeConsent,(UUID(org),'report'));row.granted=False;db_session.commit()
    elif case=='changed-before-run':
        monkeypatch.setattr(settings,'OPENROUTER_MODEL','anthropic/claude-changed-version')
        approve_reports(client,headers,org)  # new consent must not reroute an old job
    elif case=='changed-before-publication':
        router['after_request']=lambda:monkeypatch.setattr(settings,'OPENROUTER_INPUT_USD_PER_MILLION',4.0)
    elif case=='cancelled':
        from app.models.report import Report
        from datetime import datetime,timezone
        row=db_session.get(Report,UUID(queued.json()['id']))
        row.cancel_requested_at=datetime.now(timezone.utc);db_session.commit()
    elif case=='revoked-before-publication':
        from app.models.knowledge import KnowledgeConsent
        def revoke():
            row=db_session.get(KnowledgeConsent,(UUID(org),'report'))
            row.granted=False;db_session.commit()
        router['after_request']=revoke
    assert drain(db_session)==1
    endpoint=f"/api/v1/orgs/{org}/reports/{queued.json()['id']}"
    detail=client.get(endpoint,headers=headers).json()
    rows=db_session.scalars(select(AIUsage).where(AIUsage.org_id==UUID(org))).all()
    if case=='valid':
        assert detail['status']=='completed'
        provenance=detail['data']['provenance']
        assert provenance['provider']=='openrouter' and provenance['model']=='anthropic/claude-mocked-version'
        assert provenance['processing_target']==knowledge_service.report_target()
        assert provenance['provider_route']['routing']['allow_fallbacks'] is False
        assert len(rows)==1 and rows[0].cost_usd==0.00123 and rows[0].status=='succeeded'
        assert rows[0].model=='openrouter:anthropic/claude-mocked-version'
        assert client.get(endpoint+'/download?format=html',headers=headers).status_code==200
        pdf=client.get(endpoint+'/download?format=pdf',headers=headers)
        assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    else:
        assert detail['status']=='failed',detail
        assert detail['data'] is None
        assert client.get(endpoint+'/download?format=pdf',headers=headers).status_code==400
    if case in ('disabled','revoked','changed-before-run','cancelled'):
        assert router['requests']==[] and rows==[]
    else:
        assert len(router['requests'])==1
        assert len(rows)==1 and rows[0].status=='succeeded' and rows[0].cost_usd==0.00123


def test_direct_consent_is_not_reused_and_cross_org_denied(client,router,monkeypatch):
    monkeypatch.setattr(settings,'REPORT_AI_PROVIDER','anthropic')
    headers,org=owner(client)
    monkeypatch.setattr(settings,'REPORT_AI_PROVIDER','openrouter')
    base=f'/api/v1/orgs/{org}/reports/generate'
    assert client.post(base,headers=headers,json={'title':'New route'}).status_code==409
    approve_reports(client,headers,org)
    other=register(client,'other-openrouter@example.com')
    assert client.post(base,headers=other,json={'title':'Forbidden'}).status_code==403
    assert router['requests']==[]


def test_idempotency_binds_route_and_prevents_duplicate_requests(client,db_session,router,monkeypatch):
    headers,org=owner(client)
    headers={**headers,'Idempotency-Key':'mock-router-intent'}
    endpoint=f'/api/v1/orgs/{org}/reports/generate'
    first=client.post(endpoint,headers=headers,json={'title':'One report'})
    second=client.post(endpoint,headers=headers,json={'title':'One report'})
    assert first.status_code==second.status_code==202 and first.json()['id']==second.json()['id']
    assert drain(db_session)==1 and len(router['requests'])==1
    monkeypatch.setattr(settings,'OPENROUTER_OUTPUT_USD_PER_MILLION',16.0)
    approve_reports(client,headers,org)
    conflict=client.post(endpoint,headers=headers,json={'title':'One report'})
    assert conflict.status_code==409
    assert len(router['requests'])==1


@pytest.mark.parametrize('failure', ['timeout', 'rate-limit'])
@pytest.mark.parametrize('provider', ['openrouter', 'anthropic'])
def test_cancellation_during_provider_failure_stops_retry_and_reservation(
        client, db_session, router, monkeypatch, failure, provider):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from anthropic import APITimeoutError, RateLimitError
    from sqlalchemy.orm import Session
    from app.models.report import Report
    from app.services import report_service

    if provider == 'anthropic':
        monkeypatch.setattr(settings, 'REPORT_AI_PROVIDER', 'anthropic')
        monkeypatch.setattr(settings, 'ANTHROPIC_API_KEY', 'mock-only')
    headers, org = owner(client)
    queued = client.post(f'/api/v1/orgs/{org}/reports/generate', headers=headers,
        json={'title': 'Cancel during synthetic provider failure'})
    assert queued.status_code == 202
    report_id = UUID(queued.json()['id'])

    def cancel_then_fail():
        # Independent committed session reproduces a user cancellation while
        # the worker still has a stale running Report in its identity map.
        with Session(db_session.get_bind()) as cancellation_db:
            report_service.cancel_report_job(cancellation_db, report_id, UUID(org))
        if provider == 'anthropic':
            request = router['requests'][-1]
            if failure == 'timeout':
                raise APITimeoutError(request=request)
            raise RateLimitError('Synthetic rate limit',
                response=httpx.Response(429, request=request), body=None)
        if failure == 'timeout':
            raise httpx.ReadTimeout('Synthetic timeout', request=router['requests'][-1])
        raise report_provider.OpenRouterError(429)

    router['after_request'] = cancel_then_fail
    if provider == 'anthropic':
        def direct_request(**kwargs):
            router['requests'].append(httpx.Request('POST', 'https://api.anthropic.com/v1/messages'))
            cancel_then_fail()
        monkeypatch.setattr('app.services.claude_service.get_client',
            lambda: SimpleNamespace(messages=SimpleNamespace(create=direct_request)))
    backoff = Mock()
    monkeypatch.setattr('app.services.claude_service.time.sleep', backoff)
    assert drain(db_session) == 1
    detail = client.get(f'/api/v1/orgs/{org}/reports/{report_id}', headers=headers).json()
    assert detail['status'] == 'failed'
    assert detail['error_message'] == 'Generation cancelled by user'
    assert detail['data'] is None
    assert len(router['requests']) == 1
    backoff.assert_called_once()  # A genuine retryable error reached retry logic.
    rows = db_session.scalars(select(AIUsage).where(AIUsage.org_id == UUID(org))).all()
    assert len(rows) == 1 and rows[0].status == 'failed'
    db_session.expire_all()
    assert db_session.get(Report, report_id).cancel_requested_at is not None
