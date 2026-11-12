"""Read-only Stage A admission preview. Never publishes consolidation state."""
import hashlib
import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, defer, load_only

from app.models.enums import UserRole
from app.models.finding import Finding
from app.models.finding_canonical import FindingCanonicalDecision
from app.models.finding_consolidation import FindingConsolidation, FindingConsolidationDecision
from app.models.finding_history import FindingHistory
from app.models.finding_observation import FindingObservation
from app.models.finding_suppression import FindingSuppression
from app.models.finding_verification import FindingVerification
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.finding_consolidation import ConsolidationPage, ConsolidationHistoryPage
from app.services import finding_canonical
from app.services.consolidation_dependencies import MAX_OBSERVATIONS, manifest
from app.services.finding_identity import IDENTITY_VERSION, NESSUS_MAPPING
from app.services.identity_bindings import identity_reviews

PENDING_COMPONENTS = ("atomic_membership_and_dependency_publication", "atomic_visibility_publication",
    "group_aware_proof", "source_lifecycle_guards", "external_identity_conflict_validation",
    "pending_source_job_validation", "transactional_write_admission", "guarded_ui")


def page(db, org_id, *, limit, offset):
    rows = db.scalars(select(FindingConsolidation).where(FindingConsolidation.org_id == org_id)
        .order_by(FindingConsolidation.created_at.desc(), FindingConsolidation.id.desc())
        .limit(limit + 1).offset(offset)).all()
    return ConsolidationPage(items=rows[:limit], has_more=len(rows) > limit, limit=limit, offset=offset)


def history(db, org_id, identifier, *, limit, before_version):
    if db.scalar(select(FindingConsolidation.id).where(FindingConsolidation.org_id == org_id,
            FindingConsolidation.id == identifier)) is None:
        raise HTTPException(404, "Consolidation record not found")
    query = select(FindingConsolidationDecision).options(load_only(FindingConsolidationDecision.id,
        FindingConsolidationDecision.version, FindingConsolidationDecision.state,
        FindingConsolidationDecision.rationale, FindingConsolidationDecision.actor_label,
        FindingConsolidationDecision.created_at)).where(FindingConsolidationDecision.org_id == org_id,
            FindingConsolidationDecision.consolidation_id == identifier)
    if before_version is not None:
        query = query.where(FindingConsolidationDecision.version < before_version)
    rows = db.scalars(query.order_by(FindingConsolidationDecision.version.desc()).limit(limit + 1)).all()
    return ConsolidationHistoryPage(items=rows[:limit], has_more=len(rows) > limit,
        limit=limit, before_version=before_version)


def preview(db, org_id, actor_id, identifier):
    # Keep the dependency session intact; a separate, strictly read-only snapshot
    # prevents mixed identity/workflow/source generations during preview.
    with db.get_bind().engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
            return _preview(snapshot, org_id, actor_id, identifier)


def _preview(db, org_id, actor_id, identifier):
    member = db.scalar(select(OrgMembership).where(OrgMembership.org_id == org_id, OrgMembership.user_id == actor_id))
    actor = db.get(User, actor_id)
    org = db.get(Organization, org_id)
    if member is None or member.role != UserRole.admin or actor is None or not actor.is_active:
        raise HTTPException(403, "An active organization administrator is required for this preview")
    if org is None or org.archived_at is not None or org.purge_requested_at is not None:
        raise HTTPException(409, "Organization is read-only or unavailable")
    decision = db.scalar(select(FindingCanonicalDecision).where(FindingCanonicalDecision.org_id == org_id,
        FindingCanonicalDecision.id == identifier))
    if decision is None:
        raise HTTPException(404, "Canonical decision not found")
    if decision.state != "selected":
        raise HTTPException(409, "A current selected canonical decision is required")
    pair_observations = {row.id: row for row in db.scalars(select(FindingObservation)
        .options(defer(FindingObservation.payload)).where(FindingObservation.org_id == org_id,
            FindingObservation.id.in_((decision.source_observation_id, decision.target_observation_id))))}
    if len(pair_observations) != 2:
        raise HTTPException(409, "The retained reference or target observation is unavailable")
    target = pair_observations[decision.target_observation_id]
    prepared = finding_canonical.preview(db, org_id, target, decision.source_observation_id, bounded=True)
    selected = prepared["saved"]
    if not selected or selected["id"] != str(decision.id) or not selected["current"]:
        raise HTTPException(409, "Canonical selection is stale; re-review it before consolidation preview")
    ids = (decision.finding_a_id, decision.finding_b_id)
    if ({str(value) for value in ids} != {row["id"] for row in prepared["context"]["findings"]}
            or decision.canonical_finding_id not in ids):
        raise HTTPException(409, "Canonical decision membership is inconsistent; re-review the pair")
    findings = {row.id: row for row in db.scalars(select(Finding).options(
        defer(Finding.description), defer(Finding.raw_data), defer(Finding.details)).where(
            Finding.org_id == org_id, Finding.id.in_(ids)))}
    canonical = findings[decision.canonical_finding_id]
    alias = findings[next(value for value in ids if value != canonical.id)]
    blockers = []

    def block(code, message):
        if not any(item["code"] == code for item in blockers):
            blockers.append(dict(code=code, message=message))

    if canonical.domain != alias.domain or canonical.severity != alias.severity:
        block("classification_conflict", "Both findings must have the same domain and severity")
    if canonical.workflow_status not in ("open", "accepted_risk", "mitigated"):
        block("canonical_workflow", "Explicitly reopen a terminal canonical finding before consolidation")
    optional = ("assignee_id", "due_date", "risk_review_date", "due_timezone", "due_expires_at",
        "risk_review_timezone", "risk_review_expires_at", "workflow_updated_at", "risk_verified_at",
        "risk_verified_workflow_version", "risk_verification_expires_at", "risk_verified_observation_count",
        "risk_verification_source_kind", "risk_verification_document_id", "risk_verification_source_hash")
    recorded_work = db.scalar(select(or_(select(FindingHistory.id).where(FindingHistory.org_id == org_id,
        FindingHistory.finding_id == alias.id).exists(), select(FindingVerification.id).where(
            FindingVerification.org_id == org_id, FindingVerification.finding_id == alias.id).exists())))
    if (alias.workflow_status != "open" or alias.workflow_version != 0 or alias.risk_verification_version != 0
            or alias.risk_verification_state != "unverified" or recorded_work
            or any(getattr(alias, name) is not None for name in optional)):
        block("alias_not_pristine", "The alias has independent workflow/proof work; stage A must not discard it")
    if any(row.risk_verification_state == "approved" for row in findings.values()):
        block("approved_proof", "Explicitly revoke the approved scoring decision before consolidation")
    candidate_key = prepared["context"]["candidate_key"]
    standing = db.scalar(select(FindingSuppression.id).where(FindingSuppression.org_id == org_id,
        FindingSuppression.identity_version == IDENTITY_VERSION, FindingSuppression.candidate_key == candidate_key,
        FindingSuppression.state == "suppressed").limit(1))
    if standing:
        block("standing_suppression", "Resolve the standing suppression independently before consolidation")
    existing = db.scalar(select(FindingConsolidation.id).where(FindingConsolidation.org_id == org_id,
        FindingConsolidation.state == "active", or_(FindingConsolidation.finding_a_id.in_(ids),
            FindingConsolidation.finding_b_id.in_(ids), FindingConsolidation.candidate_key == candidate_key)).limit(1))
    if existing:
        block("group_conflict", "A recorded active group overlaps this pair or native identity")
    recorded = db.execute(select(FindingConsolidation.id, FindingConsolidation.version,
        FindingConsolidation.state).where(FindingConsolidation.org_id == org_id,
            FindingConsolidation.pair_key == decision.pair_key)).one_or_none()
    recorded_group = dict(id=str(recorded.id), version=recorded.version, state=recorded.state) if recorded else None

    rows = db.scalars(select(FindingObservation).options(defer(FindingObservation.payload)).where(
            FindingObservation.org_id == org_id, FindingObservation.finding_id.in_(ids)).order_by(
                FindingObservation.finding_id, FindingObservation.recorded_at.desc(), FindingObservation.id.desc())
        .limit(MAX_OBSERVATIONS + 1)).all()
    observation_material = []
    latest_classification = {}
    identity = None
    if len(rows) > MAX_OBSERVATIONS:
        block("observation_limit", "This preview supports at most 1000 retained observations across the pair")
    else:
        reviews = identity_reviews(db, org_id, rows)
        by_finding = defaultdict(list)
        for observation in rows:
            assessment, binding = reviews[observation.id]
            valid = (binding and binding["current"] and assessment["version"] == IDENTITY_VERSION
                and assessment["mapping"] == NESSUS_MAPPING and assessment["candidate_key"] == candidate_key)
            if not valid:
                block("identity_reviews_required", "Every retained observation needs a current matching independent native identity review")
            elif identity is None:
                identity = dict(version=IDENTITY_VERSION, mapping=NESSUS_MAPPING, candidate_key=candidate_key,
                    tool_id=binding["tool_id"], canonical_asset_id=binding["canonical_asset_id"])
            by_finding[observation.finding_id].append(observation)
            observation_material.append(dict(id=str(observation.id), finding_id=str(observation.finding_id),
                binding_version=binding["version"] if binding else None, current=bool(valid),
                recorded_at=observation.recorded_at.isoformat()))
        latest_ids = [observed[0].id for observed in by_finding.values()]
        # Extract only the two relevant source classifications. Historical raw
        # JSON may be large; do not decompress every retained payload for metadata.
        classifications = {str(row.id): dict(domain=row.domain, severity=row.severity) for row in db.execute(
            select(FindingObservation.id, FindingObservation.payload["domain"].astext.label("domain"),
                FindingObservation.payload["severity"].astext.label("severity")).where(
                    FindingObservation.org_id == org_id, FindingObservation.id.in_(latest_ids)))}
        latest_classification = classifications
        for identifier, finding in findings.items():
            observed = by_finding[identifier]
            if not observed:
                block("identity_reviews_required", "Both findings require retained reviewed observations")
                continue
            latest = observed[0]
            if len(observed) > 1 and observed[1].recorded_at == latest.recorded_at:
                block("ambiguous_latest_observation", "Equal observation times do not establish latest source ordering")
            classification = classifications.get(str(latest.id), {})
            if classification.get("domain") != finding.domain.value or classification.get("severity") != finding.severity.value:
                block("unpublished_classification", "Latest retained source classification differs from the displayed finding or is unavailable")
    dependencies = None
    if not blockers:
        dependencies = manifest(db, org_id, decision, findings, rows, identity)
        if dependencies is None:
            block("source_ownership_unavailable", "Both findings require active retained scan and asset owners in this organization")
    dependency_summary = ({key: dependencies[key] for key in
        ("contract", "fingerprint", "resource_count", "resource_counts")} if dependencies else None)
    context = dict(contract="consolidation-foundation-v1", org_id=str(org_id), actor_id=str(actor_id),
        decision_id=str(decision.id), decision_version=decision.version, canonical_token=prepared["review_token"],
        identity=identity, observations=observation_material, latest_classification=latest_classification, blockers=blockers,
        dependency_summary=dependency_summary, recorded_group=recorded_group, apply_available=False)
    fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return dict(contract=context["contract"], canonical_decision_id=str(decision.id), decision_version=decision.version,
        canonical_finding_id=str(canonical.id), alias_finding_id=str(alias.id), identity=identity,
        prerequisites_met=not blockers, prerequisites_scope="bounded_pair_only",
        blockers=blockers, observation_count=len(rows),
        observation_limit=MAX_OBSERVATIONS, observation_count_truncated=len(rows) > MAX_OBSERVATIONS,
        snapshot_fingerprint=fingerprint, recorded_group=recorded_group,
        dependency_summary=dependency_summary,
        findings=prepared["context"]["findings"], apply_available=False,
        pending_components=PENDING_COMPONENTS,
        availability_reason="Read-only Stage A foundation. No consolidation or payload publication can be applied.")
