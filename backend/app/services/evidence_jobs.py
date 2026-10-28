"""Explicit queued evaluation; revision checks make stale cache fail closed."""
import logging
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.enums import Domain
from app.models.organization import Organization
from app.models.evidence_evaluation import EvidenceEvaluation, OrganizationEvidenceRevision
from app.models.scoring_qualification import DomainEvidenceQualification
from app.services import dashboard_evidence as evidence
from app.services.evidence_policy import POLICY_VERSION, PROFILES, source_hash
from app.schemas.evidence_evaluation import EvaluationResult

logger = logging.getLogger(__name__)
EVALUATOR_VERSION = "dashboard-evidence-evaluation-v1"
ACTIVE = ("pending", "running")


def now():
    return datetime.now(timezone.utc)


def policy_identity():
    return source_hash({"evaluator": EVALUATOR_VERSION, "policy": POLICY_VERSION,
        "profiles": PROFILES, "binding": evidence.SCOPE_VERSION, "max_age_seconds": evidence.MAX_AGE.total_seconds()})


def revision(db, org_id):
    value = db.scalar(select(OrganizationEvidenceRevision.revision).where(OrganizationEvidenceRevision.org_id == org_id))
    return value if value is not None else 0


def enqueue(db, org_id, user_id):
    # Caller holds the organization job-admission lock. At most one active
    # evaluation per organization, enforced again by a partial unique index.
    job = db.scalar(select(EvidenceEvaluation).where(EvidenceEvaluation.org_id == org_id,
        EvidenceEvaluation.status.in_(ACTIVE)).with_for_update())
    if job is None:
        db.execute(insert(OrganizationEvidenceRevision).values(org_id=org_id, revision=0).on_conflict_do_nothing())
        job = EvidenceEvaluation(org_id=org_id, started_by=user_id)
        db.add(job); db.flush()
    return job


def valid_result(job, current_revision, instant=None):
    instant = instant or now()
    if (job is None or job.status != "completed" or job.cancel_requested_at is not None
            or job.captured_revision != current_revision or job.policy_identity != policy_identity()
            or (job.valid_until is not None and instant >= job.valid_until)):
        return False
    result = job.result
    if not isinstance(result, dict) or result.get("policy_version") != POLICY_VERSION:
        return False
    try:
        parsed = EvaluationResult.model_validate(result)
        if parsed.evaluated_at.tzinfo is None or parsed.evaluated_at > instant:
            return False
        for domain in parsed.domains:
            if domain.eligible and (domain.reviewed_at is None or domain.expires_at is None
                    or domain.reviewed_at.tzinfo is None or domain.expires_at.tzinfo is None
                    or not domain.reviewed_at <= parsed.evaluated_at < domain.expires_at
                    or not domain.source_references or job.valid_until is None
                    or job.valid_until > domain.expires_at):
                return False
    except (ValueError, TypeError):
        return False
    domains = result.get("domains")
    if not (isinstance(result.get("inventory"), dict)
        and result["inventory"].get("binding_version") == evidence.SCOPE_VERSION
        and isinstance(domains, list) and len(domains) == len(Domain)
        and all(isinstance(d, dict) and isinstance(d.get("domain"), str) and type(d.get("eligible")) is bool for d in domains)):
        return False
    if {d["domain"] for d in domains} != {d.value for d in Domain}:
        return False
    count = sum(d["eligible"] for d in domains)
    for domain in domains:
        if domain.get("evidence_status") not in ("insufficient", "limited", "conflicting", "sufficient") or not isinstance(domain.get("reason_code"), str):
            return False
        if domain["eligible"] != (domain["evidence_status"] == "sufficient" and domain["reason_code"] == "qualified"):
            return False
        if domain["eligible"] and (not domain.get("qualification_id") or not domain.get("scope") or not domain.get("expires_at")):
            return False
    compatible = len({d.get("scope") for d in domains if d["eligible"]}) == 1
    expected = "complete" if count == len(Domain) and compatible else "partial" if count else "not_assessed"
    return result.get("qualified_domain_count") == count and result.get("assessment_status") == expected


def current_result(db, org_id, instant=None):
    current_revision = revision(db, org_id)
    job = db.scalar(select(EvidenceEvaluation).where(EvidenceEvaluation.org_id == org_id,
        EvidenceEvaluation.status == "completed", EvidenceEvaluation.captured_revision == current_revision,
        EvidenceEvaluation.policy_identity == policy_identity()).order_by(EvidenceEvaluation.created_at.desc(), EvidenceEvaluation.id).limit(1))
    return job if valid_result(job, current_revision, instant) else None


def dashboard_state(db, org_id):
    from app.models.scoring_qualification import OrganizationScoringSettings
    mode = db.get(OrganizationScoringSettings, org_id, populate_existing=True)
    enabled = mode.evidence_qualified_enabled if mode else False
    current_revision = revision(db, org_id)
    job = current_result(db, org_id) if enabled else None
    return {"scoring_mode": "evidence_qualified" if enabled else "findings_based",
        "settings_version": mode.version if mode else 0,
        "evidence_revision": current_revision, "evaluation_id": str(job.id) if job else None}


class EvaluationCancelled(Exception):
    pass


def process_job(db: Session, job_id: uuid.UUID):
    job = db.get(EvidenceEvaluation, job_id, populate_existing=True)
    if job is None or job.status != "running":
        return
    org_id, engine = job.org_id, db.get_bind()
    db.rollback()  # No idle second transaction throughout the long read.
    started = time.monotonic()
    last_update = 0.0
    last_phase = None

    def progress(event, *, force=False):
        nonlocal last_update, last_phase
        tick = time.monotonic()
        if not force and tick - last_update < 0.5 and event.get("phase") == last_phase:
            return
        with Session(engine) as report:
            row = report.get(EvidenceEvaluation, job_id, populate_existing=True)
            if row is None or row.status != "running" or row.cancel_requested_at is not None:
                raise EvaluationCancelled()
            report.execute(update(EvidenceEvaluation).where(EvidenceEvaluation.id == job_id,
                EvidenceEvaluation.status == "running").values(progress={**(row.progress or {}), **event, "elapsed_seconds": round(tick-started, 1)}, heartbeat_at=now()))
            report.commit()
        last_update, last_phase = tick, event.get("phase")

    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with Session(bind=connection) as snapshot:
                org = snapshot.get(Organization, org_id)
                if org is None or org.archived_at is not None or org.purge_requested_at is not None:
                    raise EvaluationCancelled()
                captured_revision = revision(snapshot, org_id)
                captured_policy = policy_identity()
                scope = None
                with closing(evidence.inventory_progress(snapshot, org_id)) as events:
                    for event in events:
                        if event["type"] == "progress":
                            # Never throttle away the final short batch (often
                            # lifecycle rows): completed must display exact total.
                            progress(event, force=event.get("total") is not None
                                and event.get("processed") == event["total"])
                        else:
                            scope = event["data"]
                if scope is None:
                    raise ValueError("Inventory scan ended without an explicit result")
                progress({"phase": "qualifications"}, force=True)
                result = evidence.evaluate_org(snapshot, org_id, scope=scope)
                eligible = {d["domain"] for d in result["domains"] if d["eligible"]}
                expiries = [row.expires_at for row in snapshot.scalars(select(DomainEvidenceQualification).where(
                    DomainEvidenceQualification.org_id == org_id)) if row.domain.value in eligible]
                valid_until = min(expiries) if expiries else None
        # Check the current revision without locking an input counter: cascade
        # writers must not deadlock against the job row. A later writer commit
        # atomically invalidates this revision; every result read checks it again.
        row = db.get(EvidenceEvaluation, job_id, with_for_update=True, populate_existing=True)
        if row is None:
            return
        if row.cancel_requested_at is not None or row.status != "running":
            raise EvaluationCancelled()
        current = db.get(OrganizationEvidenceRevision, org_id, populate_existing=True)
        row.captured_revision, row.policy_identity = captured_revision, captured_policy
        row.status = "completed" if current is not None and current.revision == captured_revision and captured_policy == policy_identity() else "superseded"
        row.result = result if row.status == "completed" else None
        row.valid_until, row.completed_at, row.heartbeat_at = valid_until, now(), now()
        # Keep the exact total (including lifecycle rows) from the last batch.
        row.progress = {**(row.progress or {}), "phase": row.status, "elapsed_seconds": round(time.monotonic()-started, 1)}
        db.commit()
    except EvaluationCancelled:
        db.rollback()
        finish(db, job_id, "cancelled")
    except Exception:
        db.rollback()
        logger.exception("Background evidence evaluation failed for job %s", job_id)
        finish(db, job_id, "failed", "Evidence evaluation failed. Retry after checking the worker.")


def finish(db, job_id, status, message=None):
    row = db.get(EvidenceEvaluation, job_id, with_for_update=True, populate_existing=True)
    if row is not None and row.status in ACTIVE:
        row.status, row.completed_at, row.result, row.error_message = status, now(), None, message
        db.commit()
