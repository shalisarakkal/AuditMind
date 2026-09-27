"""File imports: asset inventories (CSV/JSON) and findings (generic CSV/JSON,
native .nessus).

Flow: parse the whole file -> validate every row -> write the valid rows. All
validation happens before any DB write, so the all-or-nothing mode (per-org
setting) never leaves a partial import behind.

process_import() is the single entry point, called during the request for
small files and from a background task for large ones (ingestion_background.py);
it resolves the org's effective settings and records the outcome on the scan.
"""

import csv
import io
import ipaddress
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import Domain, ScanStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.schemas.ingestion import ImportReport, RowError
from app.services.nessus_parser import NessusItem, map_nessus_domain, map_nessus_severity, parse_nessus
from app.services.org_settings import IngestionSettings, resolve_ingestion_settings

ImportKind = Literal["assets", "findings"]

ASSET_TYPES = ("server", "workstation", "network_device", "database", "cloud_resource", "application")
# Assets created for findings whose host isn't in the inventory yet.
FINDING_ASSET_TYPE = "server"
# The report lists at most this many row errors; `failed` still counts them all.
MAX_REPORTED_ERRORS = 1000

_FORMATS: dict[ImportKind, dict[str, str]] = {
    "assets": {".csv": "csv", ".json": "json"},
    "findings": {".csv": "csv", ".json": "json", ".nessus": "nessus"},
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


def validate_asset(row: int, record: Any) -> AssetRow:
    _require_object(record)
    asset_type = _text(record, "type", 50)
    if not asset_type:
        raise ValueError("type is required")
    asset_type = asset_type.lower()
    if asset_type not in ASSET_TYPES:
        raise ValueError(f"type {asset_type!r} must be one of: {', '.join(ASSET_TYPES)}")
    hostname, ip = _host(record)
    return AssetRow(
        row=row,
        type=asset_type,
        hostname=hostname,
        ip=ip,
        cloud_id=_text(record, "cloud_id", 255),
        environment=_text(record, "environment", 50),
        criticality=_text(record, "criticality", 50),
        tags=_tags(record.get("tags")),
    )


def validate_finding(row: int, record: Any) -> FindingRow:
    _require_object(record)
    hostname, ip = _host(record)
    return FindingRow(
        row=row,
        hostname=hostname,
        ip=ip,
        domain=_enum(record, "domain", Domain),
        severity=_enum(record, "severity", Severity),
        category=_text(record, "category", 100),
        description=_text(record, "description"),
        source=_text(record, "source", 100) or "manual",
        raw_data=record,
    )


def nessus_finding(item: NessusItem, ingestion: IngestionSettings) -> FindingRow | None:
    """None for an Info item the org's settings skip."""
    severity = map_nessus_severity(item.severity, ingestion.nessus_info_severity)
    if severity is None:
        return None
    hostname, ip = _host({"hostname": item.hostname, "ip": item.ip})

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


def process_import(db: Session, scan: Scan, kind: ImportKind, fmt: str, content: bytes) -> ImportReport:
    """Import `content` into the scan's org and record the outcome on the scan
    (status, summary, completed_at). Unexpected errors mark the scan failed and
    are re-raised."""
    scan_id = scan.id
    org = db.get(Organization, scan.org_id)
    ingestion = resolve_ingestion_settings(org)
    scan.status = ScanStatus.running
    db.commit()

    try:
        report = _import(db, scan, kind, fmt, content, ingestion)
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


def _finish(db: Session, scan: Scan, status: ScanStatus, summary: dict) -> None:
    scan.status = status
    scan.summary = summary
    scan.completed_at = datetime.now(timezone.utc)
    db.commit()


def _import(
    db: Session, scan: Scan, kind: ImportKind, fmt: str, content: bytes, ingestion: IngestionSettings
) -> ImportReport:
    report = ImportReport()
    errors: list[RowError] = []
    rows: list = []

    if fmt == "nessus":
        try:
            items = parse_nessus(content)
        except ValueError as exc:
            raise IngestionError(str(exc))
        if not items:
            raise IngestionError("The .nessus file contains no findings")
        for item in items:
            try:
                finding = nessus_finding(item, ingestion)
            except ValueError as exc:
                errors.append(RowError(row=item.row, message=str(exc)))
                continue
            if finding is None:
                report.skipped += 1
            else:
                rows.append(finding)
    else:
        list_key = "assets" if kind == "assets" else "findings"
        records = parse_csv(content) if fmt == "csv" else parse_json(content, list_key)
        if not records:
            raise IngestionError("The file contains no rows")
        validate = validate_asset if kind == "assets" else validate_finding
        for row, record in records:
            try:
                rows.append(validate(row, record))
            except ValueError as exc:
                errors.append(RowError(row=row, message=str(exc)))

    report.failed = len(errors)
    report.errors = errors[:MAX_REPORTED_ERRORS]
    if errors and not ingestion.import_partial_success:
        return report  # all-or-nothing: nothing is written

    _lock_org_imports(db, scan.org_id)
    if kind == "assets":
        _write_assets(db, scan.org_id, rows, ingestion, report)
    else:
        _write_findings(db, scan.org_id, scan.id, rows, report)
    return report


def _write_assets(db: Session, org_id, rows: list[AssetRow], ingestion: IngestionSettings, report: ImportReport) -> None:
    strategy = ingestion.asset_existing_strategy
    for row in rows:
        existing = None if strategy == "duplicate" else _find_asset(db, org_id, row.hostname, row.ip)
        if existing is None:
            db.add(
                Asset(
                    org_id=org_id,
                    type=row.type,
                    hostname=row.hostname,
                    ip=row.ip,
                    cloud_id=row.cloud_id,
                    environment=row.environment,
                    criticality=row.criticality,
                    tags=row.tags,
                )
            )
            db.flush()  # later rows in the same file can match it
            report.created += 1
        elif strategy == "skip":
            report.skipped += 1
        else:
            for name in ("type", "hostname", "ip", "cloud_id", "environment", "criticality", "tags"):
                value = getattr(row, name)
                if value is not None:
                    setattr(existing, name, value)
            report.updated += 1


def _write_findings(db: Session, org_id, scan_id, rows: list[FindingRow], report: ImportReport) -> None:
    for row in rows:
        asset = _find_asset(db, org_id, row.hostname, row.ip)
        if asset is None:
            asset = Asset(org_id=org_id, type=FINDING_ASSET_TYPE, hostname=row.hostname, ip=row.ip)
            db.add(asset)
        else:
            # Fill in whichever identifier the inventory didn't have yet.
            asset.hostname = asset.hostname or row.hostname
            asset.ip = asset.ip or row.ip
        db.flush()

        if _is_duplicate(db, org_id, asset.id, row):
            report.duplicates += 1
            continue
        db.add(
            Finding(
                org_id=org_id,
                scan_id=scan_id,
                asset_id=asset.id,
                category=row.category,
                domain=row.domain,
                severity=row.severity,
                description=row.description,
                source=row.source,
                raw_data=row.raw_data,
            )
        )
        db.flush()  # later rows in the same file dedup against it
        report.created += 1


def _lock_org_imports(db: Session, org_id: uuid.UUID) -> None:
    """Serialise imports into one org until this transaction ends. Matching is
    look-up-then-insert, so two overlapping imports (say, a background one and
    an upload) could otherwise both create the same host. A lock rather than a
    unique index, because the "duplicate" asset strategy allows repeats."""
    key = int.from_bytes(org_id.bytes[:8], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(key)))


def _find_asset(db: Session, org_id, hostname: str | None, ip: str | None) -> Asset | None:
    """Match by hostname (case-insensitive). Failing that, by IP, but only
    against assets with no hostname, so two differently named hosts that
    happen to share an IP are never merged."""
    assets = db.query(Asset).filter(Asset.org_id == org_id).order_by(Asset.created_at)
    if hostname:
        match = assets.filter(func.lower(Asset.hostname) == hostname.lower()).first()
        if match or not ip:
            return match
        return assets.filter(Asset.ip == ip, Asset.hostname.is_(None)).first()
    return assets.filter(Asset.ip == ip).first()


def _is_duplicate(db: Session, org_id, asset_id, row: FindingRow) -> bool:
    """Same asset + source + category. Without a category, the description
    stands in for it, so unrelated uncategorised findings aren't collapsed."""
    query = db.query(Finding.id).filter(
        Finding.org_id == org_id, Finding.asset_id == asset_id, Finding.source == row.source
    )
    if row.category is None:
        query = query.filter(Finding.category.is_(None), Finding.description.is_not_distinct_from(row.description))
    else:
        query = query.filter(Finding.category == row.category)
    return db.query(query.exists()).scalar()


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


def _host(record: dict) -> tuple[str | None, str | None]:
    hostname = _text(record, "hostname", 255)
    ip = _text(record, "ip", 64)
    if ip:
        try:
            ip = str(ipaddress.ip_address(ip))
        except ValueError:
            raise ValueError(f"ip {ip!r} is not a valid IP address")
    if not hostname and not ip:
        raise ValueError("hostname or ip is required")
    return hostname, ip


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
    else:
        raise ValueError("tags must be a list or a ;-separated string")
    tags = [part.strip() for part in parts if part.strip()]
    return tags or None
