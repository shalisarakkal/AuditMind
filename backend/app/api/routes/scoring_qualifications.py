"""Scope-bound evidence review, durable evaluation and opt-in Dashboard scoring."""
import uuid
import json
import logging
from datetime import datetime, timezone

import anyio
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.types import Receive, Scope, Send
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.enums import Domain, UserRole
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.user import User
from app.models.evidence_evaluation import EvidenceEvaluation
from app.models.membership import OrgMembership
from app.models.scoring_qualification import DomainEvidenceQualification, OrganizationScoringSettings
from app.schemas.scoring_qualification import QualificationDraftUpdate, QualificationRead, QualificationReview, QualificationRevocation, ScoringSettingsRead, ScoringSettingsUpdate
from app.services.evidence_policy import POLICY_VERSION, PROFILES
from app.services import dashboard_evidence as evidence
from app.services import evidence_jobs
from app.schemas.evidence_evaluation import EvidenceEvaluationRead
from app.services.events import record_event
from app.services.org_lock import lock_org, lock_org_jobs

router = APIRouter(prefix="/orgs/{org_id}/scoring", tags=["scoring qualifications"])


def admit_computation(db, org_id, member):
    # Compute-only jobs preserve member/sysadmin read access, while fencing
    # organization lifecycle and rechecking account/access after a lock wait.
    from app.api.deps import authorize_org_write
    if isinstance(member, OrgMembership):
        return authorize_org_write(db, org_id, member.user_id, tuple(UserRole))
    lock_org_jobs(db, org_id)
    org = db.scalar(select(Organization).where(Organization.id == org_id)
        .with_for_update(key_share=True).execution_options(populate_existing=True))
    user = db.get(User, member.user_id, populate_existing=True)
    if org is None or org.purge_requested_at is not None or user is None or not user.is_active or not user.is_sysadmin:
        raise HTTPException(403, "Organization access changed; reload before retrying")
    if org.archived_at is not None:
        raise HTTPException(409, "Archived organizations cannot start or change evaluation jobs")
    return member


def job_response(db, row, member):
    current = evidence_jobs.valid_result(row, evidence_jobs.revision(db, row.org_id))
    return {name: getattr(row, name) for name in ("id", "org_id", "status", "created_at", "run_started_at",
        "completed_at", "cancel_requested_at", "progress", "error_message")} | {
        "is_current": current, "result": row.result if current else None,
        "can_cancel": row.status in evidence_jobs.ACTIVE and (member.role == UserRole.admin or row.started_by == member.user_id)}


@router.get("/dashboard-state")
def dashboard_state(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                    _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return consistent_read(db, org_id, evidence_jobs.dashboard_state)


@router.post("/evaluations", response_model=EvidenceEvaluationRead, status_code=202)
def queue_evaluation(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                     member: OrgMembership = Depends(require_org_member)):
    member = admit_computation(db, org_id, member)
    row = evidence_jobs.enqueue(db, org_id, member.user_id)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return job_response(db, row, member)


@router.get("/evaluations/current", response_model=EvidenceEvaluationRead | None)
def latest_evaluation(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                      member: OrgMembership = Depends(require_org_member)):
    row = db.scalar(select(EvidenceEvaluation).where(EvidenceEvaluation.org_id == org_id)
        .order_by(EvidenceEvaluation.created_at.desc(), EvidenceEvaluation.id).limit(1))
    response.headers["Cache-Control"] = "no-store"
    return job_response(db, row, member) if row else None


def get_job(db, org_id, job_id):
    row = db.scalar(select(EvidenceEvaluation).where(EvidenceEvaluation.id == job_id,
        EvidenceEvaluation.org_id == org_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Evidence evaluation not found")
    return row


@router.get("/evaluations/{job_id}", response_model=EvidenceEvaluationRead)
def read_evaluation(org_id: uuid.UUID, job_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                    member: OrgMembership = Depends(require_org_member)):
    row = db.scalar(select(EvidenceEvaluation).where(EvidenceEvaluation.id == job_id,
        EvidenceEvaluation.org_id == org_id))
    if row is None:
        raise HTTPException(404, "Evidence evaluation not found")
    response.headers["Cache-Control"] = "no-store"
    return job_response(db, row, member)


@router.post("/evaluations/{job_id}/cancel", response_model=EvidenceEvaluationRead)
def cancel_evaluation(org_id: uuid.UUID, job_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                       member: OrgMembership = Depends(require_org_member)):
    member = admit_computation(db, org_id, member)
    row = get_job(db, org_id, job_id)
    if member.role != UserRole.admin and row.started_by != member.user_id:
        raise HTTPException(403, "Only the requester or an organization administrator can cancel this evaluation")
    if row.status in evidence_jobs.ACTIVE:
        row.cancel_requested_at = datetime.now(timezone.utc)
        if row.status == "pending":
            row.status, row.completed_at = "cancelled", row.cancel_requested_at
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return job_response(db, row, member)


class _ClosingStreamingResponse(StreamingResponse):
    """Close the synchronous snapshot iterator even when sending is cancelled.

    StreamingResponse's thread-pool adapter does not close its underlying sync
    iterator on disconnect. Explicit, shielded cleanup releases its cursor and
    transaction after any currently executing fetch has returned.
    """

    def __init__(self, iterator, **kwargs):
        self._snapshot_iterator = iterator
        super().__init__(iterator, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(self._snapshot_iterator.close)


@router.get("/progress/{operation}")
def scoring_progress(org_id: uuid.UUID, operation: str, db: Session = Depends(get_db),
                     _: OrgMembership = Depends(require_org_member)):
    if operation not in ("inventory", "evaluation"):
        raise HTTPException(404, "Unknown evidence operation")
    engine = db.get_bind()
    # Authorization reads are complete. Do not retain a second idle transaction
    # and pool connection for the entire duration of the streamed snapshot.
    db.rollback()

    def stream():
        try:
            with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
                with Session(bind=connection) as snapshot:
                    for event in evidence.inventory_progress(snapshot, org_id):
                        if event["type"] == "result" and operation == "evaluation":
                            yield json.dumps({"type": "progress", "phase": "qualifications"}) + "\n"
                            event = {"type": "result", "data": evidence.evaluate_org(snapshot, org_id, scope=event["data"])}
                        yield json.dumps(event, default=str) + "\n"
        except Exception:
            logging.getLogger(__name__).exception("Evidence progress request failed")
            yield json.dumps({"type": "error", "message": "Evidence evaluation failed. Please retry; no scoring changes were made."}) + "\n"

    return _ClosingStreamingResponse(stream(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.get("/profiles")
def read_profiles(org_id: uuid.UUID, _: OrgMembership = Depends(require_org_member)):
    return {"policy_version": POLICY_VERSION, "profiles": PROFILES}


def finding_source(db: Session, org_id: uuid.UUID, source_id: uuid.UUID) -> tuple[Finding, str]:
    try:
        return evidence.finding_source(db, org_id, source_id)
    except evidence.EvidenceSourceError as exc:
        raise HTTPException(404, str(exc)) from exc


def consistent_read(db, org_id, evaluator):
    # Membership was checked by the route; all scope/source/review rows are read
    # from one snapshot without holding long inventory-blocking row locks.
    with db.get_bind().connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            return evaluator(snapshot, org_id)


def settings_response(row: OrganizationScoringSettings | None) -> dict:
    return {"evidence_qualified_enabled": row.evidence_qualified_enabled if row else False,
            "version": row.version if row else 0, "available": True}


@router.get("/settings", response_model=ScoringSettingsRead)
def read_settings(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                  _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return settings_response(db.get(OrganizationScoringSettings, org_id))


@router.patch("/settings", response_model=ScoringSettingsRead)
def save_settings(org_id: uuid.UUID, payload: ScoringSettingsUpdate, response: Response,
                  db: Session = Depends(get_db), admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    row = db.get(OrganizationScoringSettings, org_id, with_for_update=True, populate_existing=True)
    if payload.expected_version != (row.version if row else 0):
        raise HTTPException(409, "Scoring settings changed; reload before retrying")
    if row is None:
        row = OrganizationScoringSettings(org_id=org_id, evidence_qualified_enabled=payload.evidence_qualified_enabled, version=1)
        db.add(row)
        record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                     item="Dashboard scoring settings", details={"from": False, "enabled": payload.evidence_qualified_enabled, "version": 1})
    elif row.evidence_qualified_enabled != payload.evidence_qualified_enabled:
        previous = row.evidence_qualified_enabled
        row.evidence_qualified_enabled = payload.evidence_qualified_enabled
        row.version += 1
        record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                     item="Dashboard scoring settings", details={"from": previous, "enabled": row.evidence_qualified_enabled, "version": row.version})
    result = settings_response(row)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/source-findings/{finding_id}")
def source_binding(org_id: uuid.UUID, finding_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                   _: OrgMembership = Depends(require_org_member)):
    finding, digest = finding_source(db, org_id, finding_id)
    response.headers["Cache-Control"] = "no-store"
    return {"source_type": "finding", "source_id": finding_id, "domain": finding.domain,
            "source_sha256": digest, "binding_version": "dashboard-finding-v1"}


@router.get("/source-documents/{version_id}")
def document_binding(org_id: uuid.UUID, version_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                     _: OrgMembership = Depends(require_org_member)):
    try:
        _, digest = evidence.document_source(db, org_id, version_id)
    except evidence.EvidenceSourceError as exc:
        raise HTTPException(404, str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    return {"source_type": "document_version", "source_id": version_id,
            "source_sha256": digest, "binding_version": "dashboard-document-v1"}


@router.get("/inventory-scope")
def inventory_binding(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                      _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return consistent_read(db, org_id, evidence.inventory_scope)


@router.get("/evaluation")
def evaluation(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
               _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return consistent_read(db, org_id, evidence.evaluate_org)


@router.get("/qualifications", response_model=list[QualificationRead])
def list_drafts(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return db.scalars(select(DomainEvidenceQualification).where(
        DomainEvidenceQualification.org_id == org_id).order_by(DomainEvidenceQualification.domain)).all()


@router.put("/qualifications/{domain}", response_model=QualificationRead)
def save_draft(org_id: uuid.UUID, domain: Domain, payload: QualificationDraftUpdate,
               response: Response, db: Session = Depends(get_db),
               admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    try:
        payload.validate_domain(domain)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = db.scalar(select(DomainEvidenceQualification).where(
        DomainEvidenceQualification.org_id == org_id, DomainEvidenceQualification.domain == domain)
        .with_for_update().execution_options(populate_existing=True))
    if payload.expected_version != (row.version if row else 0):
        raise HTTPException(409, "Qualification changed; reload before retrying")
    if row is not None and row.status == "approved":
        raise HTTPException(409, "Revoke this approval before editing its evidence")
    lock_org(db, org_id)
    if payload.inventory_sha256 is not None and payload.inventory_sha256 != evidence.inventory_scope(db, org_id)["inventory_sha256"]:
        raise HTTPException(409, "Inventory changed; reload scope before retrying")
    now = datetime.now(timezone.utc)
    for observation in payload.observations:
        try:
            digest = evidence.source_digest(db, org_id, domain, observation, lock=True)
        except evidence.EvidenceSourceError as exc:
            raise HTTPException(404, str(exc)) from exc
        if digest != observation.source_sha256:
            raise HTTPException(409, "Evidence source changed or belongs to another domain; reload before retrying")
        if observation.observed_at > now:
            raise HTTPException(422, "Observation date cannot be in the future")
    before = QualificationRead.model_validate(row).model_dump(mode="json") if row else None
    if row is None:
        row = DomainEvidenceQualification(org_id=org_id, domain=domain, version=0)
        db.add(row)
    row.policy_version = POLICY_VERSION
    row.scope, row.rationale = payload.scope, payload.rationale
    row.observations = [o.model_dump(mode="json") for o in payload.observations]
    row.inventory_sha256 = payload.inventory_sha256
    row.reviewed_by = row.reviewed_at = row.expires_at = row.review_note = None
    row.review_attestation = {}
    row.status, row.version = "draft", row.version + 1
    row.updated_by, row.updated_at = admin.user_id, now
    db.flush()
    result = QualificationRead.model_validate(row)
    record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
                 item="Evidence qualification draft", details={"before": before, "after": result.model_dump(mode="json")})
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


def locked_qualification(db, org_id, domain, expected_version):
    row = db.scalar(select(DomainEvidenceQualification).where(
        DomainEvidenceQualification.org_id == org_id, DomainEvidenceQualification.domain == domain)
        .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "Qualification not found")
    if row.version != expected_version:
        raise HTTPException(409, "Qualification changed; reload before retrying")
    return row


def persist_review(db, org_id, row, admin, before, response):
    row.version += 1
    row.updated_by, row.updated_at = admin.user_id, datetime.now(timezone.utc)
    db.flush()
    result = QualificationRead.model_validate(row)
    record_event(db, "settings_changed", org_id=org_id, actor=admin.user,
        item="Evidence qualification review", details={"before": before, "after": result.model_dump(mode="json")})
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/qualifications/{domain}/review", response_model=QualificationRead)
def review(org_id: uuid.UUID, domain: Domain, payload: QualificationReview, response: Response,
           db: Session = Depends(get_db), admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    row = locked_qualification(db, org_id, domain, payload.expected_version)
    if row.status != "draft":
        raise HTTPException(409, "Only a draft can be reviewed; revoke/edit before another review")
    if not (payload.operational_review and payload.covers_entire_inventory and payload.conflicts_reviewed):
        raise HTTPException(422, "Explicit operational, complete-inventory and conflict review attestations are required")
    lock_org(db, org_id)
    scope = evidence.inventory_scope(db, org_id)
    if not row.inventory_sha256 or row.inventory_sha256 != payload.inventory_sha256 or row.inventory_sha256 != scope["inventory_sha256"]:
        raise HTTPException(409, "Inventory is unbound or changed; rebind and review the draft")
    if scope["asset_count"] == 0 and scope["finding_count"] == 0:
        raise HTTPException(409, "An empty inventory cannot be qualified")
    if row.policy_version != POLICY_VERSION:
        raise HTTPException(409, "Evidence policy changed; update the draft before review")
    now = datetime.now(timezone.utc)
    try:
        observations = evidence.validate_observations(db, row, now, lock=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if not observations or not now < payload.expires_at <= now + evidence.MAX_AGE or any(
            payload.expires_at > o.observed_at.astimezone(timezone.utc) + evidence.MAX_AGE for o in observations):
        raise HTTPException(422, "Expiry must be future, within 90 days and within every observation's validity")
    if payload.decision == "approve" and {o.objective for o in observations} != set(PROFILES[domain.value]):
        raise HTTPException(409, "Every mandatory domain objective requires reviewed evidence")
    if payload.decision == "conflicting" and len({(o.source_type, o.source_id) for o in observations}) < 2:
        raise HTTPException(422, "Material conflicts require at least two source references and a review explanation")
    before = QualificationRead.model_validate(row).model_dump(mode="json")
    row.status = "approved" if payload.decision == "approve" else "conflicting"
    row.reviewed_by, row.reviewed_at, row.expires_at = admin.user_id, now, payload.expires_at
    row.review_note = payload.note
    row.review_attestation = {"operational_review": True, "covers_entire_inventory": True,
                             "conflicts_reviewed": True, "inventory": scope}
    return persist_review(db, org_id, row, admin, before, response)


@router.post("/qualifications/{domain}/revoke", response_model=QualificationRead)
def revoke(org_id: uuid.UUID, domain: Domain, payload: QualificationRevocation, response: Response,
           db: Session = Depends(get_db), admin: OrgMembership = Depends(require_org_role(UserRole.admin))):
    row = locked_qualification(db, org_id, domain, payload.expected_version)
    if row.status not in ("approved", "conflicting"):
        raise HTTPException(409, "Only reviewed qualifications can be revoked")
    before = QualificationRead.model_validate(row).model_dump(mode="json")
    row.status, row.review_note = "revoked", payload.note
    return persist_review(db, org_id, row, admin, before, response)
