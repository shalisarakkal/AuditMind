"""Archive, restore and purge (Phase 2d part 2).

Archiving marks rows archived (archived_at, archive_batch_id) instead of
moving them, so it's a set of UPDATEs; every read path leaves archived rows
out. One archive action is a batch (models/archive.py); restore and purge act
on a whole batch.

Every job reads the ids of the rows it will change once, then works through
them CHUNK at a time, each chunk its own short transaction under the org's
lock (org_lock.py): an import into the org waits for one chunk, not the whole
job. The last step sweeps up anything added meanwhile and marks the item, in
one transaction. A job that stops half-way (the server restarted) resumes
when it's started again, since each step only picks rows it hasn't done.

- Archive an upload: its findings; the assets it created that no other active
  upload touched (asset_scans), and any findings left on those; then the
  upload itself. Changes it made to shared assets stay.
- Archive an asset: its findings, then the asset.
- Archive a manual finding (one with no upload): just that finding.
- Restore: assets, then findings, then the upload. A finding that now
  duplicates an active one (same asset, source and category, or description
  when uncategorised: import_matching.finding_key) is purged instead; one on
  an asset archived since (in another batch) moves to that batch, so it comes
  back with its asset. Restored rows keep their archive_batch_id (it's only
  read together with archived_at).
- Purge: delete the batch's findings, assets (with any findings still on
  them) and upload. Findings of that upload that live on elsewhere (restored
  with their asset) lose their link to it instead of being deleted.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.orm import Session

from app.models.archive import ArchiveBatch, ArchiveJob, AssetScan
from app.models.asset import Asset
from app.models.enums import ArchiveAction, ArchiveItemType, ArchiveProgress, ArchiveState, Criticality, ScanStatus
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services.events import record_event
from app.services.org_lock import ARCHIVE_JOB, job_running, lock_org, lock_org_jobs
from app.services.org_settings import resolve_ingestion_settings

logger = logging.getLogger(__name__)

# Rows per transaction.
CHUNK = 20_000

_ACTIVE_JOB = (ScanStatus.pending, ScanStatus.running)
# The state a batch is in while each action runs, and after.
_STATES = {
    ArchiveAction.archive: (ArchiveState.archiving, ArchiveState.archived),
    ArchiveAction.restore: (ArchiveState.restoring, ArchiveState.restored),
    ArchiveAction.purge: (ArchiveState.purging, ArchiveState.purged),
}


class ArchiveError(Exception):
    """The action can't be done (the message says why); `status` is the HTTP
    status to answer with."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Starting a job ---------------------------------------------------------


def start_archive(
    db: Session, org_id: uuid.UUID, item_type: ArchiveItemType, item_id: uuid.UUID, user_id: uuid.UUID | None
) -> ArchiveJob:
    """Create (or resume) the item's archive batch and a job to archive it.
    Committed; run it with run_job."""
    # Held until the job row is committed: two requests at once (a double
    # click) can't both find "no archive running" and start one each.
    lock_org_jobs(db, org_id)
    model = {ArchiveItemType.upload: Scan, ArchiveItemType.asset: Asset, ArchiveItemType.finding: Finding}[item_type]
    item = db.get(model, item_id)
    if item is None or item.org_id != org_id:
        raise ArchiveError(f"{item_type.value.capitalize()} not found", 404)
    if item.archived_at is not None:
        raise ArchiveError(f"This {item_type.value} is already archived")
    if item_type == ArchiveItemType.upload:
        if item.source != "upload":
            raise ArchiveError("Only uploads can be archived this way", 422)
        if item.status in _ACTIVE_JOB:
            raise ArchiveError("This upload is still being processed; archive it once it's finished")
    if item_type == ArchiveItemType.finding and item.scan_id is not None:
        raise ArchiveError(
            "Imported findings are archived with their upload or their asset, not one by one "
            "(importing the file again would re-create them)",
            422,
        )

    # An archive that stopped half-way resumes with its own batch.
    batch = db.scalars(
        select(ArchiveBatch).where(
            ArchiveBatch.org_id == org_id,
            ArchiveBatch.item_id == item_id,
            ArchiveBatch.state == ArchiveState.archiving,
        )
    ).first()
    if batch is None:
        batch = ArchiveBatch(
            org_id=org_id,
            item_type=item_type,
            item_id=item_id,
            label=_label(item_type, item),
            state=ArchiveState.archiving,
            created_by=user_id,
            created_at=_now(),
            counts={},
        )
        db.add(batch)
        db.flush()
    return _new_job(db, batch, ArchiveAction.archive, user_id)


def start_batch_job(
    db: Session, org_id: uuid.UUID, batch_id: uuid.UUID, action: ArchiveAction, user_id: uuid.UUID | None
) -> ArchiveJob:
    """A job to restore or purge an archived batch. Committed; run it with
    run_job. An archive that stopped part-way can be restored too ("Undo"):
    that brings back what it had archived."""
    # As in start_archive: e.g. a purge by hand while the daily purge runs.
    lock_org_jobs(db, org_id)
    batch = db.get(ArchiveBatch, batch_id)
    if batch is None or batch.org_id != org_id:
        raise ArchiveError("Archived item not found", 404)
    running, _done = _STATES[action]
    allowed = {ArchiveState.archived, running}
    if action == ArchiveAction.restore:
        allowed.add(ArchiveState.archiving)
    if batch.state not in allowed:
        raise ArchiveError(f"This item is {batch.state.value}, so it can't be {_past(action)}")
    return _new_job(db, batch, action, user_id)


def _new_job(db: Session, batch: ArchiveBatch, action: ArchiveAction, user_id: uuid.UUID | None) -> ArchiveJob:
    from app.services.knowledge_service import KnowledgeError, require_active_org
    try:
        require_active_org(db, batch.org_id, lock=True)
    except KnowledgeError as exc:
        raise ArchiveError(str(exc)) from exc
    lock_org_jobs(db, batch.org_id)  # already held by the callers; taken again is a no-op
    busy = db.scalars(
        select(ArchiveJob.id).where(ArchiveJob.batch_id == batch.id, ArchiveJob.status.in_(_ACTIVE_JOB))
    ).first()
    if busy is not None:
        raise ArchiveError("Another archive, restore or purge of this item is already running")
    job = ArchiveJob(
        org_id=batch.org_id,
        batch_id=batch.id,
        action=action,
        status=ScanStatus.pending,
        started_by=user_id,
        started_at=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def unfinished_archives(
    db: Session, org_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[ArchiveProgress, uuid.UUID]]:
    """Of these items (a list page's rows), those whose archive hasn't
    finished (running now, or stopped part-way), and its batch."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(ArchiveBatch.item_id, ArchiveBatch.id, ArchiveJob.id)
        .outerjoin(ArchiveJob, and_(ArchiveJob.batch_id == ArchiveBatch.id, ArchiveJob.status.in_(_ACTIVE_JOB)))
        .where(
            ArchiveBatch.org_id == org_id,
            ArchiveBatch.state == ArchiveState.archiving,
            ArchiveBatch.item_id.in_(item_ids),
        )
    )
    found: dict[uuid.UUID, tuple[ArchiveProgress, uuid.UUID]] = {}
    for item_id, batch_id, job_id in rows:
        if job_id is not None or item_id not in found:
            progress = ArchiveProgress.running if job_id is not None else ArchiveProgress.stopped
            found[item_id] = (progress, batch_id)
    return found


def archiving_fields(unfinished: dict, item_id: uuid.UUID) -> dict:
    """A list row's `archiving` and `archiving_batch_id` (see
    unfinished_archives)."""
    progress, batch_id = unfinished.get(item_id, (None, None))
    return {"archiving": progress, "archiving_batch_id": batch_id}


def running_actions(db: Session, batch_ids: list[uuid.UUID]) -> dict[uuid.UUID, ArchiveAction]:
    """Of these batches, those a job is working on now, and what it does."""
    if not batch_ids:
        return {}
    rows = db.execute(
        select(ArchiveJob.batch_id, ArchiveJob.action).where(
            ArchiveJob.batch_id.in_(batch_ids), ArchiveJob.status.in_(_ACTIVE_JOB)
        )
    )
    return dict(rows.tuples().all())


def estimated_rows(db: Session, job: ArchiveJob) -> int:
    """About how many rows the job touches: decides whether it runs during
    the request or in the background."""
    batch = db.get(ArchiveBatch, job.batch_id)
    if job.action != ArchiveAction.archive:
        # Counted, not taken from batch.counts: an archive that stopped
        # part-way (Undo) never recorded its counts.
        return 1 + sum(
            db.scalar(select(func.count()).where(model.archive_batch_id == batch.id, model.archived_at.is_not(None)))
            for model in (Asset, Finding, Scan)
        )
    if batch.item_type == ArchiveItemType.upload:
        findings = db.scalar(select(func.count()).where(Finding.scan_id == batch.item_id))
        assets = db.scalar(select(func.count()).where(AssetScan.scan_id == batch.item_id))
        return findings + assets + 1
    if batch.item_type == ArchiveItemType.asset:
        return db.scalar(select(func.count()).where(Finding.asset_id == batch.item_id)) + 1
    return 1


def _label(item_type: ArchiveItemType, item) -> str:
    if item_type == ArchiveItemType.upload:
        label = item.filename or item.scan_type
    elif item_type == ArchiveItemType.asset:
        label = item.hostname or item.ip or item.cloud_id or "Unnamed asset"
    else:
        label = item.description or item.category or "Finding"
    return label[:255]


def _past(action: ArchiveAction) -> str:
    return {ArchiveAction.archive: "archived", ArchiveAction.restore: "restored", ArchiveAction.purge: "purged"}[
        action
    ]


# --- Running a job ------------------------------------------------------------


Progress = Callable[[str, int, int], None]


def claim_job(db: Session, job_id: uuid.UUID) -> bool:
    """Take a pending job to run it here: True if this caller got it. The
    background worker and a request that runs a small job itself both claim
    first, so a job never runs twice."""
    claimed = db.execute(
        update(ArchiveJob)
        .where(ArchiveJob.id == job_id, ArchiveJob.status == ScanStatus.pending)
        .values(status=ScanStatus.running)
    ).rowcount
    db.commit()
    return claimed == 1


def run_job(db: Session, job_id: uuid.UUID) -> ArchiveJob:
    """Carry out a claimed job (claim_job), committing a chunk at a time. On
    an unexpected error the job is marked failed and the batch stays
    mid-way, to be resumed by starting the same action again. Either way
    one Activity event records it, saved with the job's outcome."""
    job = db.get(ArchiveJob, job_id)
    batch = db.get(ArchiveBatch, job.batch_id)
    running, done = _STATES[job.action]
    # Restoring an archive that never finished is its Undo.
    undo = job.action == ArchiveAction.restore and batch.state == ArchiveState.archiving
    job.status = ScanStatus.running
    job.run_started_at = _now()
    batch.state = running
    db.commit()
    # Held while it runs: the background worker then knows it isn't dead
    # (see org_lock.job_running).
    with job_running(db, ARCHIVE_JOB, job_id):
        runner = _Runner(db, job, batch)
        try:
            summary = {
                ArchiveAction.archive: runner.archive,
                ArchiveAction.restore: runner.restore,
                ArchiveAction.purge: runner.purge,
            }[job.action]()
        except Exception:
            db.rollback()
            logger.exception("Archive job %s (%s) failed", job_id, job.action.value)
            job = db.get(ArchiveJob, job_id)
            job.status = ScanStatus.failed
            job.summary = {"error": "Couldn't finish: start it again to carry on from where it stopped"}
            job.completed_at = _now()
            job.progress = None
            _record(db, job, db.get(ArchiveBatch, job.batch_id), undo, details={"error": job.summary["error"]})
            db.commit()
            return job
        batch.state = done
        job.status = ScanStatus.completed
        job.summary = summary
        job.completed_at = _now()
        job.progress = None
        _record(db, job, batch, undo)
        db.commit()
        if sum(v for v in summary.values() if isinstance(v, int)) > CHUNK:
            # Lists, the dashboard and imports get good plans straight away.
            runner.analyze()
        db.refresh(job)
        return job


def fail_job(db: Session, job: ArchiveJob, message: str) -> None:
    """Mark a job that can't carry on failed, with its Activity event. Its
    batch stays mid-way: starting the same action again resumes it."""
    batch = db.get(ArchiveBatch, job.batch_id)
    undo = job.action == ArchiveAction.restore and batch.state == ArchiveState.archiving
    job.status = ScanStatus.failed
    job.summary = {"error": message}
    job.completed_at = _now()
    job.progress = None
    _record(db, job, batch, undo, details={"error": message})
    db.commit()


def _record(db: Session, job: ArchiveJob, batch: ArchiveBatch, undo: bool, details: dict | None = None) -> None:
    """The job's Activity event. Criticality: purge Critical; a restore
    that purged duplicates, and any failure, Warning; else Info."""
    summary = job.summary or {}
    counts = {k: v for k, v in summary.items() if isinstance(v, int) and v}
    extra = {"item_type": batch.item_type.value, **({"undo": True} if undo else {}), **(details or {})}
    if job.run_started_at and (waited := job.run_started_at - job.started_at).total_seconds() >= 1:
        extra["waited_seconds"] = round(waited.total_seconds())
    record_event(
        db,
        job.action.value,
        org_id=job.org_id,
        actor=db.get(User, job.started_by) if job.started_by else None,
        item=batch.label,
        started_at=job.run_started_at or job.started_at,
        ended_at=job.completed_at,
        outcome="completed" if job.status == ScanStatus.completed else "failed",
        criticality=Criticality.warning if summary.get("duplicates_purged") else None,
        counts=counts,
        details=extra,
    )


class _Runner:
    def __init__(self, db: Session, job: ArchiveJob, batch: ArchiveBatch):
        self.db = db
        self.job = job
        self.batch = batch
        self.org_id = batch.org_id
        self.params = {"b": batch.id, "item": batch.item_id, "now": batch.created_at}

    def _ids(self, sql: str) -> list[uuid.UUID]:
        """The rows a step will do, read once: re-reading them for each chunk
        would walk past the rows already done every time."""
        return list(self.db.scalars(text(sql), self.params))

    def _in_chunks(self, phase: str, ids: list[uuid.UUID], sql: str) -> int:
        """Run `sql` (which acts on `:ids`) CHUNK ids at a time, each chunk its
        own transaction under the org's lock. Returns the rows it changed."""
        done = 0
        for start in range(0, len(ids), CHUNK):
            lock_org(self.db, self.org_id)
            done += self.db.execute(text(sql), {**self.params, "ids": ids[start : start + CHUNK]}).rowcount
            self.job.progress = {"phase": phase, "rows_done": min(start + CHUNK, len(ids)), "rows_total": len(ids)}
            self.db.commit()
        return done

    def _finish(self, *statements: str) -> None:
        """The last step, in one transaction under the lock (committed by
        run_job): sweeps up rows added since the ids were read, and marks the
        item itself."""
        lock_org(self.db, self.org_id)
        for sql in statements:
            self.db.execute(text(sql), self.params)

    def _count(self, sql: str) -> int:
        return self.db.execute(text(sql), self.params).scalar_one()

    def analyze(self) -> None:
        """Refresh Postgres's statistics on the big tables. After a job moves
        a million rows in or out of the archive, they're far off until
        autovacuum catches up, and the planner then picks plans meant for a
        small table (measured: a restore chunk's duplicate check took minutes
        instead of 0.6 s). A few seconds even at millions of rows."""
        self.db.execute(text("ANALYZE findings, assets"))
        self.db.commit()

    def _archived_counts(self) -> dict[str, int]:
        return {
            name: self._count(f"SELECT count(*) FROM {table} WHERE archive_batch_id = :b AND archived_at IS NOT NULL")
            for name, table in (("uploads", "scans"), ("assets", "assets"), ("findings", "findings"))
        }

    # --- archive

    def archive(self) -> dict:
        kind = self.batch.item_type
        mark = "SET archived_at = :now, archive_batch_id = :b"
        active_ids = "id = ANY(:ids) AND archived_at IS NULL"
        # Findings left on the batch's archived assets (added by hand, say).
        on_batch_assets = (
            "SELECT f.id FROM assets a JOIN findings f ON f.asset_id = a.id "
            "WHERE a.archive_batch_id = :b AND a.archived_at IS NOT NULL AND f.archived_at IS NULL"
        )
        if kind == ArchiveItemType.upload:
            ids = self._ids("SELECT id FROM findings WHERE scan_id = :item AND archived_at IS NULL")
            self._in_chunks("findings", ids, f"UPDATE findings {mark} WHERE {active_ids}")
            # Assets the upload created (never ones it only matched or
            # updated) that no other active upload touched; checked again as
            # each chunk is archived.
            only_this_upload = (
                "NOT EXISTS (SELECT 1 FROM asset_scans o JOIN scans os ON os.id = o.scan_id "
                "WHERE o.asset_id = assets.id AND o.scan_id <> :item AND os.archived_at IS NULL)"
            )
            ids = self._ids(
                "SELECT a.id FROM asset_scans l JOIN assets a ON a.id = l.asset_id "
                "WHERE l.scan_id = :item AND l.created AND a.archived_at IS NULL"
            )
            self._in_chunks("assets", ids, f"UPDATE assets {mark} WHERE {active_ids} AND {only_this_upload}")
            # Usually none: the upload's own findings are done already.
            self._finish(
                f"UPDATE findings {mark} WHERE id IN ({on_batch_assets})",
                f"UPDATE findings {mark} WHERE scan_id = :item AND archived_at IS NULL",
                f"UPDATE scans {mark} WHERE id = :item AND archived_at IS NULL",
            )
        elif kind == ArchiveItemType.asset:
            ids = self._ids("SELECT id FROM findings WHERE asset_id = :item AND archived_at IS NULL")
            self._in_chunks("findings", ids, f"UPDATE findings {mark} WHERE {active_ids}")
            self._finish(
                f"UPDATE assets {mark} WHERE id = :item AND archived_at IS NULL",
                f"UPDATE findings {mark} WHERE asset_id = :item AND archived_at IS NULL",
            )
        else:
            self._finish(f"UPDATE findings {mark} WHERE id = :item AND archived_at IS NULL")
        self.batch.counts = self._archived_counts()
        return dict(self.batch.counts)

    # --- restore

    def restore(self) -> dict:
        counts = self._archived_counts()
        in_batch = "archive_batch_id = :b AND archived_at IS NOT NULL"
        ids = self._ids(f"SELECT id FROM assets WHERE {in_batch}")
        self._in_chunks("assets", ids, "UPDATE assets SET archived_at = NULL WHERE id = ANY(:ids)")

        ids = self._ids(f"SELECT id FROM findings WHERE {in_batch}")
        if len(ids) > CHUNK:
            # The duplicate check below needs current statistics.
            self.analyze()
        # Each chunk in one transaction, under the lock: nothing else can take
        # these findings out of the batch meanwhile, so the statements go by
        # id alone. (Repeating "in this batch" made Postgres combine the
        # batch's whole index with the ids and recheck every row of the batch
        # against the chunk: minutes per chunk for a million-row batch.)
        moved = duplicates = restored = 0
        for start in range(0, len(ids), CHUNK):
            lock_org(self.db, self.org_id)
            params = {**self.params, "ids": ids[start : start + CHUNK]}
            # A finding on an asset archived since (in another batch) moves to
            # that batch, to come back with it.
            gone = self.db.scalars(
                text(
                    "UPDATE findings f SET archive_batch_id = a.archive_batch_id FROM assets a "
                    "WHERE f.id = ANY(:ids) AND a.id = f.asset_id AND a.archived_at IS NOT NULL "
                    "AND a.archive_batch_id IS DISTINCT FROM :b RETURNING f.id"
                ),
                params,
            ).all()
            moved += len(gone)
            if gone:
                params["ids"] = list(set(params["ids"]) - set(gone))
            # One that duplicates an active finding is purged instead.
            duplicates += self.db.execute(
                text(
                    "DELETE FROM findings f WHERE f.id = ANY(:ids) AND f.archived_at IS NOT NULL "
                    "AND f.workflow_version = 0 "
                    "AND f.source IS NOT NULL AND EXISTS (SELECT 1 FROM findings g "
                    "WHERE g.org_id = f.org_id AND g.asset_id IS NOT DISTINCT FROM f.asset_id "
                    "AND g.archived_at IS NULL AND g.source = f.source "
                    "AND g.category IS NOT DISTINCT FROM f.category "
                    "AND (f.category IS NOT NULL OR g.description IS NOT DISTINCT FROM f.description))"
                ),
                params,
            ).rowcount
            restored += self.db.execute(
                text("UPDATE findings SET archived_at = NULL WHERE id = ANY(:ids) AND archived_at IS NOT NULL"), params
            ).rowcount
            self.job.progress = {"phase": "findings", "rows_done": min(start + CHUNK, len(ids)), "rows_total": len(ids)}
            self.db.commit()
        self._finish(f"UPDATE scans SET archived_at = NULL WHERE {in_batch}")
        return {
            "uploads": counts["uploads"],
            "assets": counts["assets"],
            "findings": restored,
            "duplicates_purged": duplicates,
            # Still archived, with the asset they're on.
            "findings_kept_with_asset": moved,
        }

    # --- purge

    def purge(self) -> dict:
        in_batch = "archive_batch_id = :b AND archived_at IS NOT NULL"
        # Only rows still archived: never one restored meanwhile.
        by_id = "id = ANY(:ids) AND archived_at IS NOT NULL"
        findings = self._in_chunks(
            "findings", self._ids(f"SELECT id FROM findings WHERE {in_batch}"), f"DELETE FROM findings WHERE {by_id}"
        )
        # Findings still on the batch's assets (archived with an upload that
        # shared them) go with them: deleted here so they're counted.
        findings += self._in_chunks(
            "findings",
            self._ids(
                "SELECT f.id FROM assets a JOIN findings f ON f.asset_id = a.id "
                "WHERE a.archive_batch_id = :b AND a.archived_at IS NOT NULL"
            ),
            f"DELETE FROM findings WHERE {by_id}",
        )
        assets = self._in_chunks(
            "assets", self._ids(f"SELECT id FROM assets WHERE {in_batch}"), f"DELETE FROM assets WHERE {by_id}"
        )
        # The upload's findings that live on (restored with their asset) keep
        # their data but lose the link to it.
        self._in_chunks(
            "saving",
            self._ids(
                "SELECT f.id FROM scans s JOIN findings f ON f.scan_id = s.id "
                "WHERE s.archive_batch_id = :b AND s.archived_at IS NOT NULL"
            ),
            "UPDATE findings SET scan_id = NULL WHERE id = ANY(:ids)",
        )
        uploads = self._count(f"SELECT count(*) FROM scans WHERE {in_batch}")
        self._finish(f"DELETE FROM scans WHERE {in_batch}")
        purged = {"uploads": uploads, "assets": assets, "findings": findings}
        return purged


# --- Auto-purge ---------------------------------------------------------------


def purge_at(org: Organization, archived_at: datetime) -> datetime:
    """When an item archived at `archived_at` is purged automatically."""
    return archived_at + timedelta(days=resolve_ingestion_settings(org).archive_retention_days)


def purge_expired(db: Session, now: datetime | None = None, queue: bool = False) -> int:
    """Purge every archived item past its org's retention; returns how many.
    Run by scripts/purge_expired.py; each purge is an Activity event by
    "System". `queue`: only queue the purges (the background worker's daily
    run), as low-priority jobs it takes when nothing else waits; returns how
    many were queued. An archived org is left as it is (read-only, kept
    whole until the Sysadmin restores or purges it)."""
    now = now or _now()
    purged = 0
    for org in db.scalars(
        select(Organization).where(Organization.archived_at.is_(None), Organization.purge_requested_at.is_(None))
    ).all():
        cutoff = now - timedelta(days=resolve_ingestion_settings(org).archive_retention_days)
        due = db.scalars(
            select(ArchiveBatch.id).where(
                ArchiveBatch.org_id == org.id,
                ArchiveBatch.state.in_((ArchiveState.archived, ArchiveState.purging)),
                ArchiveBatch.created_at < cutoff,
            )
        ).all()
        for batch_id in due:
            try:
                job = start_batch_job(db, org.id, batch_id, ArchiveAction.purge, None)
            except ArchiveError as exc:  # e.g. someone is restoring it right now
                db.rollback()
                logger.info("Auto-purge skipped batch %s: %s", batch_id, exc)
                continue
            if queue:
                purged += 1
            elif claim_job(db, job.id) and run_job(db, job.id).status == ScanStatus.completed:
                purged += 1
    return purged
