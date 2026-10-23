"""Trusted operator qualifications; source text/model output cannot grant coverage."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.models.enums import Domain
from app.schemas.evidence_assessment import EvidenceAssessment, EvidenceSnapshot
from app.services.scoring_service import tier_for_score

POLICY_VERSION = 'domain-evidence-v1'
AGGREGATION_VERSION = 'weighted-seven-half-up-v1'
# Objectives require operational observations, not just a standard or policy.
PROFILES = {
    'identity_access': ('privileged_authentication', 'account_lifecycle', 'access_review'),
    'network_config': ('exposure_inventory', 'segmentation_test', 'configuration_review'),
    'vulnerability_management': ('scan_coverage', 'patch_validation', 'exception_review'),
    'backup_recovery': ('backup_coverage', 'restore_test', 'recovery_objectives'),
    'monitoring_detection': ('log_coverage', 'detection_test', 'alert_triage'),
    'incident_response': ('contact_validation', 'response_exercise', 'lessons_followup'),
    'compliance_alignment': ('applicability_mapping', 'control_evidence_review', 'gap_review'),
}
WEIGHTS = dict(zip(PROFILES, (20, 15, 15, 15, 15, 10, 10)))


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    domain: Domain
    objective: str
    source_type: str = Field(pattern='^(finding|citation)$')
    source_id: str = Field(min_length=1, max_length=160)
    source_sha256: str = Field(pattern='^[0-9a-f]{64}$')
    observed_at: datetime
    scope: str = Field(min_length=1, max_length=2000)
    operational_review: bool = Field(strict=True)


class QualificationPack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy_version: str
    org_id: UUID
    reviewer: str = Field(min_length=1, max_length=255)
    reviewed_at: datetime
    expires_at: datetime
    scope: str = Field(min_length=1, max_length=2000)
    observations: list[Observation] = Field(max_length=100)


def pack_bytes() -> bytes:
    name = settings.REPORT_EVIDENCE_QUALIFICATIONS_FILE
    if not name:
        return b''
    with Path(name).open('rb') as stream:
        raw = stream.read(131073)
    if len(raw) > 131072:
        raise ValueError('Evidence qualification file exceeds 128 KiB')
    QualificationPack.model_validate_json(raw)
    return raw


def identity() -> dict:
    if not settings.REPORT_EVIDENCE_V3_ENABLED:
        return {}
    return {'policy': POLICY_VERSION, 'profiles': PROFILES, 'aggregation': AGGREGATION_VERSION,
            'qualification_sha256': hashlib.sha256(pack_bytes()).hexdigest()}


def source_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def qualification(context: dict, org_id: UUID) -> dict:
    raw = pack_bytes()
    result = {'policy_version': POLICY_VERSION, 'profiles': PROFILES,
              'pack_sha256': hashlib.sha256(raw).hexdigest(), 'qualified_domains': [],
              'qualified_references': {}, 'scope': None}
    if not raw:
        return result
    pack = QualificationPack.model_validate_json(raw)
    now = datetime.fromisoformat(context['captured_at'])
    if now.tzinfo is None:
        raise ValueError('Evidence capture requires a timezone')
    dates = [pack.reviewed_at, pack.expires_at, *[o.observed_at for o in pack.observations]]
    if any(d.tzinfo is None for d in dates):
        raise ValueError('Qualification dates require time zones')
    if pack.policy_version != POLICY_VERSION or pack.org_id != org_id:
        raise ValueError('Qualification policy or organization mismatch')
    if not pack.reviewer.strip() or not pack.scope.strip():
        raise ValueError('Qualification requires reviewer and scope')
    if not pack.reviewed_at <= now < pack.expires_at or (pack.expires_at - pack.reviewed_at).total_seconds() > 90 * 86400:
        raise ValueError('Qualification is not current or exceeds 90-day validity')
    sources = {('finding', f['finding_id']): f for f in context['sample_findings']}
    sources.update({('citation', c['citation_id']): c for c in context['citations']
                    if c.get('content_kind') == 'organization_policy'})
    by_domain = {d: set() for d in PROFILES}
    refs = {d: set() for d in PROFILES}
    for obs in pack.observations:
        domain = obs.domain.value
        source = sources.get((obs.source_type, obs.source_id))
        if (obs.objective not in PROFILES[domain] or not obs.operational_review
                or obs.scope != pack.scope or source is None or source.get('text_limits')
                or (obs.source_type == 'finding' and source.get('domain') != domain)
                or source_hash(source) != obs.source_sha256
                or not obs.observed_at <= pack.reviewed_at
                or (now - obs.observed_at).total_seconds() > 90 * 86400):
            raise ValueError('Qualification observation is stale, out of scope, excluded or hash-mismatched')
        by_domain[domain].add(obs.objective)
        refs[domain].add(obs.source_id)
    result['qualified_domains'] = [d for d in PROFILES if by_domain[d] == set(PROFILES[d])]
    result['qualified_references'] = {d: sorted(refs[d]) for d in result['qualified_domains']}
    result.update(scope=pack.scope, reviewer=pack.reviewer, reviewed_at=pack.reviewed_at.isoformat(), expires_at=pack.expires_at.isoformat())
    return result


def finalize(response: EvidenceAssessment, context: dict, org_id: UUID) -> EvidenceSnapshot:
    qualified = qualification(context, org_id)
    findings = {f['finding_id'] for f in context['sample_findings']}
    citations = {c['citation_id'] for c in context['citations']}
    organizational = {c['citation_id'] for c in context['citations'] if c.get('content_kind') == 'organization_policy'}
    for domain in response.domains:
        ids = {str(x) for x in domain.evidence_finding_ids}
        if not ids <= findings or not set(domain.citation_ids) <= citations:
            raise ValueError('Domain references excluded or foreign evidence')
        observations = len(ids) + len(set(domain.citation_ids) & organizational)
        if domain.evidence_status in ('sufficient', 'limited', 'conflicting'):
            minimum = 2 if domain.evidence_status == 'conflicting' else 1
            if observations < minimum:
                raise ValueError('Domain requires organizational observations, not guidance alone')
        if domain.evidence_status == 'sufficient':
            name = domain.domain.value
            expected = set(qualified['qualified_references'].get(name, []))
            if name not in qualified['qualified_domains'] or not expected <= ids | set(domain.citation_ids):
                raise ValueError('Sufficient domain lacks trusted reviewed coverage')
    complete = all(d.evidence_status == 'sufficient' for d in response.domains)
    score = (sum(d.score * WEIGHTS[d.domain.value] for d in response.domains) + 50) // 100 if complete else None
    snapshot = EvidenceSnapshot(**response.model_dump(), overall_score=score,
        overall_tier=tier_for_score(score) if score is not None else None,
        assessment_status='complete' if complete else 'partial')
    snapshot.provenance = {'schema_version': 3, 'evidence_qualification': qualified,
        'aggregation_version': AGGREGATION_VERSION,
        'evidence_status_counts': {s: sum(d.evidence_status == s for d in response.domains)
                                  for s in ('sufficient', 'limited', 'insufficient', 'conflicting')}}
    return snapshot
