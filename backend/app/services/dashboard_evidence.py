"""Live qualification integrity, not AI assessment or a claim of control success."""
import hashlib
import uuid
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, cast, Text
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import Domain
from app.models.finding import Finding
from app.models.event import Event
from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
from app.models.scoring_qualification import DomainEvidenceQualification
from app.schemas.scoring_qualification import QualificationDraftUpdate
from app.services.evidence_policy import POLICY_VERSION, PROFILES, source_hash

MAX_AGE = timedelta(days=90)
SCOPE_VERSION = "dashboard-organization-inventory-v2"


class EvidenceSourceError(ValueError):
    pass


def finding_source(db: Session, org_id: uuid.UUID, source_id: uuid.UUID, *, lock=False):
    query = select(Finding).where(Finding.id == source_id, Finding.org_id == org_id, Finding.archived_at.is_(None))
    if lock:
        query = query.with_for_update(read=True)
    finding = db.scalar(query.execution_options(populate_existing=True))
    if finding is None:
        raise EvidenceSourceError("Active organization finding not found")
    snapshot = {name: getattr(finding, name) for name in (
        "id", "org_id", "asset_id", "scan_id", "domain", "severity", "category",
        "description", "source", "raw_data", "event_count", "first_seen", "last_seen")}
    snapshot["binding_version"] = "dashboard-finding-v1"
    return finding, source_hash(snapshot)


def document_source(db: Session, org_id: uuid.UUID, source_id: uuid.UUID, *, lock=False):
    query = select(KnowledgeVersion, KnowledgeDocument).join(KnowledgeDocument,
        KnowledgeDocument.id == KnowledgeVersion.document_id).where(KnowledgeVersion.id == source_id,
        KnowledgeDocument.org_id == org_id, KnowledgeVersion.content_kind == "organization_policy",
        KnowledgeVersion.current.is_(True), KnowledgeVersion.retired_at.is_(None), KnowledgeVersion.purged_at.is_(None))
    result = db.execute(query.execution_options(populate_existing=True)).first()
    if result is None:
        raise EvidenceSourceError("Current organization operational document version not found")
    version, document = result
    if lock:
        # Publishing locks document before version. Follow that order explicitly:
        # a joined FOR SHARE can lock version first and deadlock with publishing.
        document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document.id,
            KnowledgeDocument.org_id == org_id).with_for_update(read=True).execution_options(populate_existing=True))
        version = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == source_id,
            KnowledgeVersion.current.is_(True), KnowledgeVersion.content_kind == "organization_policy",
            KnowledgeVersion.retired_at.is_(None), KnowledgeVersion.purged_at.is_(None))
            .with_for_update(read=True).execution_options(populate_existing=True))
        if document is None or version is None:
            raise EvidenceSourceError("Operational document changed during review")
    if not version.content or not version.content.strip() or hashlib.sha256(version.content.encode("utf-8")).hexdigest() != version.content_hash:
        raise EvidenceSourceError("Document content is missing or inconsistent with its hash")
    return version, source_hash({"binding_version": "dashboard-document-v1", "org_id": org_id,
        "document_id": document.id, "version_id": version.id, "number": version.number,
        "title": document.title, "edition": version.edition, "source": version.source,
        "content_kind": version.content_kind, "content_hash": version.content_hash})


def source_digest(db, org_id, domain, observation, *, lock=False):
    if observation.source_type == "document_version":
        return document_source(db, org_id, observation.source_id, lock=lock)[1]
    finding, digest = finding_source(db, org_id, observation.source_id, lock=lock)
    if finding.domain != domain:
        raise EvidenceSourceError("Evidence finding belongs to another domain")
    return digest


def inventory_scope(db: Session, org_id: uuid.UUID) -> dict:
    for event in inventory_progress(db, org_id):
        if event["type"] == "result":
            return event["data"]
    raise RuntimeError("Inventory scan ended without a result")


def inventory_progress(db: Session, org_id: uuid.UUID):
    """Bounded-memory fingerprint; reviewer/evaluation calls only, not default dashboard.

    Includes full active baseline population, not just assets appearing in evidence.
    A future default rollout must benchmark this on large inventories.
    """
    started = time.monotonic()
    yield {"type": "progress", "phase": "counting", "processed": 0, "total": None, "elapsed_seconds": 0}
    digest = hashlib.sha256(f"{SCOPE_VERSION}:{org_id}".encode())
    assets = findings = 0
    asset_columns = (Asset.id, Asset.type, Asset.subtype, Asset.type_known, Asset.hostname,
        Asset.ip, Asset.cloud_id, Asset.environment, Asset.criticality, Asset.tags, Asset.details)
    finding_columns = (Finding.id, Finding.asset_id, Finding.scan_id, Finding.domain,
        Finding.severity, Finding.category, Finding.description, Finding.source, Finding.raw_data)
    # Include material lifecycle history so archiving/restoring the same IDs or
    # retiring/reactivating identical content cannot resurrect an old approval.
    # Retention removing these events conservatively requires re-review too.
    lifecycle_types = ("import", "archive", "restore", "purge", "asset_added", "finding_added",
        "document_uploaded", "document_retired", "document_removed", "document_reactivation_queued",
        "org_archived", "org_restored")
    populations = (
        ("assets", Asset, asset_columns, (Asset.org_id == org_id, Asset.archived_at.is_(None))),
        ("findings", Finding, finding_columns, (Finding.org_id == org_id, Finding.archived_at.is_(None))),
        ("lifecycle", Event, (Event.id, Event.type, Event.outcome), (Event.org_id == org_id, Event.type.in_(lifecycle_types))),
    )
    total = sum(db.scalar(select(func.count()).select_from(model).where(*filters)) for _, model, _, filters in populations)
    processed = 0
    for kind, model, columns, filters in populations:
        yield {"type": "progress", "phase": kind, "processed": processed, "total": total,
               "elapsed_seconds": round(time.monotonic() - started, 1)}
        # PostgreSQL canonical JSONB preserves all projected semantic fields.
        # Only fixed-size hashes cross the wire, not millions of JSON payloads.
        row_hash = func.sha256(func.convert_to(cast(func.jsonb_build_array(*columns), Text), "UTF8"))
        # Materialize the compact projection before sorting. Sorting on the base
        # UUID key otherwise encourages millions of random heap-page reads.
        compact = select(model.id.label("id"), row_hash.label("digest")).where(*filters).cte("inventory_hashes").prefix_with("MATERIALIZED")
        query = select(compact.c.digest).order_by(compact.c.id).execution_options(yield_per=5000)
        with db.execute(query) as result:
            for batch in result.partitions(5000):
                for row in batch:
                    digest.update(kind.encode() + bytes(row[0]))
                processed += len(batch)
                assets += len(batch) if kind == "assets" else 0
                findings += len(batch) if kind == "findings" else 0
                yield {"type": "progress", "phase": kind, "processed": processed, "total": total,
                       "elapsed_seconds": round(time.monotonic() - started, 1)}
    yield {"type": "result", "data": {"scope_kind": "organization_all", "binding_version": SCOPE_VERSION,
           "inventory_sha256": digest.hexdigest(), "asset_count": assets, "finding_count": findings}}


def validate_observations(db, row, now, *, lock=False):
    payload = QualificationDraftUpdate(expected_version=row.version, scope=row.scope,
        rationale=row.rationale, observations=row.observations, inventory_sha256=row.inventory_sha256)
    payload.validate_domain(row.domain)
    digests = {}
    for observation in payload.observations:
        if not now - MAX_AGE <= observation.observed_at <= now:
            raise ValueError("Observation is expired or in the future")
        key = (observation.source_type, observation.source_id)
        if key not in digests:
            digests[key] = source_digest(db, row.org_id, row.domain, observation, lock=lock)
        if digests[key] != observation.source_sha256:
            raise EvidenceSourceError("Evidence source changed; re-review required")
    return payload.observations


def domain_evaluation(db, row, domain, scope, now):
    def result(status, reason):
        return {"domain": domain.value, "evidence_status": status, "reason_code": reason,
                "eligible": status == "sufficient", "qualification_id": str(row.id) if row else None,
                "version": row.version if row else None}
    if row is None:
        return result("insufficient", "no_evidence")
    if row.status not in ("approved", "conflicting"):
        return result("limited" if row.observations else "insufficient", "revoked" if row.status == "revoked" else "draft_only")
    if row.policy_version != POLICY_VERSION:
        return result("limited", "policy_changed")
    if not row.reviewed_by or not row.reviewed_at or not row.expires_at or not isinstance(row.review_attestation, dict) or any(
        row.review_attestation.get(key) is not True for key in ("operational_review", "covers_entire_inventory", "conflicts_reviewed")):
        return result("limited", "approval_incomplete")
    bound_scope = row.review_attestation.get("inventory")
    if not isinstance(bound_scope, dict) or bound_scope.get("binding_version") != SCOPE_VERSION or bound_scope.get("inventory_sha256") != row.inventory_sha256:
        return result("limited", "scope_binding_invalid")
    reviewed_at = row.reviewed_at.astimezone(timezone.utc)
    expires_at = row.expires_at.astimezone(timezone.utc)
    if not reviewed_at <= now < expires_at or expires_at - reviewed_at > MAX_AGE:
        return result("limited", "review_expired_or_invalid")
    if row.inventory_sha256 != scope["inventory_sha256"]:
        return result("limited", "inventory_changed")
    if scope["asset_count"] == 0 and scope["finding_count"] == 0:
        return result("insufficient", "empty_inventory")
    try:
        observations = validate_observations(db, row, now)
        if any(o.observed_at > row.reviewed_at for o in observations):
            return result("limited", "observation_after_review")
    except (ValueError, TypeError):
        return result("limited", "source_invalid_or_stale")
    if row.status == "conflicting":
        return result("conflicting", "material_conflict") if len({(o.source_type, o.source_id) for o in observations}) >= 2 else result("limited", "conflict_references_incomplete")
    if {o.objective for o in observations} != set(PROFILES[domain.value]):
        return result("limited", "objectives_incomplete")
    return result("sufficient", "qualified")


def evaluate_org(db: Session, org_id: uuid.UUID, *, now=None, scope=None):
    now = now or datetime.now(timezone.utc)
    scope = scope if scope is not None else inventory_scope(db, org_id)
    rows = {row.domain: row for row in db.scalars(select(DomainEvidenceQualification).where(DomainEvidenceQualification.org_id == org_id))}
    domains = [domain_evaluation(db, rows.get(domain), domain, scope, now) for domain in Domain]
    count = sum(domain["eligible"] for domain in domains)
    same_scope = len({rows[domain].scope for domain in rows if rows[domain].status == "approved"}) == 1
    return {"policy_version": POLICY_VERSION, "evaluated_at": now.isoformat(), "inventory": scope, "domains": domains,
        "qualified_domain_count": count,
        "assessment_status": "complete" if count == len(Domain) and same_scope else "partial" if count else "not_assessed",
        "overall_reason": "scope_mismatch" if count == len(Domain) and not same_scope else None}
