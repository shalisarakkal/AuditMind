"""Current bounded proof scope for an already published pair, not admission."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import defer
from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_consolidation import FindingConsolidation
from app.models.finding_observation import FindingObservation
from app.services.consolidation_dependencies import MAX_OBSERVATIONS, manifest
from app.services.identity_bindings import identity_reviews


def capture(db, org_id, finding):
    if finding.consolidation_id is None:
        return None
    root=db.scalar(select(FindingConsolidation).where(FindingConsolidation.org_id==org_id,
        FindingConsolidation.id==finding.consolidation_id).execution_options(populate_existing=True))
    if root is None or root.state!='active' or root.canonical_finding_id!=finding.id:
        raise HTTPException(409,'Current canonical consolidation is required for scoring evidence')
    decision=db.scalar(select(FindingCanonicalDecision).where(FindingCanonicalDecision.org_id==org_id,
        FindingCanonicalDecision.id==root.canonical_decision_id))
    latest=db.scalar(select(FindingCanonicalDecision.id).where(FindingCanonicalDecision.org_id==org_id,
        FindingCanonicalDecision.pair_key==root.pair_key).order_by(FindingCanonicalDecision.version.desc()).limit(1))
    if decision is None or decision.state!='selected' or decision.id!=latest:
        raise HTTPException(409,'Canonical designation is no longer available')
    observations=db.scalars(select(FindingObservation).options(defer(FindingObservation.payload)).where(
        FindingObservation.org_id==org_id,FindingObservation.finding_id.in_((root.finding_a_id,root.finding_b_id)))
        .limit(MAX_OBSERVATIONS+1)).all()
    if not 2<=len(observations)<=MAX_OBSERVATIONS:
        raise HTTPException(409,'Group evidence exceeds the bounded review limit or is unavailable')
    reviews=identity_reviews(db,org_id,observations)
    if any(not binding or not binding['current'] or assessment['candidate_key']!=root.candidate_key
            for assessment,binding in reviews.values()):
        raise HTTPException(409,'All group observations need current independently reviewed identities; undo and review changed sources')
    findings={row.id:row for row in db.scalars(select(Finding).options(defer(Finding.raw_data),
        defer(Finding.description),defer(Finding.details)).where(Finding.org_id==org_id,
            Finding.id.in_((root.finding_a_id,root.finding_b_id))))}
    if len({(row.domain,row.severity) for row in findings.values()})!=1:
        raise HTTPException(409,'Group classification changed; undo and review both findings')
    latest=[]
    for identifier in findings:
        rows=sorted((o for o in observations if o.finding_id==identifier),key=lambda o:(o.recorded_at,o.id),reverse=True)
        if not rows or (len(rows)>1 and rows[0].recorded_at==rows[1].recorded_at):
            raise HTTPException(409,'Group sources have missing or ambiguous latest observations')
        latest.append(rows[0].id)
    for row in db.execute(select(FindingObservation.finding_id,FindingObservation.payload['domain'].astext,
            FindingObservation.payload['severity'].astext).where(FindingObservation.org_id==org_id,FindingObservation.id.in_(latest))):
        current=findings[row[0]]
        if row[1]!=current.domain.value or row[2]!=current.severity.value:
            raise HTTPException(409,'Latest source classification differs from the displayed group; undo and review sources')
    sources=manifest(db,org_id,decision,findings,observations,dict(canonical_asset_id=str(root.canonical_asset_id),tool_id=str(root.tool_id)))
    digest=db.scalar(select(func.am_consolidation_proof_v1(org_id,root.id)))
    if sources is None or digest is None:
        raise HTTPException(409,'Retained group sources are unavailable, changed or exceed the supported proof size limits')
    return dict(contract='consolidated-proof-v1',group_id=str(root.id),version=root.version,
        canonical_finding_id=str(finding.id),member_ids=sorted(str(value) for value in findings),
        observation_count=len(observations),digest=digest)
