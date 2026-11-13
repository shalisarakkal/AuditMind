"""Indexed lifecycle admission for published groups; metadata alone is not authority."""
from fastapi import HTTPException
from sqlalchemy import and_, exists, select, union
from sqlalchemy.orm import aliased
from app.models.archive import AssetScan
from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_consolidation import FindingConsolidation, FindingConsolidationDependency, FindingConsolidationMember


def ensure_free(db, org_id, kind, identifier):
    root=FindingConsolidation
    dependency=FindingConsolidationDependency
    published=exists(select(Finding.id).where(Finding.org_id==root.org_id,
        Finding.id==root.canonical_finding_id,Finding.consolidation_id==root.id))
    if not db.scalar(select(root.id).where(root.org_id==org_id,root.state=='active',published).limit(1)):
        return
    current=aliased(FindingConsolidation)
    generation=and_(current.org_id==dependency.org_id,current.id==dependency.consolidation_id,
        current.version==dependency.generation,current.state=='active')
    candidates=[select(dependency.consolidation_id).join(current,generation).where(dependency.org_id==org_id,
        dependency.resource_kind==kind,dependency.resource_id==identifier)]
    if kind in ('scan','asset','observation'):
        observation=FindingObservation
        match={'scan':observation.scan_id,'observation':observation.id,
            'asset':observation.asset_identity['asset_id'].astext}[kind]
        value=str(identifier) if kind=='asset' else identifier
        candidates.append(select(FindingConsolidationMember.consolidation_id).join(observation,
            and_(FindingConsolidationMember.org_id==observation.org_id,
                FindingConsolidationMember.finding_id==observation.finding_id)).where(
            observation.org_id==org_id,match==value))
    if kind=='scan':
        candidates.append(select(dependency.consolidation_id).join(current,generation).join(AssetScan,AssetScan.asset_id==dependency.resource_id).where(
            dependency.org_id==org_id,dependency.resource_kind=='asset',
            AssetScan.scan_id==identifier,AssetScan.created.is_(True)))
    # Start from tenant/resource indexes and the exact current generation, not
    # one correlated scan per group. Historical resources remain audit data;
    # they must not block retirement of an unrelated old tool after re-admission.
    identifiers=union(*candidates) if len(candidates)>1 else candidates[0]
    identifier=db.scalar(select(root.id).where(root.org_id==org_id,root.state=='active',published,
        root.id.in_(identifiers)).limit(1))
    if identifier:
        raise HTTPException(409,dict(code='active_consolidation',
            message='Undo the active finding consolidation in Findings > Workflow > Consolidation review before changing or removing this source.',
            consolidation_id=str(identifier)))


def ensure_identity_free(db,org_id,candidate_key):
    root=FindingConsolidation
    published=exists(select(Finding.id).where(Finding.org_id==root.org_id,
        Finding.id==root.canonical_finding_id,Finding.consolidation_id==root.id))
    from app.services.finding_identity import IDENTITY_VERSION
    identifier=db.scalar(select(root.id).where(root.org_id==org_id,root.state=='active',
        root.identity_version==IDENTITY_VERSION,root.candidate_key==candidate_key,published).limit(1))
    if identifier:
        raise HTTPException(409,dict(code='active_consolidation',message='Undo the active finding consolidation before reviewing another member of this native identity.',consolidation_id=str(identifier)))
