"""New-contract generation and mixed-version APIs on real PostgreSQL, mocked AI."""
from copy import deepcopy
from uuid import UUID, uuid4
import json
from datetime import datetime, timedelta, timezone
import pytest
from app.core.config import settings
from app.models.enums import Domain, ReportStatus
from app.models.report import Report
from app.models.finding import Finding
from app.schemas.evidence_assessment import EvidenceAssessment
from app.services import report_ai_service, knowledge_service
from app.services import evidence_policy
from app.worker.runner import drain
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, approve_reports

pytestmark = requires_db


def body():
    return dict(title='Synthetic partial', executive_summary='Evidence limited', resilience_summary='Not a certification',
        domains=[dict(domain=d.value,evidence_status='insufficient',evidence_reason='No operational observations',
            evidence_finding_ids=[],citation_ids=[],score=None,tier=None,justification='Unobserved',strengths=[],weaknesses=[]) for d in Domain],remediations=[])


@pytest.mark.parametrize('case', ['partial', 'forged-sufficient', 'stale-target'])
def test_worker_new_contract_and_fail_closed(client, db_session, monkeypatch, case):
    monkeypatch.setattr(settings,'REPORT_EVIDENCE_V3_ENABLED',True)
    monkeypatch.setattr(settings,'REPORT_EVIDENCE_QUALIFICATIONS_FILE','')
    monkeypatch.setattr(settings,'REPORT_AI_PROVIDER','anthropic')
    monkeypatch.setattr(settings,'ANTHROPIC_API_KEY','mock-only')
    monkeypatch.setattr(report_ai_service,'retrieve_standards_for_findings',lambda *a,**kw: [])
    payload = body()
    if case == 'forged-sufficient':
        payload['domains'][0].update(evidence_status='sufficient',score=60,tier='medium',citation_ids=['invented'])
    def complete(*a, **kw):
        assert kw['response_model'] is EvidenceAssessment
        assert 'qualified_domains' in a[0]
        return EvidenceAssessment(**payload)
    monkeypatch.setattr(report_ai_service,'ask_claude_structured',complete)
    headers=register(client,'evidence-new@example.com'); org=first_org_id(client,headers)
    approve_reports(client,headers,org)
    base=f'/api/v1/orgs/{org}/reports'
    queued=client.post(base+'/generate',headers=headers,json={'title':'Synthetic evidence-aware'})
    assert queued.status_code==202
    if case == 'stale-target':
        monkeypatch.setattr(settings,'REPORT_EVIDENCE_V3_ENABLED',False)
    assert drain(db_session) == 1
    result=client.get(base+'/'+queued.json()['id'],headers=headers).json()
    if case != 'partial':
        assert result['status']=='failed'
        return
    assert result['status']=='completed' and result['overall_score'] is None
    assert result['assessment_status']=='partial'
    assert result['data']['provenance']['schema_version']==3
    assert result['data']['provenance']['rule_based']['overall_score']==100
    for kind in ('html','pdf'):
        exported=client.get(base+'/'+result['id']+'/download',params={'format':kind},headers=headers)
        assert exported.status_code==200
        if kind=='html':
            assert 'Partial AI assessment' in exported.text and 'None/100' not in exported.text
        else:
            assert exported.content.startswith(b'%PDF')
    raw=db_session.get(Report,UUID(result['id'])); before=deepcopy(raw.data)
    raw.data={**raw.data,'overall_score':59,'overall_tier':'high','assessment_status':'complete'}
    db_session.commit()
    complete_id=str(raw.id)
    other=Report(org_id=UUID(org),title='Partial second',status=ReportStatus.completed,data=before)
    db_session.add(other); db_session.commit()
    for order in ('asc','desc'):
        rows=client.get(base,headers=headers,params={'sort':'score','order':order}).json()['items']
        assert rows[0]['id']==complete_id and rows[-1]['overall_score'] is None
    filtered=client.get(base,headers=headers,params={'assessment_status':'partial'}).json()
    assert filtered['total']==1 and filtered['items'][0]['id']==str(other.id)
    assert client.get(base,headers=headers,params={'score':'59'}).json()['total']==1
    foreign=register(client,'evidence-foreign@example.com')
    assert client.get(base+'/'+result['id'],headers=foreign).status_code==403


def test_complete_reviewed_capture_persists_server_aggregation(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings,'REPORT_EVIDENCE_V3_ENABLED',True)
    monkeypatch.setattr(settings,'REPORT_EVIDENCE_QUALIFICATIONS_FILE','')
    monkeypatch.setattr(settings,'REPORT_AI_PROVIDER','anthropic')
    monkeypatch.setattr(settings,'ANTHROPIC_API_KEY','mock-only')
    monkeypatch.setattr(report_ai_service,'retrieve_standards_for_findings',lambda *a,**kw: [])
    headers=register(client,'evidence-complete@example.com'); org=first_org_id(client,headers)
    db_session.add_all([Finding(org_id=UUID(org),domain=d,severity='high',category='Synthetic operational test',
        description='Synthetic reviewed operational observation, not a real security test') for d in Domain])
    db_session.commit()
    context=report_ai_service._gather_org_audit_context(db_session,UUID(org))
    now=datetime.now(timezone.utc)
    records=[]
    ids={}
    for finding in context['sample_findings']:
        ids[finding['domain']]=finding['finding_id']
        records.extend(dict(domain=finding['domain'],objective=o,source_type='finding',source_id=finding['finding_id'],
            source_sha256=evidence_policy.source_hash(finding),observed_at=(now-timedelta(days=1)).isoformat(),
            scope='Synthetic local fixture',operational_review=True) for o in evidence_policy.PROFILES[finding['domain']])
    path=tmp_path/'qualifications.json'
    path.write_text(json.dumps(dict(policy_version=evidence_policy.POLICY_VERSION,org_id=org,reviewer='Synthetic reviewer',
        reviewed_at=now.isoformat(),expires_at=(now+timedelta(days=1)).isoformat(),scope='Synthetic local fixture',observations=records)),encoding='utf-8')
    monkeypatch.setattr(settings,'REPORT_EVIDENCE_QUALIFICATIONS_FILE',str(path))
    payload=body()
    for domain in payload['domains']:
        domain.update(evidence_status='sufficient',score=0,tier='critical',evidence_finding_ids=[ids[domain['domain']]])
    monkeypatch.setattr(report_ai_service,'ask_claude_structured',lambda *a,**kw: EvidenceAssessment(**payload))
    approve_reports(client,headers,org)
    base=f'/api/v1/orgs/{org}/reports'
    queued=client.post(base+'/generate',headers=headers,json={'title':'Reviewed synthetic assessment'})
    assert queued.status_code==202
    assert drain(db_session)==1
    result=client.get(base+'/'+queued.json()['id'],headers=headers).json()
    assert result['status']=='completed' and result['overall_score']==0
    assert result['assessment_status']=='complete'
    assert result['data']['overall_tier']=='critical'
    assert len(result['data']['provenance']['evidence_qualification']['qualified_domains'])==7
    assert result['data']['provenance']['rule_based']['overall_score'] != 0
