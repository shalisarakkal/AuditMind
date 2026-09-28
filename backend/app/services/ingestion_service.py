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
import io
import ipaddress
import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import Domain, ScanStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.schemas.ingestion import ImportReport, RowError, RowWarning
from app.services.asset_types import BUILTIN_TYPE_ALIASES, resolve_asset_type
from app.services.nessus_parser import NessusItem, map_nessus_domain, map_nessus_severity, parse_nessus
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
    db: Session, scan: Scan, kind: ImportKind, fmt: str, content: bytes, profile: RowReader | None = None
) -> ImportReport:
    """Import `content` into the scan's org and record the outcome on the scan
    (status, summary, completed_at). kind "profile" reads each row with
    `profile`. Unexpected errors mark the scan failed and are re-raised."""
    scan_id = scan.id
    org = db.get(Organization, scan.org_id)
    ingestion = resolve_ingestion_settings(org)
    scan.status = ScanStatus.running
    db.commit()

    try:
        report = _import(db, scan, kind, fmt, content, ingestion, profile)
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
    db: Session,
    scan: Scan,
    kind: ImportKind,
    fmt: str,
    content: bytes,
    ingestion: IngestionSettings,
    profile: RowReader | None,
) -> ImportReport:
    report = ImportReport()
    errors: list[RowError] = []
    warnings: list[RowWarning] = []
    asset_rows: list[AssetRow] = []
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
        for item in items:
            def read_nessus(row_warnings: list[str], item: NessusItem = item):
                finding = nessus_finding(item, ingestion, row_warnings)
                if finding is None:
                    report.skipped += 1
                    return None, []
                return None, [finding]

            read(item.row, read_nessus)
    else:
        if profile is not None:
            list_key = profile.json_list_key
        else:
            list_key = "assets" if kind == "assets" else "findings"
        records = parse_csv(content) if fmt == "csv" else parse_json(content, list_key)
        if not records:
            raise IngestionError("The file contains no rows")
        for row, record in records:
            def read_record(row_warnings: list[str], row: int = row, record: Any = record):
                if profile is not None:
                    return profile.read_row(row, record, ingestion, row_warnings)
                if kind == "assets":
                    return validate_asset(row, record, ingestion.asset_type_aliases, row_warnings), []
                return None, [validate_finding(row, record, row_warnings)]

            read(row, read_record)

    if ingestion.asset_existing_strategy != "duplicate":
        warnings += _repeated_asset_warnings(asset_rows)
    report.failed = len(errors)
    report.errors = errors[:MAX_REPORTED_ERRORS]
    # All-or-nothing with a bad row: nothing is written.
    if not errors or ingestion.import_partial_success:
        _lock_org_imports(db, scan.org_id)
        asset_by_row = _write_assets(db, scan.org_id, asset_rows, ingestion, report, warnings)
        # When a file creates assets too, `created` counts those, so its
        # findings are counted separately.
        count_findings_as = "findings_created" if profile is not None and profile.creates_assets else "created"
        _write_findings(db, scan.org_id, scan.id, finding_rows, report, warnings, asset_by_row, count_findings_as)
    warnings.sort(key=lambda w: w.row)
    report.warnings = warnings[:MAX_REPORTED_ERRORS]
    report.warnings_total = len(warnings)
    return report


def _asset_key(row: AssetRow) -> tuple[str, ...]:
    """Which rows of one file are the same asset (see _find_assets)."""
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


def _write_assets(
    db: Session,
    org_id,
    rows: list[AssetRow],
    ingestion: IngestionSettings,
    report: ImportReport,
    warnings: list[RowWarning],
) -> dict[int, Asset]:
    """Create or update each row's asset per the org's strategy. Returns the
    asset each row ended up as (created, updated, or matched and skipped), so
    findings from the same row attach to it."""
    strategy = ingestion.asset_existing_strategy
    asset_by_row: dict[int, Asset] = {}
    for row in rows:
        existing = None
        if strategy != "duplicate":
            category = row.type if row.type_known else None
            matches = _find_assets(db, org_id, row.hostname, row.ip, row.cloud_id, category)
            existing = matches[0] if matches else None
            if len(matches) > 1 and category is None:
                warnings.append(_several_matches_warning(row, matches, "updated"))
        if existing is None:
            if strategy != "duplicate" and row.type_known and row.hostname:
                others = _other_categories(db, org_id, row.hostname, row.type)
                if others:
                    warnings.append(
                        RowWarning(
                            row=row.row,
                            message=f"{row.hostname} is already recorded as a {' and a '.join(others)}; "
                            f"this {row.type} was added as a separate asset",
                        )
                    )
            existing = Asset(
                org_id=org_id,
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
            db.add(existing)
            db.flush()  # later rows in the same file can match it
            report.created += 1
        elif strategy == "skip":
            report.skipped += 1
        else:
            for name in ("hostname", "ip", "cloud_id", "environment", "criticality", "tags"):
                value = getattr(row, name)
                if value is not None:
                    setattr(existing, name, value)
            # A guessed type never replaces a known one. The subtype describes
            # the type, so they change together: a row saying just "server"
            # clears an earlier "laptop".
            if row.type_known or not existing.type_known:
                existing.type, existing.subtype = row.type, row.subtype
                existing.type_known = row.type_known
            if row.details:
                # Merged, so facts from different sources accumulate.
                existing.details = {**(existing.details or {}), **row.details}
            report.updated += 1
        asset_by_row[row.row] = existing
    return asset_by_row


def _write_findings(
    db: Session,
    org_id,
    scan_id,
    rows: list[FindingRow],
    report: ImportReport,
    warnings: list[RowWarning],
    asset_by_row: dict[int, Asset] | None = None,
    count_as: Literal["created", "findings_created"] = "created",
) -> None:
    """Record each finding against its row's asset (from asset_by_row), else
    the matching inventory asset of any category, else a new one whose type
    is a guess."""
    for row in rows:
        asset = (asset_by_row or {}).get(row.row)
        if asset is None:
            matches = _find_assets(db, org_id, row.hostname, row.ip, row.cloud_id)
            if not matches:
                only_cloud = not row.hostname and not row.ip
                asset = Asset(
                    org_id=org_id,
                    type=FINDING_CLOUD_ASSET_TYPE if only_cloud else FINDING_ASSET_TYPE,
                    type_known=False,
                    hostname=row.hostname,
                    ip=row.ip,
                    cloud_id=row.cloud_id,
                )
                db.add(asset)
            else:
                asset = matches[0]
                if len(matches) > 1:
                    warnings.append(_several_matches_warning(row, matches, "recorded the finding on"))
                # Fill in whichever identifier the inventory didn't have yet.
                asset.hostname = asset.hostname or row.hostname
                asset.ip = asset.ip or row.ip
                asset.cloud_id = asset.cloud_id or row.cloud_id
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
        setattr(report, count_as, getattr(report, count_as) + 1)


def _several_matches_warning(row: AssetRow | FindingRow, matches: list[Asset], action: str) -> RowWarning:
    """A row whose category isn't known matched several assets sharing its
    name (or IP); it went to the first, the oldest."""
    categories = ", ".join(sorted({asset.type for asset in matches}))
    return RowWarning(
        row=row.row,
        message=f"{row.hostname or row.ip} matches {len(matches)} assets ({categories}) and this row "
        f"doesn't say which; {action} the {matches[0].type} (the oldest)",
    )


def _other_categories(db: Session, org_id, hostname: str, category: str) -> list[str]:
    """Categories of the other assets named `hostname`, for a new asset that
    shares its name with a different kind of device."""
    rows = (
        db.query(Asset.type)
        .filter(Asset.org_id == org_id, func.lower(Asset.hostname) == hostname.lower(), Asset.type != category)
        .distinct()
        .all()
    )
    return sorted(type_ for (type_,) in rows)


def _lock_org_imports(db: Session, org_id: uuid.UUID) -> None:
    """Serialise imports into one org until this transaction ends. Matching is
    look-up-then-insert, so two overlapping imports (say, a background one and
    an upload) could otherwise both create the same host. A lock rather than a
    unique index, because the "duplicate" asset strategy allows repeats."""
    key = int.from_bytes(org_id.bytes[:8], "big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(key)))


def _find_assets(
    db: Session,
    org_id,
    hostname: str | None,
    ip: str | None,
    cloud_id: str | None = None,
    category: str | None = None,
) -> list[Asset]:
    """The assets a row could be, best first; the row goes to the first.

    By cloud ID (exact), else hostname (case-insensitive), else IP but only
    against assets with no hostname, so two differently named hosts that
    happen to share an IP are never merged. A row with a cloud ID only matches
    by name or IP an asset with no cloud ID of its own.

    By name or IP, a row whose category is known matches only an asset of that
    category or one whose type is a guess (a same-category asset first), so a
    server and a printer sharing a name stay two assets. A row with no known
    category (category None) matches any, the oldest first."""
    assets = db.query(Asset).filter(Asset.org_id == org_id)
    if cloud_id:
        match = assets.filter(Asset.cloud_id == cloud_id).order_by(Asset.created_at).first()
        if match or (not hostname and not ip):
            return [match] if match else []
        assets = assets.filter(Asset.cloud_id.is_(None))
    if category:
        assets = assets.filter(or_(Asset.type == category, Asset.type_known.is_(False)))
        assets = assets.order_by(Asset.type != category, Asset.created_at)
    else:
        assets = assets.order_by(Asset.created_at)
    if hostname:
        matches = assets.filter(func.lower(Asset.hostname) == hostname.lower()).all()
        if matches or not ip:
            return matches
        return assets.filter(Asset.ip == ip, Asset.hostname.is_(None)).all()
    return assets.filter(Asset.ip == ip).all()


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
        raise ValueError("hostname, ip or cloud_id is required")
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
