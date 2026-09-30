"""File imports: asset inventories (CSV/JSON), findings (generic CSV/JSON,
native .nessus), and profile imports, where each row of a tool's export
becomes an asset plus any findings (import_profiles.py).

Flow: parse the whole file -> validate every row -> write the valid rows. All
validation happens before any DB write, so the all-or-nothing mode (per-org
setting) never leaves a partial import behind.

process_import() is the single entry point, called during the request for
small files and from a background task for large ones (ingestion_background.py);
it resolves the org's effective settings and records the outcome on the scan.
"""

import csv
import enum
import io
import ipaddress
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Protocol

from psycopg.types.json import Jsonb
from sqlalchemy import bindparam, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app.models.archive import AssetScan
from app.models.asset import Asset
from app.models.enums import Criticality, Domain, ScanStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.schemas.ingestion import ImportReport, RowError, RowWarning
from app.services.asset_types import BUILTIN_TYPE_ALIASES, resolve_asset_type
from app.services.events import record_event
from app.services.import_matching import AssetIndex, FindingIndex, IndexedAsset, finding_key
from app.services.nessus_parser import NessusItem, map_nessus_domain, map_nessus_severity, parse_nessus
from app.services.org_lock import IMPORT_JOB, job_running, lock_org
from app.services.org_settings import IngestionSettings, resolve_ingestion_settings

ImportKind = Literal["assets", "findings", "profile"]

# Assets created for findings whose host isn't in the inventory yet (a cloud
# resource when the finding names only a cloud ID). A guess: an inventory
# import later replaces it with the real category.
FINDING_ASSET_TYPE = "server"
FINDING_CLOUD_ASSET_TYPE = "cloud_resource"
# The report lists at most this many row errors (and warnings); `failed`
# still counts every error.
MAX_REPORTED_ERRORS = 1000
IDENTITY_REQUIRED = "hostname, ip or cloud_id is required"
# The columns a generic file identifies each row's host by. A generic import
# whose file has none of them is almost certainly the wrong source for it.
_IDENTITY_COLUMNS = {"hostname", "ip", "cloud_id"}
_EXPECTED_COLUMNS = {
    "assets": "type, hostname and/or ip or cloud_id, and optionally subtype, environment, criticality, tags",
    "findings": "hostname and/or ip or cloud_id, domain, severity, and optionally category, description, source",
}
# New rows sent to the database per batch, and file rows per progress report.
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


# Told how a large import goes: (phase, done, total). Phases, in order:
# "reading" (file rows checked), "waiting" (for another import into the org),
# "writing" (file rows written), "findings" (a tool export's findings
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
    text = _decode(content)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestionError("The CSV file has no header row")
    records = []
    try:
        for record in reader:
            # Cells beyond the header land under the None key; ignore them.
            records.append((reader.line_num, {_key(k): v for k, v in record.items() if k is not None}))
    except csv.Error as exc:
        raise IngestionError(f"Invalid CSV at line {reader.line_num}: {exc}")
    return records


def parse_json(content: bytes, list_key: str) -> list[tuple[int, Any]]:
    """(1-based position, record) for a top-level list, or {list_key: [...]}."""
    try:
        data = json.loads(_decode(content))
    except json.JSONDecodeError as exc:
        raise IngestionError(f"Invalid JSON: {exc}")
    if isinstance(data, dict) and list_key in data:
        data = data[list_key]
    if not isinstance(data, list):
        raise IngestionError(f'Expected a JSON list of records, or {{"{list_key}": [...]}}')
    return [
        (position, {_key(k): v for k, v in record.items()} if isinstance(record, dict) else record)
        for position, record in enumerate(data, start=1)
    ]


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
    content: bytes,
    profile: RowReader | None = None,
    progress: ProgressCallback | None = None,
) -> ImportReport:
    """Import `content` into the scan's org and record the outcome on the scan
    (status, summary, completed_at). kind "profile" reads each row with
    `profile`; `progress` is told how the writing goes. Unexpected errors mark
    the scan failed and are re-raised."""
    scan_id = scan.id
    org = db.get(Organization, scan.org_id)
    ingestion = resolve_ingestion_settings(org)
    scan.status = ScanStatus.running
    scan.run_started_at = datetime.now(timezone.utc)
    scan.progress = {"phase": "reading"}
    db.commit()

    # Held until the outcome is saved: the background worker then knows it
    # runs (see org_lock.job_running).
    with job_running(db, IMPORT_JOB, scan_id):
        try:
            report = _import(db, scan, kind, fmt, content, ingestion, profile, progress)
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
               "failed": "rows_failed"},
    "findings": {"created": "findings_created", "duplicates": "duplicate_findings", "skipped": "items_skipped",
                 "failed": "rows_failed"},
    "profile": {"created": "assets_created", "updated": "assets_updated", "skipped": "assets_skipped",
                "findings_created": "findings_created", "duplicates": "duplicate_findings", "failed": "rows_failed"},
}


# Import profiles that record findings only: their "created" counts findings.
FINDINGS_ONLY_SCAN_TYPES = ("findings_csv", "findings_json", "nessus", "generic_findings_import")


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
        details["retried"] = "Cut off (the worker stopped) and started again from the saved file"
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


def _import(
    db: Session,
    scan: Scan,
    kind: ImportKind,
    fmt: str,
    content: bytes,
    ingestion: IngestionSettings,
    profile: RowReader | None,
    progress: ProgressCallback | None = None,
) -> ImportReport:
    report = ImportReport()
    errors: list[RowError] = []
    warnings: list[RowWarning] = []
    asset_rows: list[AssetRow] = []
    columns: list[str] = []  # the file's (first record's) column names
    finding_rows: list[FindingRow] = []

    def read(row: int, reader: Callable[[list[str]], tuple[AssetRow | None, list[FindingRow]]]) -> None:
        """Run one row's reader. A ValueError fails the row, and its warnings
        are dropped since nothing from it is imported."""
        row_warnings: list[str] = []
        try:
            asset, findings = reader(row_warnings)
        except ValueError as exc:
            errors.append(RowError(row=row, message=str(exc)))
            return
        if asset is not None:
            asset_rows.append(asset)
        finding_rows.extend(findings)
        warnings.extend(RowWarning(row=row, message=message) for message in row_warnings)

    if fmt == "nessus":
        try:
            items = parse_nessus(content)
        except ValueError as exc:
            raise IngestionError(str(exc))
        if not items:
            raise IngestionError("The .nessus file contains no findings")
        for position, item in enumerate(items, start=1):
            def read_nessus(row_warnings: list[str], item: NessusItem = item):
                finding = nessus_finding(item, ingestion, row_warnings)
                if finding is None:
                    report.skipped += 1
                    return None, []
                return None, [finding]

            read(item.row, read_nessus)
            _report_reading(progress, position, len(items))
    else:
        if profile is not None:
            list_key = profile.json_list_key
        else:
            list_key = "assets" if kind == "assets" else "findings"
        records = parse_csv(content) if fmt == "csv" else parse_json(content, list_key)
        if not records:
            raise IngestionError("The file contains no rows")
        first = records[0][1]
        columns = list(first) if isinstance(first, dict) else []
        for position, (row, record) in enumerate(records, start=1):
            def read_record(row_warnings: list[str], row: int = row, record: Any = record):
                if profile is not None:
                    return profile.read_row(row, record, ingestion, row_warnings)
                if kind == "assets":
                    return validate_asset(row, record, ingestion.asset_type_aliases, row_warnings), []
                return None, [validate_finding(row, record, row_warnings)]

            read(row, read_record)
            _report_reading(progress, position, len(records))
        del records, record  # read into rows; free them before writing

    if ingestion.asset_existing_strategy != "duplicate":
        warnings += _repeated_asset_warnings(asset_rows)
    report.failed = len(errors)
    if profile is None and not asset_rows and not finding_rows:
        if hint := _wrong_source_hint(kind, columns):
            warnings.append(RowWarning(row=0, message=hint))
    report.errors = errors[:MAX_REPORTED_ERRORS]
    # All-or-nothing with a bad row: nothing is written.
    if not errors or ingestion.import_partial_success:
        lock_org(db, scan.org_id, on_wait=lambda: progress and progress("waiting", 0, 0))
        index = _load_asset_index(db, scan.org_id, asset_rows, finding_rows)
        rows_total = len({r.row for r in asset_rows} | {r.row for r in finding_rows})
        writes = _PendingWrites(db, scan.id, progress, rows_total)
        asset_by_row = _write_assets(db, scan.org_id, asset_rows, ingestion, report, warnings, index, writes)
        # When a file creates assets too, `created` counts those, so its
        # findings are counted separately.
        count_findings_as = "findings_created" if profile is not None and profile.creates_assets else "created"
        _write_findings(
            db, scan.org_id, scan.id, finding_rows, report, warnings, index, writes, asset_by_row, count_findings_as
        )
        if progress is not None:
            progress("saving", 0, 0)
        writes.flush()
    warnings.sort(key=lambda w: w.row)
    report.warnings = warnings[:MAX_REPORTED_ERRORS]
    report.warnings_total = len(warnings)
    return report


def _report_reading(progress: ProgressCallback | None, rows_read: int, rows_total: int) -> None:
    """Every WRITE_BATCH rows read, and once all are."""
    if progress is not None and (rows_read % WRITE_BATCH == 0 or rows_read == rows_total):
        progress("reading", rows_read, rows_total)


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
        "export, import it with that tool's source; event logs (cloud activity, audit or endpoint security "
        "events) can't be imported yet."
    )


def _asset_key(row: AssetRow) -> tuple[str, ...]:
    """Which rows of one file are the same asset (see import_matching.py)."""
    if row.cloud_id:
        return "cloud_id", row.cloud_id
    category = row.type if row.type_known else ""
    if row.hostname:
        return "hostname", row.hostname.lower(), category
    return "ip", row.ip or "", category


def _repeated_asset_warnings(rows: list[AssetRow]) -> list[RowWarning]:
    """One warning per asset that a file lists more than once with different
    values: each row updates the same asset, so the last one wins."""
    by_asset: dict[tuple[str, ...], list[AssetRow]] = {}
    for row in rows:
        by_asset.setdefault(_asset_key(row), []).append(row)
    warnings = []
    for repeats in by_asset.values():
        if len(repeats) == 1:  # most assets: nothing to compare
            continue
        values = {repr({k: v for k, v in vars(r).items() if k != "row"}) for r in repeats}
        if len(values) > 1:
            last = repeats[-1]
            label = last.cloud_id or last.hostname or last.ip
            warnings.append(
                RowWarning(
                    row=last.row,
                    message=f"{label} appears on {len(repeats)} rows with different values; "
                    f"later rows overwrite earlier ones (the last is row {last.row})",
                )
            )
    return warnings


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

    phase = "writing"

    def start_phase(self, phase: str, rows_total: int) -> None:
        """Count progress afresh, e.g. a tool export's findings after its rows."""
        self.phase, self.rows_done, self.rows_total = phase, 0, rows_total
        if self.progress is not None:
            self.progress(phase, 0, rows_total)

    def row_done(self) -> None:
        self.rows_done += 1
        if self.progress is not None and (self.rows_done % WRITE_BATCH == 0 or self.rows_done == self.rows_total):
            self.progress(self.phase, self.rows_done, self.rows_total)

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


def _write_assets(
    db: Session,
    org_id,
    rows: list[AssetRow],
    ingestion: IngestionSettings,
    report: ImportReport,
    warnings: list[RowWarning],
    index: AssetIndex,
    writes: _PendingWrites,
) -> dict[int, IndexedAsset]:
    """Create or update each row's asset per the org's strategy. Returns the
    asset each row ended up as (created, updated, or matched and skipped), so
    findings from the same row attach to it."""
    strategy = ingestion.asset_existing_strategy
    asset_by_row: dict[int, IndexedAsset] = {}
    for row in rows:
        existing = None
        if strategy != "duplicate":
            category = row.type if row.type_known else None
            matches = index.find(row.hostname, row.ip, row.cloud_id, category)
            existing = matches[0] if matches else None
            if len(matches) > 1 and category is None:
                warnings.append(_several_matches_warning(row, matches, "updated"))
        if existing is None:
            if strategy != "duplicate" and row.type_known and row.hostname:
                others = index.other_categories(row.hostname, row.type)
                if others:
                    warnings.append(
                        RowWarning(
                            row=row.row,
                            message=f"{row.hostname} is already recorded as a {' and a '.join(others)}; "
                            f"this {row.type} was added as a separate asset",
                        )
                    )
            existing = _new_asset(
                index,
                writes,
                org_id,
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
        elif strategy == "skip":
            report.skipped += 1
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
            report.updated += 1
        asset_by_row[row.row] = existing
        writes.link(existing.id)
        writes.row_done()
    return asset_by_row


def _write_findings(
    db: Session,
    org_id,
    scan_id,
    rows: list[FindingRow],
    report: ImportReport,
    warnings: list[RowWarning],
    index: AssetIndex,
    writes: _PendingWrites,
    asset_by_row: dict[int, IndexedAsset] | None = None,
    count_as: Literal["created", "findings_created"] = "created",
) -> None:
    """Record each finding against its row's asset (from asset_by_row), else
    the matching inventory asset of any category, else a new one whose type
    is a guess."""
    asset_by_row = asset_by_row or {}
    findings = _load_finding_index(db, org_id, index.existing_ids)
    # A tool export's rows were counted with their assets: count its
    # findings as a phase of their own. A findings file counts file rows (a
    # .nessus item or CSV row may give several findings).
    own_phase = bool(asset_by_row) and bool(rows)
    if own_phase:
        writes.start_phase("findings", len(rows))
    previous_row = None
    for row in rows:
        if own_phase or (row.row not in asset_by_row and row.row != previous_row):
            writes.row_done()
        previous_row = row.row

        asset = asset_by_row.get(row.row)
        if asset is None:
            matches = index.find(row.hostname, row.ip, row.cloud_id)
            if not matches:
                only_cloud = not row.hostname and not row.ip
                asset = _new_asset(
                    index,
                    writes,
                    org_id,
                    type=FINDING_CLOUD_ASSET_TYPE if only_cloud else FINDING_ASSET_TYPE,
                    type_known=False,
                    hostname=row.hostname,
                    ip=row.ip,
                    cloud_id=row.cloud_id,
                )
            else:
                asset = matches[0]
                if len(matches) > 1:
                    warnings.append(_several_matches_warning(row, matches, "recorded the finding on"))
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
        key = finding_key(asset.id, row.source, row.category, row.description)
        if key in findings:
            report.duplicates += 1
            continue
        findings.add(key)  # later rows in the same file dedup against it
        writes.create_finding(
            {
                "id": uuid.uuid4(),
                "org_id": org_id,
                "scan_id": scan_id,
                "asset_id": asset.id,
                "category": row.category,
                "domain": row.domain,
                "severity": row.severity,
                "description": row.description,
                "source": row.source,
                "raw_data": row.raw_data,
                "created_at": writes.created_at(),
            }
        )
        setattr(report, count_as, getattr(report, count_as) + 1)


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


def _load_asset_index(
    db: Session, org_id: uuid.UUID, asset_rows: list[AssetRow], finding_rows: list[FindingRow]
) -> AssetIndex:
    """The org's assets the file can touch (see import_matching.py), loaded
    once per import, after taking the lock so a concurrent import's assets
    are committed and included."""
    rows = [*asset_rows, *finding_rows]
    return AssetIndex.load(
        db,
        org_id,
        hostnames=(r.hostname for r in rows if r.hostname),
        ips=(r.ip for r in rows if r.ip),
        cloud_ids=(r.cloud_id for r in rows if r.cloud_id),
    )


def _load_finding_index(db: Session, org_id: uuid.UUID, asset_ids: list[uuid.UUID]) -> FindingIndex:
    return FindingIndex.load(db, org_id, asset_ids)


# --- Field helpers -------------------------------------------------------------


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IngestionError("The file is not valid UTF-8 text")


def _key(key: Any) -> Any:
    return key.strip().lower() if isinstance(key, str) else key


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
