"""Atomic, least-recently-served scheduling across organization scopes.

An organization occupies at most one queued-job slot. Its other jobs stay
pending rather than occupying workers waiting on the inventory lock. The actual
inventory locks still serialize against synchronous API operations.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import String, case, cast, func, literal, select, union_all, update
from sqlalchemy.dialects.postgresql import insert
from app.core.config import settings
from app.models.archive import ArchiveJob
from app.models.evidence_evaluation import EvidenceEvaluation
from app.models.knowledge import KnowledgeDocument, KnowledgeIndex, KnowledgeVersion
from app.models.organization import Organization
from app.models.report import Report
from app.models.scan import Scan
from app.models.worker_dispatch import WorkerDispatch
from app.models.dashboard_snapshot import DashboardSnapshot


def _scope(org):
    return func.coalesce(cast(org, String), literal("shared-standards"))


def claim(db, clock):
    # Only queue admission is serialized, never the actual processing. Commit
    # includes status + fair-state so simultaneous workers cannot over-admit.
    db.execute(select(func.pg_advisory_xact_lock(9, 0)))
    now = clock()
    documents = select(_scope(KnowledgeDocument.org_id)).select_from(KnowledgeIndex).join(
        KnowledgeVersion, KnowledgeVersion.id == KnowledgeIndex.version_id).join(
        KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id).where(KnowledgeIndex.status == "running")
    busy = union_all(
        *[select(_scope(model.org_id)).where(model.status == "running")
          for model in (Scan, ArchiveJob, Report, EvidenceEvaluation, DashboardSnapshot)], documents).subquery()
    busy_scopes = select(busy.c[0])
    # Also bound claims across processes during restarts/failover. Inline HTTP
    # jobs have no worker heartbeat and are not worker-pool reservations.
    reservations = union_all(*[select(model.id).where(model.status == "running", model.heartbeat_at.is_not(None))
        for model in (Scan, ArchiveJob, Report, KnowledgeIndex, EvidenceEvaluation, DashboardSnapshot)]).subquery()
    if db.scalar(select(func.count()).select_from(reservations)) >= settings.WORKER_CONCURRENCY:
        db.rollback()
        return None
    purging = select(Organization.id).where(Organization.purge_requested_at.is_not(None))
    candidates = []
    models = [("import", Scan, Scan.started_at, Scan.org_id),
              ("archive", ArchiveJob, ArchiveJob.started_at, ArchiveJob.org_id),
              ("report", Report, Report.created_at, Report.org_id),
              ("document", KnowledgeIndex, KnowledgeIndex.created_at, KnowledgeDocument.org_id),
              ("evidence", EvidenceEvaluation, EvidenceEvaluation.created_at, EvidenceEvaluation.org_id),
              ("dashboard", DashboardSnapshot, DashboardSnapshot.requested_at, DashboardSnapshot.org_id)]
    for kind, model, queued, org in models:
        scope = _scope(org)
        priority = literal(0)
        if kind == "archive":
            overdue = queued <= now - timedelta(minutes=settings.AUTO_PURGE_MAX_WAIT_MINUTES)
            priority = case((model.started_by.is_(None) & ~overdue, 1), else_=0)
        query = select(model.id, org.label("org_id"), scope.label("scope"), queued.label("queued"),
                       WorkerDispatch.last_started_at.label("last"), priority.label("priority")).select_from(model)
        if kind == "document":
            query = query.join(KnowledgeVersion, KnowledgeVersion.id == model.version_id).join(
                KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
        query = query.outerjoin(WorkerDispatch, WorkerDispatch.scope_id == scope).where(
            model.status == "pending", scope.not_in(busy_scopes), org.is_(None) | org.not_in(purging))
        if kind == "import":
            query = query.where(Scan.source == "upload")
        row = db.execute(query.order_by(priority, WorkerDispatch.last_started_at.asc().nulls_first(), queued, model.id)
                         .limit(1).with_for_update(of=model, skip_locked=True)).first()
        if row:
            candidates.append((kind, model, row))
    if not candidates:
        db.rollback()
        return None
    kind, model, row = min(candidates, key=lambda item: (item[2].priority,
        item[2].last or datetime.min.replace(tzinfo=timezone.utc), item[2].queued or now, str(item[2].id)))
    now = clock()  # Fresh heartbeat after selection/lock waits, not before them.
    values = dict(status="running", heartbeat_at=now)
    if kind in {"report", "document", "evidence", "dashboard"}:
        values["run_started_at"] = now
    db.execute(update(model).where(model.id == row.id).values(**values))
    db.execute(insert(WorkerDispatch).values(scope_id=row.scope, org_id=row.org_id, last_started_at=now)
               .on_conflict_do_update(index_elements=["scope_id"], set_={"last_started_at": now}))
    db.commit()  # Releases all other candidate locks as well.
    return kind, row.id
