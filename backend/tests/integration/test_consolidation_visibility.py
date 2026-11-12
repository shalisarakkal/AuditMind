"""Simulated publication only: public writer remains disabled throughout."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.finding import Finding
from app.models.finding_consolidation import (FindingConsolidation, FindingConsolidationDecision,
    FindingConsolidationMember)
from app.models.list_revision import OrganizationListRevision
from app.models.evidence_evaluation import OrganizationEvidenceRevision
from app.models.dashboard_snapshot import DashboardSnapshot
from app.models.session import PlatformSetting
from app.services import consolidation_visibility as visibility, dashboard_evidence, dashboard_snapshots, status_scoring
from app.services.scoring_service import count_org_findings
from app.services.consolidation_transactions import publish, _stage_metadata
from tests.conftest import requires_db
from tests.integration.test_finding_consolidation_foundation import native
from tests.integration.test_consolidation_transactions import request as metadata_request

pytestmark = requires_db


def apply(db, n):
    who, payload = metadata_request(db,n)
    result = visibility._stage_with_visibility(db,uuid.UUID(n['org']),who,payload)
    return who,payload,result


def total(db, org):
    return sum(sum(values.values()) for values in count_org_findings(db,org).values())


def undo_fixture(db, org, who, result):
    root = db.get(FindingConsolidation,uuid.UUID(result['consolidation_id']))
    root.version,root.state = 2,'undone'
    db.execute(delete(FindingConsolidationMember).where(FindingConsolidationMember.org_id==org,
        FindingConsolidationMember.consolidation_id==root.id))
    db.add(FindingConsolidationDecision(org_id=org,consolidation_id=root.id,version=2,state='undone',
        request_id=uuid.uuid4(),request_hash='b'*64,rationale='Synthetic undo admission',context={},
        actor_id=who,actor_label='Synthetic reviewer'))
    db.flush()
    visibility._clear_after_undo(db,org,root.id,2)


def test_one_visible_finding_everywhere_but_both_sources_and_workflows_retained(client,db_session,native):
    n=native;org=uuid.UUID(n['org'])
    assert client.get(n['base']+'/findings',headers=n['headers']).json()['total']==2
    sources={row.id:(row.scan_id,row.asset_id,row.workflow_version,row.workflow_status)
        for row in db_session.scalars(select(Finding).where(Finding.org_id==org))}
    before=db_session.scalar(select(OrganizationListRevision.finding_revision).where(OrganizationListRevision.org_id==org))
    who,payload,result=apply(db_session,n)
    assert total(db_session,org)==1
    with Session(db_session.get_bind()) as outsider:
        assert total(outsider,org)==2
        assert visibility.revision(outsider,org)==0
    db_session.commit()
    assert visibility.revision(db_session,org)==1
    assert db_session.scalar(select(OrganizationListRevision.finding_revision).where(OrganizationListRevision.org_id==org))>before
    body=client.get(n['base']+'/findings',headers=n['headers']).json()
    assert body['total']==1 and len(body['items'])==1
    assert str(n['source'].finding_id)==body['items'][0]['id']
    assert client.get(n['base']+'/findings?finding_id='+str(n['target'].finding_id),headers=n['headers']).json()['total']==0
    assert {row.id:(row.scan_id,row.asset_id,row.workflow_version,row.workflow_status)
        for row in db_session.scalars(select(Finding).where(Finding.org_id==org))}==sources
    assert db_session.scalar(select(func.count()).select_from(Finding).where(Finding.org_id==org))==2
    from app.api.routes.dashboard import capture_inventory
    captured=capture_inventory(org,db_session)
    assert sum(sum(v.values()) for v in captured['counts'].values())==1
    assert len(captured['top_findings'])==1 and captured['consolidation_revision']==1
    _,policy=status_scoring.apply_policy(db_session,org,count_org_findings(db_session,org),capture_basis=True)
    assert policy['recorded_findings']==2 and policy['active_findings']==1 and policy['consolidated_alias_findings']==1
    assert len(policy['consolidation_basis'])==1 and policy['excluded_findings']==0


def test_invalidation_failure_rolls_back_metadata_visibility_and_all_revisions(db_session,native,monkeypatch):
    org=uuid.UUID(native['org'])
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY,value={'enabled':True,'version':1}))
    saved=DashboardSnapshot(org_id=org,status='completed',requested_at=datetime.now(timezone.utc),payload={'synthetic_before':True})
    db_session.add(saved);db_session.commit()
    saved_id=saved.id
    who,payload=metadata_request(db_session,native)
    before=db_session.scalar(select(OrganizationListRevision.finding_revision).where(OrganizationListRevision.org_id==org))
    original=visibility._invalidate
    evidence_before=db_session.scalar(select(OrganizationEvidenceRevision.revision).where(OrganizationEvidenceRevision.org_id==org))
    def fail(db,org_id):
        original(db,org_id)
        raise RuntimeError('Synthetic consumer invalidation failure')
    monkeypatch.setattr(visibility,'_invalidate',fail)
    with pytest.raises(RuntimeError,match='Synthetic consumer'):
        visibility._stage_with_visibility(db_session,org,who,payload)
    assert total(db_session,org)==2 and visibility.revision(db_session,org)==0
    assert db_session.scalar(select(func.count()).select_from(FindingConsolidation))==0
    assert db_session.scalar(select(OrganizationListRevision.finding_revision).where(OrganizationListRevision.org_id==org))==before
    assert db_session.scalar(select(OrganizationEvidenceRevision.revision).where(OrganizationEvidenceRevision.org_id==org))==evidence_before
    saved=db_session.get(DashboardSnapshot,saved_id,populate_existing=True)
    assert saved.status=='completed' and saved.payload=={'synthetic_before':True}


def test_undo_retains_history_changes_evidence_scope_and_retry_never_rehides(db_session,native):
    org=uuid.UUID(native['org'])
    original_scope=dashboard_evidence.inventory_scope(db_session,org)
    original_source=dashboard_evidence.finding_source(db_session,org,native['source'].finding_id)[1]
    who,payload,result=apply(db_session,native);db_session.commit()
    first_scope=dashboard_evidence.inventory_scope(db_session,org)
    assert original_scope!=first_scope
    undo_fixture(db_session,org,who,result);db_session.commit()
    assert total(db_session,org)==2 and visibility.revision(db_session,org)==2
    assert all(row.consolidation_id is None and row.consolidation_alias_id is None and row.consolidation_history_id
        for row in db_session.scalars(select(Finding)))
    assert dashboard_evidence.inventory_scope(db_session,org) not in (original_scope,first_scope)
    assert dashboard_evidence.finding_source(db_session,org,native['source'].finding_id)[1]!=original_source
    replay=visibility._stage_with_visibility(db_session,org,who,payload)
    assert replay['replayed'] and total(db_session,org)==2 and visibility.revision(db_session,org)==2


def test_metadata_only_receipt_cannot_be_upgraded_via_retry(db_session,native):
    who,payload=metadata_request(db_session,native);org=uuid.UUID(native['org'])
    _stage_metadata(db_session,org,who,payload);db_session.commit()
    with pytest.raises(HTTPException) as caught:
        visibility._stage_with_visibility(db_session,org,who,payload)
    assert caught.value.status_code==409
    assert total(db_session,org)==2 and visibility.revision(db_session,org)==0


def test_old_physical_only_proof_cannot_exclude_a_group_and_alias_only_scope_is_neutral(db_session,native):
    org=uuid.UUID(native['org'])
    apply(db_session,native);db_session.commit()
    canonical=db_session.get(Finding,native['source'].finding_id)
    canonical.workflow_status='resolved';canonical.risk_verification_state='approved'
    canonical.risk_verified_workflow_version=canonical.workflow_version
    canonical.risk_verified_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    canonical.risk_verification_expires_at=datetime.now(timezone.utc)+timedelta(days=1)
    canonical.risk_verified_observation_count=1;canonical.risk_verification_source_kind='reference'
    db_session.flush()
    _,policy=status_scoring.apply_policy(db_session,org,count_org_findings(db_session,org))
    assert policy['excluded_findings']==0 and policy['current_risk_findings']==1
    _,alias_scope=status_scoring.apply_policy(db_session,org,{},filters=[Finding.id==native['target'].finding_id])
    assert alias_scope['not_assessed'] and alias_scope['all_consolidated_aliases']


def test_saved_dashboard_payload_is_never_served_across_visibility_publication(client,db_session,native):
    org=uuid.UUID(native['org']);path=native['base']+'/dashboard'
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY,value={'enabled':True,'version':1}))
    db_session.commit()
    assert client.get(path,headers=native['headers']).status_code==202
    row=db_session.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id==org))
    dashboard_snapshots.process(db_session,row.id)
    old=client.get(path,headers=native['headers']);assert old.status_code==200,old.text
    assert sum(old.json()['findings_by_severity'].values())==2
    apply(db_session,native);db_session.commit()
    assert client.get(path,headers=native['headers']).status_code==202
    dashboard_snapshots.process(db_session,row.id)
    fresh=client.get(path,headers=native['headers']);assert fresh.status_code==200,fresh.text
    assert sum(fresh.json()['findings_by_severity'].values())==1


def test_in_flight_dashboard_capture_cannot_overwrite_visibility_invalidation(client,db_session,native,monkeypatch):
    from app.api.routes import dashboard
    org=uuid.UUID(native['org']);path=native['base']+'/dashboard'
    who,payload=metadata_request(db_session,native)
    db_session.add(PlatformSetting(key=dashboard_snapshots.SETTINGS_KEY,value={'enabled':True,'version':1}))
    db_session.commit()
    client.get(path,headers=native['headers'])
    row=db_session.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id==org))
    original=dashboard.capture_inventory
    def capture_then_publish(org_id,snapshot):
        captured=original(org_id,snapshot)
        with Session(db_session.get_bind()) as other:
            visibility._stage_with_visibility(other,org,who,payload)
            other.commit()
        return captured
    monkeypatch.setattr(dashboard,'capture_inventory',capture_then_publish)
    dashboard_snapshots.process(db_session,row.id)
    db_session.expire_all()
    current=db_session.get(DashboardSnapshot,row.id)
    assert current.payload is None and current.status=='pending'
    assert client.get(path,headers=native['headers']).status_code==202
    monkeypatch.setattr(dashboard,'capture_inventory',original)
    dashboard_snapshots.process(db_session,current.id)
    assert sum(client.get(path,headers=native['headers']).json()['findings_by_severity'].values())==1


def test_new_reports_use_visible_canonical_and_old_snapshots_stay_immutable(db_session,native,monkeypatch):
    import copy
    from app.services import report_service,report_ai_service
    from app.models.report import Report
    org=uuid.UUID(native['org'])
    old=report_service.create_rule_based_test_report(db_session,org,'Before simulated consolidation')
    original=copy.deepcopy(old.data)
    assert old.data['total_findings']==2
    apply(db_session,native);db_session.commit()
    fresh=report_service.create_rule_based_test_report(db_session,org,'After simulated consolidation')
    assert fresh.data['total_findings']==1
    assert fresh.data['provenance']['status_scoring']['consolidated_alias_findings']==1
    assert db_session.get(Report,old.id,populate_existing=True).data==original
    monkeypatch.setattr(report_ai_service,'retrieve_standards_for_findings',lambda *args,**kwargs:[])
    context=report_ai_service._read_org_audit_context(db_session,org)
    assert context['total_findings']==1
    assert all(row['finding_id']!=str(native['target'].finding_id) for row in context['sample_findings'])


def test_public_publication_gate_stays_disabled(db_session,native):
    who,payload=metadata_request(db_session,native)
    with pytest.raises(HTTPException):publish(db_session,uuid.UUID(native['org']),who,payload)
    assert total(db_session,uuid.UUID(native['org']))==2


def test_private_undo_refuses_pending_orm_work_without_flushing(db_session,native):
    org=uuid.UUID(native['org'])
    finding=db_session.get(Finding,native['source'].finding_id)
    previous=finding.description
    finding.description='Synthetic unsaved caller edit'
    with pytest.raises(HTTPException) as caught:
        visibility._clear_after_undo(db_session,org,uuid.uuid4(),2)
    assert caught.value.status_code==409 and finding in db_session.dirty
    with Session(db_session.get_bind()) as other:
        assert other.scalar(select(Finding.description).where(Finding.id==finding.id))==previous
