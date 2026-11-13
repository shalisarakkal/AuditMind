"""Real approved group evidence must cover both independent retained members."""
import copy
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.services import status_scoring
from app.services.scoring_service import count_org_findings
from tests.conftest import requires_db
from tests.integration.test_finding_consolidation_foundation import native
from tests.integration.test_consolidation_visibility import apply

pytestmark=requires_db


def submission(client,db,n):
    apply(db,n);db.commit()
    finding_id=str(n['source'].finding_id)
    path=n['base']+'/findings/'+finding_id
    response=client.patch(path+'/workflow',headers=n['headers'],json=dict(expected_version=0,
        status='resolved',rationale='Synthetic group retest',verification='Both members reviewed'))
    assert response.status_code==200,response.text
    instant=datetime.now(timezone.utc)
    response=client.post(path+'/risk-verification',headers=n['headers'],json=dict(expected_version=0,
        expected_workflow_version=1,source_reference='https://evidence.example/group',
        observed_at=(instant-timedelta(hours=1)).isoformat(),note='Retested both scanner members'))
    assert response.status_code==200,response.text
    review=dict(expected_version=1,expected_workflow_version=1,decision='approved',
        expires_at=(instant+timedelta(days=1)).isoformat(),note='Reviewed both source sets',
        evidence_reviewed=True,self_review_acknowledged=True)
    return path+'/risk-verification',review,response.json()


def approved(client,db,n):
    endpoint,payload,pending=submission(client,db,n)
    result=client.post(endpoint+'/review',headers=n['headers'],json=payload)
    assert result.status_code==200,result.text
    assert result.json()['eligible_for_exclusion'] is True
    return endpoint,result.json()


def test_group_approval_counts_once_and_retains_both_source_references(client,db_session,native):
    endpoint,result=approved(client,db_session,native)
    context=result['records'][0]['attestation']['group_context']
    assert context['observation_count']==2 and len(context['member_ids'])==2
    assert len(context['digest'])==64
    _,policy=status_scoring.apply_policy(db_session,uuid.UUID(native['org']),count_org_findings(db_session,native['org']))
    assert (policy['recorded_findings'],policy['active_findings'],policy['excluded_findings'])==(2,1,1)
    response=client.get(native['base']+'/findings/'+str(native['target'].finding_id)+'/risk-verification',headers=native['headers'])
    assert response.status_code==404


@pytest.mark.parametrize('mutation',['alias_payload','canonical_payload','new_alias_observation','lost_scan','asset_change'])
def test_either_member_source_drift_invalidates_approval(client,db_session,native,mutation):
    endpoint,result=approved(client,db_session,native)
    alias=db_session.get(Finding,native['target'].finding_id)
    canonical=db_session.get(Finding,native['source'].finding_id)
    if mutation=='alias_payload':alias.description='Changed scanner details'
    elif mutation=='canonical_payload':canonical.description='Changed canonical scanner details'
    elif mutation=='asset_change':
        from app.models.asset import Asset
        db_session.get(Asset,alias.asset_id).hostname='changed-source.example'
    elif mutation=='lost_scan':
        observation=db_session.get(FindingObservation,native['target'].id)
        observation.scan_id=None
    else:
        original=db_session.get(FindingObservation,native['target'].id)
        values={column.name:copy.deepcopy(getattr(original,column.name)) for column in FindingObservation.__table__.columns}
        values.update(id=uuid.uuid4(),import_id=uuid.uuid4(),recorded_at=original.recorded_at-timedelta(days=2))
        db_session.add(FindingObservation(**values))
    db_session.commit()
    result=client.get(endpoint,headers=native['headers'])
    assert result.status_code==200,result.text
    assert result.json()['eligible_for_exclusion'] is False


def test_pending_group_context_cannot_be_approved_after_alias_drift(client,db_session,native):
    endpoint,payload,pending=submission(client,db_session,native)
    alias=db_session.get(Finding,native['target'].finding_id);alias.description='Changed after submission'
    db_session.commit()
    result=client.post(endpoint+'/review',headers=native['headers'],json=payload)
    assert result.status_code==409,result.text


def test_assignment_note_preserves_group_approval_but_reopening_invalidates(client,db_session,native):
    endpoint,result=approved(client,db_session,native)
    path=native['base']+'/findings/'+str(native['source'].finding_id)+'/workflow'
    response=client.patch(path,headers=native['headers'],json=dict(expected_version=1,rationale='Assignment-only note'))
    assert response.status_code==200,response.text
    assert client.get(endpoint,headers=native['headers']).json()['eligible_for_exclusion'] is True
    response=client.patch(path,headers=native['headers'],json=dict(expected_version=2,status='open',rationale='Retest failed'))
    assert response.status_code==200,response.text
    assert client.get(endpoint,headers=native['headers']).json()['eligible_for_exclusion'] is False


def test_dismissal_progress_and_connection_timezone_do_not_change_group_proof(client,db_session,native):
    from sqlalchemy import func,text
    from app.models.scan import Scan
    endpoint,result=approved(client,db_session,native)
    group_id=db_session.get(Finding,native['source'].finding_id).consolidation_id
    before=db_session.scalar(select(func.am_consolidation_proof_v1(uuid.UUID(native['org']),group_id)))
    db_session.execute(text("SET LOCAL timezone='America/Los_Angeles'"))
    assert db_session.scalar(select(func.am_consolidation_proof_v1(uuid.UUID(native['org']),group_id)))==before
    scan=db_session.get(Scan,native['source'].scan_id)
    scan.dismissed_at=datetime.now(timezone.utc);scan.progress={'phase':'complete'}
    db_session.commit()
    assert client.get(endpoint,headers=native['headers']).json()['eligible_for_exclusion'] is True


def test_oversized_retained_source_fails_closed_without_hiding_risk(client,db_session,native):
    endpoint,result=approved(client,db_session,native)
    alias=db_session.get(Finding,native['target'].finding_id)
    alias.description='x'*(16*1024*1024+1);db_session.commit()
    assert client.get(endpoint,headers=native['headers']).json()['eligible_for_exclusion'] is False


def test_domain_source_and_inventory_digests_include_both_group_members(client,db_session,native):
    from app.services import dashboard_evidence
    endpoint,result=approved(client,db_session,native)
    org=uuid.UUID(native['org']);identifier=native['source'].finding_id
    before=dashboard_evidence.finding_source(db_session,org,identifier)[1]
    inventory_before=dashboard_evidence.inventory_scope(db_session,org)
    alias=db_session.get(Finding,native['target'].finding_id)
    alias.description='Different retained alias scanner material';db_session.commit()
    assert dashboard_evidence.finding_source(db_session,org,identifier)[1]!=before
    assert dashboard_evidence.inventory_scope(db_session,org)!=inventory_before


def test_new_submission_cannot_implicitly_revoke_group_approval(client,db_session,native):
    endpoint,result=approved(client,db_session,native)
    response=client.post(endpoint,headers=native['headers'],json=dict(expected_version=2,
        expected_workflow_version=1,source_reference='https://evidence.example/replacement',
        observed_at=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),note='Replace evidence without revocation'))
    assert response.status_code==409 and 'revoke' in response.text
    assert client.get(endpoint,headers=native['headers']).json()['state']=='approved'


@pytest.mark.parametrize('job_state',['failed','pending','running'])
def test_failed_source_archive_does_not_prevent_explicit_group_revocation(client,db_session,native,job_state):
    from app.models.archive import ArchiveBatch,ArchiveJob
    from app.models.enums import ArchiveAction,ArchiveItemType,ArchiveState,ScanStatus
    endpoint,result=approved(client,db_session,native)
    finding=db_session.get(Finding,native['source'].finding_id)
    batch=ArchiveBatch(org_id=uuid.UUID(native['org']),item_type=ArchiveItemType.upload,
        item_id=finding.scan_id,label='Retained failed source operation',state=ArchiveState.archiving)
    db_session.add(batch);db_session.flush()
    db_session.add(ArchiveJob(org_id=uuid.UUID(native['org']),batch_id=batch.id,
        action=ArchiveAction.archive,status=ScanStatus(job_state)))
    db_session.commit()
    response=client.post(endpoint+'/review',headers=native['headers'],json=dict(expected_version=2,
        expected_workflow_version=1,decision='revoked',note='Explicitly revoke before recovery'))
    if job_state!='failed':
        assert response.status_code==409
        return
    assert response.status_code==200,response.text
    assert response.json()['state']=='revoked'
    assert response.json()['eligible_for_exclusion'] is False
