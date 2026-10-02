"""File imports: asset inventories (CSV/JSON), findings (generic CSV/JSON,
native .nessus), and profile imports, where each row of a tool's export
becomes an asset plus any findings (import_profiles.py).

Flow (Phase 2f part 1): read the file a record at a time (import_readers)
and check each row, staging what it gives (import_staging); then publish it
all in one step under the org's lock: match each row's asset, write it and
its findings. Nothing is written before every row is checked, so the
all-or-nothing mode (per-org setting) never leaves a partial import behind,
and no one sees half an upload.

The background worker's imports stage in the database, a chunk at a time,
so one cut off carries on from where it got to; imports run in the request
(small files) stage in memory.

process_import() is the single entry point; it resolves the org's effective
settings and records the outcome on the scan.
"""

import dataclasses
import enum
import hashlib
import ipaddress
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from psycopg.types.json import Jsonb
from sqlalchemy import bindparam, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.models.archive import AssetScan
from app.models.asset import Asset
from app.models.enums import Criticality, Domain, ScanStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.schemas.ingestion import ImportReport, RowError, RowNote, RowWarning
from app.services import import_staging
from app.services.asset_types import BUILTIN_TYPE_ALIASES, resolve_asset_type
from app.services.events import record_event
from app.services.import_matching import TARGETED_LOAD_MAX, AssetIndex, FindingIndex, IndexedAsset, Origin, finding_key
from app.services.import_readers import FileReader, ImportFileError
from app.services.import_staging import Capped, ReadState, StagedRow
from app.services.nessus_parser import NessusItem, map_nessus_domain, map_nessus_severity
from app.services.org_lock import IMPORT_JOB, job_running, lock_org
from app.services.org_settings import IngestionSettings, resolve_ingestion_settings

logger = logging.getLogger(__name__)

ImportKind = Literal["assets", "findings", "profile"]

# Assets created for findings whose host isn't in the inventory yet (a cloud
# resource when the finding names only a cloud ID). A guess: an inventory
# import later replaces it with the real category.
FINDING_ASSET_TYPE = "server"
FINDING_CLOUD_ASSET_TYPE = "cloud_resource"
# The report lists at most this many row errors (and warnings); `failed`
# still counts every error.
MAX_REPORTED_ERRORS = import_staging.MAX_LISTED
IDENTITY_REQUIRED = "hostname, ip or cloud_id is required"
# The columns a generic file identifies each row's host by. A generic import
# whose file has none of them is almost certainly the wrong source for it.
_IDENTITY_COLUMNS = {"hostname", "ip", "cloud_id"}
_EXPECTED_COLUMNS = {
    "assets": "type, hostname and/or ip or cloud_id, and optionally subtype, environment, criticality, tags",
    "findings": "hostname and/or ip or cloud_id, domain, severity, and optionally category, description, source",
}
# New rows sent to the database per batch, file rows per staged chunk, and
# file rows per progress report.
WRITE_BATCH = 2000
# Assets whose updates are gathered before they're sent (see _PendingWrites).
UPDATE_BATCH = 20000

_FORMATS: dict[ImportKind, dict[str, str]] = {
    "assets": {".csv": "csv", ".json": "json"},
    "findings": {".csv": "csv", ".json": "json", ".nessus": "nessus"},
    "profile": {".csv": "csv", ".json": "json"},
}
_SCAN_TYPES = {
    ("assets", "csv"): "asset_import",
    ("assets", "json"): "asset_import",
    ("findings", "csv"): "findings_csv",
    ("findings", "json"): "findings_json",
    ("findings", "nessus"): "nessus",
}


class IngestionError(Exception):
    """A problem with the file as a whole (wrong type, unparseable, empty)."""


@dataclass
class AssetRow:
    row: int
    type: str
    hostname: str | None
    ip: str | None
    cloud_id: str | None = None
    environment: str | None = None
    criticality: str | None = None
    tags: list[str] | None = None
    subtype: str | None = None
    details: dict = field(default_factory=dict)
    # False when the type is a guess (see Asset.type_known).
    type_known: bool = True


@dataclass
class FindingRow:
    row: int
    hostname: str | None
    ip: str | None
    domain: Domain
    severity: Severity
    category: str | None
    description: str | None
    source: str
    raw_data: dict = field(default_factory=dict)
    cloud_id: str | None = None
    # An event log's finding sums events up (event_sources.py).
    event_count: int | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    details: dict | None = None


# Told how a large import goes: (phase, done, total). Phases, in order:
# "reading" (file rows checked; the total is an estimate until the end),
# "waiting" (for another import into the org), "writing" (file rows
# written), "saving" (committing). done/total are 0 when there's no count.
ProgressCallback = Callable[[str, int, int], None]


class RowReader(Protocol):
    """How a profile import reads each record (see import_profiles.py)."""

    key: str
    # Findings-only profiles count findings as `created`, like /findings/import.
    creates_assets: bool
    # For JSON files: records may be wrapped as {json_list_key: [...]}.
    json_list_key: str

    def read_row(
        self, row: int, record: Any, ingestion: IngestionSettings, warnings: list[str]
    ) -> tuple[AssetRow | None, list[FindingRow]]: ...

    # Optional extras, found with getattr (see _RowChecker): start() gives
    # what reads one import's rows (an event log's profile gives a fresh
    # tally of its own); a reader that sums rows up (event logs, Phase 2f
    # part 2) has finish() -> list[StagedRow], called once every row is
    # read, and snapshot() -> dict / restore(dict), so what it has gathered
    # survives a resume.


# --- Formats ---------------------------------------------------------------


def detect_format(filename: str | None, kind: ImportKind) -> str:
    """File format from the extension. Raises IngestionError if unsupported."""
    allowed = _FORMATS[kind]
    match = re.search(r"\.[^.]+$", (filename or "").lower())
    if not match or match.group() not in allowed:
        raise IngestionError(f"Unsupported file type; expected {', '.join(allowed)}")
    return allowed[match.group()]


def scan_type_for(kind: ImportKind, fmt: str) -> str:
    return _SCAN_TYPES[(kind, fmt)]


def parse_csv(content: bytes) -> list[tuple[int, dict]]:
    """(line number, record) per data row; header names are case-insensitive."""
    return _read_all(content, "csv", "")


def parse_json(content: bytes, list_key: str) -> list[tuple[int, Any]]:
    """(1-based position, record) for a top-level list, or {list_key: [...]}."""
    return _read_all(content, "json", list_key)


def _read_all(content: bytes, fmt: str, list_key: str) -> list[tuple[int, Any]]:
    try:
        return list(FileReader(content, fmt, list_key).records())
    except ImportFileError as exc:
        raise IngestionError(str(exc))


# --- Row validation (raises ValueError with a message for the report) -------


def validate_asset(
    row: int,
    record: Any,
    type_aliases: dict[str, str] = BUILTIN_TYPE_ALIASES,
    warnings: list[str] | None = None,
    *,
    fallback_type: tuple[str, str | None] | None = None,
    details: dict | None = None,
) -> AssetRow:
    """`type` is a category or an alias for one (the alias becomes the subtype
    unless the record has one). fallback_type (category, subtype) is used when
    the record has no type, e.g. a type worked out from a scanned OS."""
    _require_object(record)
    raw_type = _text(record, "type", 100)
    if raw_type:
        asset_type, alias_subtype = resolve_asset_type(raw_type, type_aliases)
    elif fallback_type:
        asset_type, alias_subtype = fallback_type
    else:
        raise ValueError("type is required")
    hostname, ip, cloud_id = _identity(record, warnings)
    return AssetRow(
        row=row,
        type=asset_type,
        subtype=_text(record, "subtype", 100) or (alias_subtype[:100] if alias_subtype else None),
        hostname=hostname,
        ip=ip,
        cloud_id=cloud_id,
        environment=_text(record, "environment", 50),
        criticality=_text(record, "criticality", 50),
        tags=_tags(record.get("tags")),
        details=details or {},
    )


def validate_finding(row: int, record: Any, warnings: list[str] | None = None, raw: dict | None = None) -> FindingRow:
    """raw: what to keep as the finding's raw_data (default: the record)."""
    _require_object(record)
    hostname, ip, cloud_id = _identity(record, warnings)
    return FindingRow(
        row=row,
        hostname=hostname,
        ip=ip,
        cloud_id=cloud_id,
        domain=_enum(record, "domain", Domain),
        severity=_enum(record, "severity", Severity),
        category=_text(record, "category", 100),
        description=_text(record, "description"),
        source=_text(record, "source", 100) or "manual",
        raw_data=record if raw is None else raw,
    )


def nessus_finding(
    item: NessusItem, ingestion: IngestionSettings, warnings: list[str] | None = None
) -> FindingRow | None:
    """None for an Info item the org's settings skip."""
    severity = map_nessus_severity(item.severity, ingestion.nessus_info_severity)
    if severity is None:
        return None
    hostname, ip, _ = _identity({"hostname": item.hostname, "ip": item.ip}, warnings)

    location = f" ({item.port}/{item.protocol})" if item.port and item.port != "0" else ""
    description = item.plugin_name + (f": {item.synopsis}" if item.synopsis else "")
    return FindingRow(
        row=item.row,
        hostname=hostname,
        ip=ip,
        domain=map_nessus_domain(item.plugin_family, ingestion.nessus_domain_map, ingestion.nessus_default_domain),
        severity=severity,
        # Plugin + port identifies the finding on a host (the dedup key).
        category=f"Nessus {item.plugin_id}{location}"[:100],
        description=description or None,
        source="nessus",
        raw_data=item.raw,
    )


# --- Entry point -------------------------------------------------------------


def process_import(
    db: Session,
    scan: Scan,
    kind: ImportKind,
    fmt: str,
    source: bytes | Path,
    profile: RowReader | None = None,
    progress: ProgressCallback | None = None,
) -> ImportReport:
    """Import `source` into the scan's org and record the outcome on the scan
    (status, summary, completed_at). `source` is the file's content (run in
    the request: staged in memory) or its saved path (the background
    worker: staged in the database, resumable). kind "profile" reads each
    row with `profile`; `progress` is told how it goes. Unexpected errors
    mark the scan failed and are re-raised."""
    scan_id = scan.id
    org = db.get(Organization, scan.org_id)
    ingestion = resolve_ingestion_settings(org)
    scan.status = ScanStatus.running
    # Carrying on after a cut-off: it started when it first ran.
    scan.run_started_at = scan.run_started_at or datetime.now(timezone.utc)
    scan.progress = {"phase": "reading"}
    db.commit()

    # Held until the outcome is saved: the background worker then knows it
    # runs (see org_lock.job_running).
    with job_running(db, IMPORT_JOB, scan_id):
        try:
            report = _import(db, scan, kind, fmt, source, ingestion, profile, progress)
            # Failed if all-or-nothing rejected the file, or no row was usable.
            usable = report.created + report.updated + report.skipped + report.duplicates
            rejected = report.failed > 0 and (not ingestion.import_partial_success or usable == 0)
            status = ScanStatus.failed if rejected else ScanStatus.completed
        except IngestionError as exc:
            db.rollback()
            report = ImportReport(errors=[RowError(row=0, message=str(exc))])
            status = ScanStatus.failed
        except Exception:
            db.rollback()
            _finish(db, db.get(Scan, scan_id), ScanStatus.failed, {"error": "Unexpected error during import"})
            raise

        _finish(db, db.get(Scan, scan_id), status, report.model_dump(mode="json"))
        return report


# What an import report's counts are counts of, by kind of import (see
# ImportReport): an asset list counts assets; a findings file, findings; a
# tool export (import profile), assets and then findings. Activity events
# record them under these names, so "900 created" says what was created.
_EVENT_COUNTS = {
    "assets": {"created": "assets_created", "updated": "assets_updated", "skipped": "assets_skipped",
               "repeated": "rows_repeated", "failed": "rows_failed"},
    "findings": {"created": "findings_created", "duplicates": "duplicate_findings", "skipped": "items_skipped",
                 "failed": "rows_failed"},
    "profile": {"created": "assets_created", "updated": "assets_updated", "skipped": "assets_skipped",
                "repeated": "rows_repeated", "findings_created": "findings_created",
                "duplicates": "duplicate_findings", "failed": "rows_failed"},
}


# Import profiles that record findings only: their "created" counts findings.
FINDINGS_ONLY_SCAN_TYPES = (
    "findings_csv",
    "findings_json",
    "nessus",
    "generic_findings_import",
    # Event logs (Phase 2f part 2): findings that sum events up.
    "azure_activity_import",
    "aws_cloudtrail_import",
    "gcp_audit_import",
    "ossem_events_import",
)


def import_kind(scan_type: str) -> str:
    """assets, findings or profile (a tool export), from the scan's type."""
    if scan_type == "asset_import":
        return "assets"
    return "findings" if scan_type in FINDINGS_ONLY_SCAN_TYPES else "profile"


def event_counts(scan_type: str, summary: dict) -> dict:
    """An import report's non-zero counts under names saying what they count."""
    names = _EVENT_COUNTS[import_kind(scan_type)]
    return {names[key]: n for key, n in summary.items() if key in names and isinstance(n, int) and n}


def fail_import(db: Session, scan: Scan, message: str) -> None:
    """Mark an import that can't run (or be run again) failed, with its
    Activity event."""
    _finish(db, scan, ScanStatus.failed, {"error": message})


def _finish(db: Session, scan: Scan, status: ScanStatus, summary: dict) -> None:
    """Record the outcome on the scan and its Activity event, together."""
    scan.status = status
    scan.summary = summary
    scan.completed_at = datetime.now(timezone.utc)
    scan.progress = None
    counts = event_counts(scan.scan_type, summary)
    details = {}
    if error := summary.get("error") or next((e["message"] for e in summary.get("errors", []) if e["row"] == 0), None):
        details["error"] = error
    if scan.retry_count:
        details["retried"] = "Cut off (the worker stopped) and carried on from where it had got to"
    if scan.run_started_at and scan.started_at and (waited := scan.run_started_at - scan.started_at).total_seconds() >= 1:
        details["waited_seconds"] = round(waited.total_seconds())
    record_event(
        db,
        "import",
        org_id=scan.org_id,
        actor=db.get(User, scan.started_by) if scan.started_by else None,
        item=scan.filename or scan.scan_type,
        started_at=scan.run_started_at or scan.started_at,
        ended_at=scan.completed_at,
        outcome=status.value,
        # Rows that failed: worth a look, though the file imported.
        criticality=Criticality.warning if summary.get("failed") else None,
        counts=counts,
        details=details,
    )
    db.commit()
    try:
        import_staging.discard(db, scan.id)
    except Exception:  # the worker's daily clean-up gets it later
        logger.warning("Couldn't drop import %s's staging", scan.id, exc_info=True)
        db.rollback()
    if status == ScanStatus.completed and scan.content_hash:
        _drop_superseded_files(db, scan)


def _drop_superseded_files(db: Session, scan: Scan) -> None:
    """The same file (same content) is now imported: earlier failed uploads
    of it in the org no longer keep theirs for Retry, which would only import
    it again."""
    from app.api.uploads import upload_path  # the api package imports this module

    failed = db.scalars(
        select(Scan.id).where(
            Scan.org_id == scan.org_id,
            Scan.content_hash == scan.content_hash,
            Scan.status == ScanStatus.failed,
            Scan.id != scan.id,
        )
    ).all()
    for scan_id in failed:
        try:
            upload_path(scan_id).unlink(missing_ok=True)
        except OSError:  # the worker's daily clean-up gets it later
            pass


def _import(
    db: Session,
    scan: Scan,
    kind: ImportKind,
    fmt: str,
    source: bytes | Path,
    ingestion: IngestionSettings,
    profile: RowReader | None,
    progress: ProgressCallback | None = None,
) -> ImportReport:
    """Read and check every row into staging, then publish it (unless
    all-or-nothing rejects the file)."""
    if profile is not None:
        list_key = profile.json_list_key
    else:
        list_key = "assets" if kind == "assets" else "findings"
    fresh = ReadState(
        fingerprint=_fingerprint(kind, fmt, ingestion, profile),
        identifiers=import_staging.Identifiers(limit=TARGETED_LOAD_MAX),
    )
    if isinstance(source, bytes):
        staging = import_staging.MemoryStaging(fresh)
    else:
        staging = import_staging.DbStaging(db, scan.id, fresh)
    state = staging.load()
    if not state.read_done:
        _stage(staging, state, FileReader(source, fmt, list_key), _RowChecker(kind, ingestion, profile), ingestion, progress)

    report = ImportReport(
        failed=state.failed,
        errors=list(state.errors.items),
        skipped=state.skipped,
        skipped_rows=list(state.skipped_rows.items),
    )
    # Warnings from reading, then publishing; listed by row, the lowest
    # MAX_REPORTED_ERRORS of them, with the count of all.
    warnings: list[Capped] = [state.warnings]
    if profile is None and state.rows_with_output == 0:
        if hint := _wrong_source_hint(kind, state.columns):
            warnings.append(Capped([RowWarning(row=0, message=hint)], 1))
    # All-or-nothing with a bad row: nothing is written.
    if not state.failed or ingestion.import_partial_success:
        lock_org(db, scan.org_id, on_wait=lambda: progress and progress("waiting", 0, 0))
        found = state.identifiers
        index = AssetIndex.load(
            db, scan.org_id, found.hostnames, found.ips, found.cloud_ids, whole_org=found.whole_org
        )
        writes = _PendingWrites(db, scan.id, progress, state.items_staged)
        # When a file creates assets too, `created` counts those, so its
        # findings are counted separately.
        count_findings_as = "findings_created" if profile is not None and profile.creates_assets else "created"
        publisher = _Publisher(db, scan.org_id, scan.id, ingestion, report, index, writes, count_findings_as)
        for item in staging.items():
            publisher.publish(item)
        warnings += publisher.finish()
        if progress is not None:
            progress("saving", 0, 0)
        writes.flush()
    merged = sorted((w for capped in warnings for w in capped.items), key=lambda w: w.row)
    report.warnings = merged[:MAX_REPORTED_ERRORS]
    report.warnings_total = sum(capped.total for capped in warnings)
    return report


def _fingerprint(kind: ImportKind, fmt: str, ingestion: IngestionSettings, profile: RowReader | None) -> str:
    """What a staged read depends on: a resume with anything different
    (settings changed, a newer app) reads the file again. Built from the
    values themselves, sorted, never from repr(): that holds memory
    addresses and set orders that change every time Python starts, so a
    restarted worker would never carry on."""
    basis = {
        "version": import_staging.STAGING_VERSION,
        "kind": kind,
        "format": fmt,
        "settings": dataclasses.asdict(ingestion),
        "profile": None
        if profile is None
        else {
            "key": profile.key,
            "family": getattr(getattr(profile, "family", None), "key", None),
            "column_map": getattr(profile, "column_map", None),
            "params": params.model_dump(mode="json") if (params := getattr(profile, "params", None)) else None,
        },
    }
    canonical = json.dumps(basis, sort_keys=True, default=_canonical)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _canonical(value: Any) -> Any:
    """For json.dumps: sets sorted, enums by value."""
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, enum.Enum):
        return value.value
    raise TypeError(f"Can't fingerprint {type(value).__name__}")


class _RowChecker:
    """Reads and checks one record into what it gives (its asset and
    findings), noting errors, warnings and skipped rows in the read state.
    A ValueError fails the row, and its warnings are dropped since nothing
    from it is imported.

    The seam for profiles that sum rows up (Phase 2f part 2): finish() is
    called once every row is read and may give more rows, and what they
    gather is saved with each staged chunk (snapshot/restore), so it
    survives a resume."""

    def __init__(self, kind: ImportKind, ingestion: IngestionSettings, profile: RowReader | None):
        self.kind = kind
        self.ingestion = ingestion
        # What reads this import's rows: the profile, or (an event log) a
        # fresh tally of its own.
        start = getattr(profile, "start", None)
        self.profile = start() if start else profile

    def check(self, row: int, record: Any, state: ReadState) -> StagedRow | None:
        row_warnings: list[str] = []
        try:
            asset, findings = self._read(row, record, row_warnings, state)
        except ValueError as exc:
            state.failed += 1
            state.errors.add(RowError(row=row, message=str(exc)))
            return None
        for message in row_warnings:
            state.warnings.add(RowWarning(row=row, message=message))
        if asset is None and not findings:
            return None
        state.rows_with_output += 1
        return StagedRow(row, asset, findings)

    def _read(
        self, row: int, record: Any, warnings: list[str], state: ReadState
    ) -> tuple[AssetRow | None, list[FindingRow]]:
        if isinstance(record, NessusItem):
            finding = nessus_finding(record, self.ingestion, warnings)
            if finding is None:
                state.skipped += 1
                state.skipped_rows.add(
                    RowNote(
                        row=record.row,
                        item=f"{record.hostname or record.ip or 'no host'}: Nessus {record.plugin_id} "
                        f"{record.plugin_name}"[:300],
                        message="Info severity: skipped, as Settings say (Nessus Info items: Skip them)",
                    )
                )
                return None, []
            return None, [finding]
        if self.profile is not None:
            return self.profile.read_row(row, record, self.ingestion, warnings)
        if self.kind == "assets":
            return validate_asset(row, record, self.ingestion.asset_type_aliases, warnings), []
        return None, [validate_finding(row, record, warnings)]

    def finish(self) -> list[StagedRow]:
        finish = getattr(self.profile, "finish", None)
        return list(finish()) if finish else []

    def snapshot(self) -> dict:
        snapshot = getattr(self.profile, "snapshot", None)
        return snapshot() if snapshot else {}

    def restore(self, state: dict) -> None:
        restore = getattr(self.profile, "restore", None)
        if restore and state:
            restore(state)


def _stage(
    staging: "import_staging.MemoryStaging | import_staging.DbStaging",
    state: ReadState,
    reader: FileReader,
    checker: _RowChecker,
    ingestion: IngestionSettings,
    progress: ProgressCallback | None,
) -> None:
    """Read the file from where `state` got to, staging each WRITE_BATCH
    rows' output with the state (a resumable point). Once a row has failed
    and all-or-nothing will reject the file, rows are still checked (so the
    report counts every error) but no longer staged."""
    checker.restore(state.checker)
    chunk: list[StagedRow] = []

    def keep(item: StagedRow | None) -> None:
        if item is not None and (not state.failed or ingestion.import_partial_success):
            chunk.append(item)
            state.identifiers.add_row(item)

    def save(done: bool) -> None:
        state.checker = checker.snapshot()
        state.read_done = done
        staging.add(chunk, state)
        chunk.clear()

    try:
        for row, record in reader.records(skip_through=state.last_row):
            if state.rows_seen == 0:
                state.columns = list(record) if isinstance(record, dict) else []
            state.rows_seen += 1
            keep(checker.check(row, record, state))
            state.last_row = row
            if state.rows_seen % WRITE_BATCH == 0:
                save(done=False)
                if progress is not None:
                    estimate = state.rows_seen * reader.size // max(reader.position, 1)
                    progress("reading", state.rows_seen, max(estimate, state.rows_seen))
    except ImportFileError as exc:
        raise IngestionError(str(exc))
    if state.rows_seen == 0:
        raise IngestionError(
            "The .nessus file contains no findings" if reader.fmt == "nessus" else "The file contains no rows"
        )
    for item in checker.finish():
        keep(item)
    save(done=True)
    if progress is not None:
        progress("reading", state.rows_seen, state.rows_seen)


def _wrong_source_hint(kind: ImportKind, columns: list[str]) -> str | None:
    """For a generic import that imported nothing: if the file has none of the
    columns that identify a host, it's most likely another tool's export (a
    cloud inventory, an activity log...), so say so and name its columns."""
    if not columns or _IDENTITY_COLUMNS & set(columns):
        return None
    shown = ", ".join(columns[:8]) + (", ..." if len(columns) > 8 else "")
    return (
        f"Nothing was imported: this file's columns ({shown}) don't match this source, which needs a "
        f"hostname, ip or cloud_id column and expects {_EXPECTED_COLUMNS[kind]}. If the file is a tool's "
        "export or an event log (Azure Activity, CloudTrail, GCP Audit, endpoint security events), "
        "import it with that source."
    )


def _asset_key(row: AssetRow) -> tuple[str, ...]:
    """Which rows of one file are the same asset (see import_matching.py)."""
    if row.cloud_id:
        return "cloud_id", row.cloud_id
    category = row.type if row.type_known else ""
    if row.hostname:
        return "hostname", row.hostname.lower(), category
    return "ip", row.ip or "", category


class _RepeatedAssets:
    """Assets a file lists more than once with different values: each row
    updates the same asset, so the last one wins. One warning per asset,
    at its last row. Kept per asset, not per row."""

    def __init__(self):
        # key -> [rows, first row's values (hashed), differ?, last row, label]
        self._seen: dict[tuple[str, ...], list] = {}

    def add(self, row: AssetRow) -> None:
        values = hash(repr({k: v for k, v in vars(row).items() if k != "row"}))
        label = row.cloud_id or row.hostname or row.ip
        seen = self._seen.get(_asset_key(row))
        if seen is None:
            self._seen[_asset_key(row)] = [1, values, False, row.row, label]
        else:
            seen[0] += 1
            seen[2] = seen[2] or values != seen[1]
            seen[3], seen[4] = row.row, label

    def warnings(self) -> list[RowWarning]:
        return [
            RowWarning(
                row=last,
                message=f"{label} appears on {count} rows with different values; "
                f"later rows overwrite earlier ones (the last is row {last})",
            )
            for count, _, differ, last, label in self._seen.values()
            if count > 1 and differ
        ]


class _PendingWrites:
    """What an import has decided to write, sent to the database in bulk.
    Matching doesn't need it there: the in-memory indexes already have it.

    New rows are sent (with COPY) every WRITE_BATCH of them. Updates are
    gathered per asset until UPDATE_BATCH assets have some, since a file
    often lists the same host many times. Progress, in file rows, is reported
    every WRITE_BATCH rows.

    It also records which assets the upload touched (asset_scans), so
    archiving another upload leaves them be."""

    def __init__(self, db: Session, scan_id: uuid.UUID, progress: "ProgressCallback | None", rows_total: int):
        self.db = db
        self.scan_id = scan_id
        self.linked: set[uuid.UUID] = set()
        self.links: list[dict] = []
        self.progress = progress
        self.rows_total = rows_total
        self.rows_done = 0
        self.new_assets: dict[uuid.UUID, dict] = {}
        self.asset_updates: dict[uuid.UUID, dict] = {}
        self.details: dict[uuid.UUID, dict] = {}
        self.findings: list[dict] = []
        self._last_created: datetime | None = None

    def created_at(self) -> datetime:
        """Now, but always after the previous row's: "oldest first" follows the
        file's order even when the clock hasn't moved on between rows."""
        now = datetime.now(timezone.utc)
        if self._last_created is not None and now <= self._last_created:
            now = self._last_created + timedelta(microseconds=1)
        self._last_created = now
        return now

    def create_asset(self, values: dict) -> None:
        self.new_assets[values["id"]] = values
        self._created()

    def update_asset(self, asset_id: uuid.UUID, values: dict, details: dict | None = None) -> None:
        """Set columns, and merge `details` into the asset's (later keys win)."""
        if asset_id in self.new_assets:  # not inserted yet: fold it in
            new = self.new_assets[asset_id]
            new.update(values)
            if details:
                new["details"] = {**new["details"], **details}
        else:
            self.asset_updates.setdefault(asset_id, {}).update(values)
            if details:
                self.details[asset_id] = {**self.details.get(asset_id, {}), **details}
            if max(len(self.asset_updates), len(self.details)) >= UPDATE_BATCH:
                self.flush()

    def link(self, asset_id: uuid.UUID, created: bool = False) -> None:
        """The upload touched this asset: created it, or updated or matched
        it. A new asset is linked (as created) as it's queued, so later
        links to it from the same file change nothing."""
        if asset_id not in self.linked:
            self.linked.add(asset_id)
            self.links.append({"scan_id": self.scan_id, "asset_id": asset_id, "created": created})

    def create_finding(self, values: dict) -> None:
        self.findings.append(values)
        self._created()

    def row_done(self) -> None:
        self.rows_done += 1
        if self.progress is not None and (self.rows_done % WRITE_BATCH == 0 or self.rows_done == self.rows_total):
            self.progress("writing", self.rows_done, self.rows_total)

    def _created(self) -> None:
        if len(self.new_assets) + len(self.findings) >= WRITE_BATCH:
            self.flush()

    def flush(self) -> None:
        """Write everything pending. Assets first: findings may refer to them."""
        if self.new_assets:
            _copy_rows(self.db, Asset.__tablename__, list(self.new_assets.values()))
        if self.asset_updates:
            self.db.execute(update(Asset), [{"id": id_, **values} for id_, values in self.asset_updates.items()])
        if self.details:
            table = Asset.__table__
            self.db.execute(
                update(table)
                .where(table.c.id == bindparam("asset_id"))
                .values(details=table.c.details.op("||")(bindparam("new_details", type_=JSONB))),
                [{"asset_id": id_, "new_details": details} for id_, details in self.details.items()],
            )
        if self.links:
            _copy_rows(self.db, AssetScan.__tablename__, self.links)
        if self.findings:
            _copy_rows(self.db, Finding.__tablename__, self.findings)
        self.new_assets, self.asset_updates, self.details, self.findings, self.links = {}, {}, {}, [], []


def _copy_rows(db: Session, table: str, rows: list[dict]) -> None:
    """Insert rows (all with the same keys) with COPY, inside the session's
    transaction: much faster than INSERTs for thousands of rows."""
    columns = list(rows[0])
    with db.connection().connection.cursor() as cursor:
        with cursor.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row([_copy_value(row[column]) for column in columns])


def _copy_value(value: Any) -> Any:
    if isinstance(value, dict):
        return Jsonb(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


class _Publisher:
    """Writes staged rows, in file order: each row's asset (created, updated
    or matched and skipped, per the org's strategy), then its findings, on
    that asset or else on the matching inventory asset of any category,
    else on a new one whose type is a guess."""

    def __init__(
        self,
        db: Session,
        org_id: uuid.UUID,
        scan_id: uuid.UUID,
        ingestion: IngestionSettings,
        report: ImportReport,
        index: AssetIndex,
        writes: _PendingWrites,
        count_findings_as: Literal["created", "findings_created"],
    ):
        self.db, self.org_id, self.scan_id = db, org_id, scan_id
        self.strategy = ingestion.asset_existing_strategy
        self.report, self.index, self.writes = report, index, writes
        self.count_findings_as = count_findings_as
        self.findings = FindingIndex.load(db, org_id, index.existing_ids)
        self.warnings: Capped = Capped()
        self.duplicates: list[tuple[FindingRow, Origin]] = []  # the first, to list
        self.repeated = _RepeatedAssets() if self.strategy != "duplicate" else None

    def publish(self, item: StagedRow) -> None:
        asset = self._asset(item.asset) if item.asset is not None else None
        for finding in item.findings:
            self._finding(finding, asset)
        self.writes.row_done()

    def finish(self) -> list[Capped]:
        """The publishing warnings (and repeated assets'), and the listed
        duplicates' notes."""
        self.report.duplicate_rows = _duplicate_notes(self.db, self.duplicates)
        repeated = Capped()
        for warning in sorted(self.repeated.warnings() if self.repeated else [], key=lambda w: w.row):
            repeated.add(warning)
        return [repeated, self.warnings]

    def _asset(self, row: AssetRow) -> IndexedAsset:
        index, writes, report = self.index, self.writes, self.report
        if self.repeated is not None:
            self.repeated.add(row)
        existing = None
        if self.strategy != "duplicate":
            category = row.type if row.type_known else None
            matches = index.find(row.hostname, row.ip, row.cloud_id, category)
            existing = matches[0] if matches else None
            if len(matches) > 1 and category is None:
                self.warnings.add(_several_matches_warning(row, matches, "updated"))
        if existing is None:
            if self.strategy != "duplicate" and row.type_known and row.hostname:
                others = index.other_categories(row.hostname, row.type)
                if others:
                    self.warnings.add(
                        RowWarning(
                            row=row.row,
                            message=f"{row.hostname} is already recorded as a {' and a '.join(others)}; "
                            f"this {row.type} was added as a separate asset",
                        )
                    )
            existing = _new_asset(
                index,
                writes,
                self.org_id,
                type=row.type,
                subtype=row.subtype,
                type_known=row.type_known,
                hostname=row.hostname,
                ip=row.ip,
                cloud_id=row.cloud_id,
                environment=row.environment,
                criticality=row.criticality,
                tags=row.tags,
                details=row.details,
            )
            report.created += 1
        elif existing.id in writes.linked and self.strategy == "skip":
            report.repeated += 1  # left as its first row had it
        elif self.strategy == "skip":
            report.skipped += 1
            if len(report.skipped_rows) < MAX_REPORTED_ERRORS:
                report.skipped_rows.append(
                    RowNote(
                        row=row.row,
                        item=_host(row)[:300],
                        message="Already recorded: left unchanged, as Settings say "
                        "(Asset already in inventory: Leave it unchanged)",
                    )
                )
        else:
            values = {
                name: value
                for name in ("hostname", "ip", "cloud_id", "environment", "criticality", "tags")
                if (value := getattr(row, name)) is not None
            }
            # A guessed type never replaces a known one. The subtype describes
            # the type, so they change together: a row saying just "server"
            # clears an earlier "laptop".
            if row.type_known or not existing.type_known:
                values.update(type=row.type, subtype=row.subtype, type_known=row.type_known)
            index.update(
                existing,
                **{k: v for k, v in values.items() if k in ("hostname", "ip", "cloud_id", "type", "type_known")},
            )
            # Details are merged, so facts from different sources accumulate.
            writes.update_asset(existing.id, values, row.details or None)
            # Named by an earlier row of this file (created or matched by it):
            # a repeat, not another asset updated.
            if existing.id in writes.linked:
                report.repeated += 1
            else:
                report.updated += 1
        writes.link(existing.id)
        return existing

    def _finding(self, row: FindingRow, asset: IndexedAsset | None) -> None:
        index, writes = self.index, self.writes
        if asset is None and not (row.hostname or row.ip or row.cloud_id):
            # An event log's finding about no one host (a whole tenant).
            self._create_finding(row, None)
            return
        if asset is None:
            matches = index.find(row.hostname, row.ip, row.cloud_id)
            if not matches:
                only_cloud = not row.hostname and not row.ip
                asset = _new_asset(
                    index,
                    writes,
                    self.org_id,
                    type=FINDING_CLOUD_ASSET_TYPE if only_cloud else FINDING_ASSET_TYPE,
                    type_known=False,
                    hostname=row.hostname,
                    ip=row.ip,
                    cloud_id=row.cloud_id,
                )
            else:
                asset = matches[0]
                if len(matches) > 1:
                    self.warnings.add(_several_matches_warning(row, matches, "recorded the finding on"))
                # Fill in whichever identifier the inventory didn't have yet.
                filled = {
                    name: getattr(row, name)
                    for name in ("hostname", "ip", "cloud_id")
                    if getattr(asset, name) is None and getattr(row, name) is not None
                }
                if filled:
                    index.update(asset, **filled)
                    writes.update_asset(asset.id, filled)

        writes.link(asset.id)
        self._create_finding(row, asset)

    def _create_finding(self, row: FindingRow, asset: IndexedAsset | None) -> None:
        """Unless the same finding is already recorded (on its asset, or for
        no asset): then it's counted as a duplicate."""
        key = finding_key(asset.id if asset else None, row.source, row.category, row.description)
        if key in self.findings:
            self.report.duplicates += 1
            if len(self.duplicates) < MAX_REPORTED_ERRORS:
                self.duplicates.append((row, self.findings.origin(key)))
            return
        self.findings.add(key, row.row)  # later rows in the same file dedup against it
        self.writes.create_finding(
            {
                "id": uuid.uuid4(),
                "org_id": self.org_id,
                "scan_id": self.scan_id,
                "asset_id": asset.id if asset else None,
                "category": row.category,
                "domain": row.domain,
                "severity": row.severity,
                "description": row.description,
                "source": row.source,
                "raw_data": row.raw_data,
                "event_count": row.event_count,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "details": row.details,
                "created_at": self.writes.created_at(),
            }
        )
        setattr(self.report, self.count_findings_as, getattr(self.report, self.count_findings_as) + 1)


def _duplicate_notes(db: Session, duplicates: list[tuple[FindingRow, Origin]]) -> list[RowNote]:
    """Each listed duplicate, with what it duplicates: a finding from an
    earlier upload (named), one added by hand, or an earlier row of this file."""
    scan_ids = {origin for _, origin in duplicates if isinstance(origin, uuid.UUID)}
    uploads = dict(db.execute(select(Scan.id, Scan.filename).where(Scan.id.in_(scan_ids))).tuples().all()) if scan_ids else {}
    notes = []
    for row, origin in duplicates:
        if isinstance(origin, int):
            message = f"Same as row {origin} of this file"
        elif origin is None:
            message = "Same as a finding added by hand"
        else:
            message = f"Same as a finding from {uploads.get(origin) or 'an earlier upload'}"
        what = row.category or row.description or "uncategorised"
        notes.append(RowNote(row=row.row, item=f"{_host(row)}: {what}"[:300], message=message))
    return notes


def _host(row: AssetRow | FindingRow) -> str:
    return row.hostname or row.ip or row.cloud_id or "no host"


def _new_asset(index: AssetIndex, writes: _PendingWrites, org_id, **values) -> IndexedAsset:
    """Queue a new asset for insertion and index it, so later rows match it."""
    values = {
        "id": uuid.uuid4(),
        "org_id": org_id,
        "subtype": None,
        "environment": None,
        "criticality": None,
        "tags": None,
        "details": {},
        "created_at": writes.created_at(),
        **values,
    }
    writes.create_asset(values)
    writes.link(values["id"], created=True)
    asset = IndexedAsset(
        id=values["id"],
        type=values["type"],
        type_known=values["type_known"],
        hostname=values["hostname"],
        ip=values["ip"],
        cloud_id=values["cloud_id"],
    )
    index.add(asset)
    return asset


def _several_matches_warning(row: AssetRow | FindingRow, matches: list[IndexedAsset], action: str) -> RowWarning:
    """A row whose category isn't known matched several assets sharing its
    name (or IP); it went to the first, the oldest."""
    categories = ", ".join(sorted({asset.type for asset in matches}))
    return RowWarning(
        row=row.row,
        message=f"{row.hostname or row.ip} matches {len(matches)} assets ({categories}) and this row "
        f"doesn't say which; {action} the {matches[0].type} (the oldest)",
    )


# --- Field helpers -------------------------------------------------------------


def _require_object(record: Any) -> None:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")


def _text(record: dict, key: str, max_length: int | None = None) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{key} must be text")
    value = str(value).strip()
    if not value:
        return None
    if max_length and len(value) > max_length:
        raise ValueError(f"{key} is longer than {max_length} characters")
    return value


def _identity(record: dict, warnings: list[str] | None = None) -> tuple[str | None, str | None, str | None]:
    """(hostname, ip, cloud_id): at least one is required. Cloud resources are
    often known only by their cloud ID (ARN, resource ID)."""
    hostname = _text(record, "hostname", 255)
    cloud_id = _text(record, "cloud_id", 255)
    ip = _text(record, "ip", 64)
    if ip:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError(f"ip {ip!r} is not a valid IP address")
        ip = str(address)
        unusual = unusual_ip_kind(address)
        if unusual and warnings is not None:
            article = "an" if unusual[0] in "aeiou" else "a"
            warnings.append(f"ip {ip} is {article} {unusual} address; imported anyway")
    if not hostname and not ip and not cloud_id:
        raise ValueError(IDENTITY_REQUIRED)
    return hostname, ip, cloud_id


def unusual_ip_kind(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Why an address can't be a normal host's, if it can't. Private ranges
    (10.x, 192.168.x...) are normal for internal hosts: no warning."""
    if address.is_unspecified:
        return "unspecified"
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link-local"
    if address.is_multicast:
        return "multicast"
    if address.is_reserved:
        return "reserved"
    return None


def _enum(record: dict, key: str, enum_cls):
    value = _text(record, key)
    if not value:
        raise ValueError(f"{key} is required")
    try:
        return enum_cls(value.lower())
    except ValueError:
        allowed = ", ".join(member.value for member in enum_cls)
        raise ValueError(f"{key} {value!r} must be one of: {allowed}")


def _tags(value: Any) -> list[str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        parts = re.split(r"[;,]", value)
    elif isinstance(value, list):
        parts = [str(part) for part in value]
    elif isinstance(value, dict):
        parts = [f"{key}:{val}" if str(val).strip() else str(key) for key, val in value.items()]
    else:
        raise ValueError("tags must be a list, an object or a ;-separated string")
    tags = [part.strip() for part in parts if part.strip()]
    return tags or None
