"""Import profiles: read a tool's own export (endpoint agent, network scan,
cloud inventory...) where each row becomes an asset plus any findings.

A *family* is the code that knows how to read one kind of export: which
fields it has and which findings its rules raise. A *profile* is a family plus
data: the column header for each field and the family's rule settings. The
built-in profiles use each family's defaults; an org can copy one and adjust
its column names and settings (import_profiles table). There's no formula
language: admins tune existing rules, they can't add new logic.

Row flow: map the record's columns to fields -> fill blanks from the
profile's default values -> the family builds the asset row (with details) and
its findings. A ValueError fails the row; anything recoverable (a value that
can't be read, an unusual IP) becomes a warning instead.
"""

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.models.enums import Domain, Severity
from app.models.import_profile import ImportProfile
from app.schemas.import_profile import (
    CloudInventoryParams,
    DirectoryParams,
    EndpointAgentParams,
    GenericAssetsParams,
    GenericFindingsParams,
    NetworkScanParams,
    ProfileField,
    ProfileParams,
)
from app.services.ingestion_service import AssetRow, FindingRow, IngestionError, validate_asset, validate_finding
from app.services.org_settings import IngestionSettings

# Fields every asset-producing family can map (the asset table's own columns).
ASSET_FIELDS = (
    ProfileField(name="type", label="Type"),
    ProfileField(name="subtype", label="Subtype"),
    ProfileField(name="hostname", label="Hostname"),
    ProfileField(name="ip", label="IP address"),
    ProfileField(name="cloud_id", label="Cloud ID"),
    ProfileField(name="environment", label="Environment"),
    ProfileField(name="criticality", label="Criticality"),
    ProfileField(name="tags", label="Tags"),
)
FINDING_FIELDS = (
    ProfileField(name="hostname", label="Hostname"),
    ProfileField(name="ip", label="IP address"),
    ProfileField(name="cloud_id", label="Cloud ID"),
    ProfileField(name="domain", label="Domain"),
    ProfileField(name="severity", label="Severity"),
    ProfileField(name="category", label="Category"),
    ProfileField(name="description", label="Description"),
    ProfileField(name="source", label="Source"),
)


# A mapped column may name alternatives, "ResourceType|Type": the first one the
# file has is read. Other columns can be kept in the asset's details (at most
# this many, each value cut to 500 characters).
MAX_OTHER_COLUMNS = 50


def utc_now() -> datetime:
    """Import time, for the stale-date checks. A test seam."""
    return datetime.now(timezone.utc)


# --- Profiles ---------------------------------------------------------------


@dataclass(frozen=True)
class Family:
    key: str
    label: str
    creates_assets: bool
    creates_findings: bool
    json_list_key: str
    fields: tuple[ProfileField, ...]
    default_column_map: dict[str, str]
    params_model: type[ProfileParams]
    read: Callable[["ProfileConfig", int, dict, dict, IngestionSettings, list[str]], tuple[AssetRow | None, list[FindingRow]]]

    @property
    def field_names(self) -> set[str]:
        return {f.name for f in self.fields}


@dataclass(frozen=True)
class ProfileConfig:
    """A resolved profile, ready to read rows. Pure data (no DB handles), so
    it can be handed to a background import."""

    key: str
    name: str
    family: Family
    builtin: bool
    column_map: dict[str, str]
    params: ProfileParams

    @property
    def creates_assets(self) -> bool:
        return self.family.creates_assets

    @property
    def json_list_key(self) -> str:
        return self.family.json_list_key

    def column(self, field: str) -> str:
        """The file's header for a field (its first name), for messages."""
        return self.column_map.get(field, field).split("|")[0].strip()

    def read_row(
        self, row: int, record: Any, ingestion: IngestionSettings, warnings: list[str]
    ) -> tuple[AssetRow | None, list[FindingRow]]:
        if not isinstance(record, dict):
            raise ValueError("record must be an object")
        values: dict[str, Any] = {}
        read: set[str] = set()
        for field, header in self.column_map.items():
            names = column_names(header)
            read.update(names)
            values[field] = next((record[name] for name in names if name in record), None)
        type_defaulted = False
        for field, default in self.params.default_values.items():
            if _blank(values.get(field)):
                values[field] = default
                type_defaulted = type_defaulted or field == "type"
        asset, findings = self.family.read(self, row, values, record, ingestion, warnings)
        if asset is not None and type_defaulted:
            # A default is the profile's guess, not what the file says (an
            # endpoint agent runs on servers too), so it doesn't pin the match.
            asset.type_known = False
        if asset is not None and self.params.keep_other_columns:
            asset.details = {**_other_columns(record, read), **asset.details}
        return asset, findings

    def type_aliases(self, ingestion: IngestionSettings) -> dict[str, str]:
        return {**ingestion.asset_type_aliases, **self.params.type_aliases}


def builtin_profile(family: Family) -> ProfileConfig:
    return ProfileConfig(
        key=family.key,
        name=family.label,
        family=family,
        builtin=True,
        column_map=dict(family.default_column_map),
        params=family.params_model(),
    )


def custom_profile(profile: ImportProfile) -> ProfileConfig:
    """Raises ValueError if the stored profile no longer validates."""
    family = FAMILIES.get(profile.family)
    if family is None:
        raise ValueError(f"unknown profile type {profile.family!r}")
    column_map, params = validate_profile_parts(family, profile.column_map, profile.params)
    return ProfileConfig(
        key=str(profile.id), name=profile.name, family=family, builtin=False, column_map=column_map, params=params
    )


def resolve_profile(db: Session, org_id: uuid.UUID, key: str) -> ProfileConfig:
    """A built-in profile by family key, or one of the org's own by id.
    Raises IngestionError if there's no such profile in this org."""
    if key in FAMILIES:
        return builtin_profile(FAMILIES[key])
    profile = find_custom_profile(db, org_id, key)
    if profile is None:
        raise IngestionError(f"Unknown import profile {key!r}")
    try:
        return custom_profile(profile)
    except ValueError as exc:
        raise IngestionError(f"Import profile {profile.name!r} is invalid: {exc}")


def find_custom_profile(db: Session, org_id: uuid.UUID, key: str) -> ImportProfile | None:
    try:
        profile_id = uuid.UUID(key)
    except ValueError:
        return None
    profile = db.get(ImportProfile, profile_id)
    return profile if profile is not None and profile.org_id == org_id else None


def validate_profile_parts(family: Family, column_map: dict, params: dict) -> tuple[dict[str, str], ProfileParams]:
    """Check a column map and settings against the family. Raises ValueError
    with a readable message."""
    if not isinstance(column_map, dict):
        raise ValueError("column_map must be an object")
    cleaned: dict[str, str] = {}
    for field, header in column_map.items():
        if field not in family.field_names:
            raise ValueError(f"column_map: {field!r} is not a field of {family.label} (fields: {_names(family)})")
        if not isinstance(header, str) or not header.strip():
            raise ValueError(f"column_map: the column for {field!r} can't be blank")
        names = [name.strip() for name in header.split("|")]
        if not all(names):
            raise ValueError(f"column_map: the column for {field!r} has a blank alternative")
        if len(header.strip()) > 200:
            raise ValueError(f"column_map: the columns for {field!r} are longer than 200 characters")
        cleaned[field] = "|".join(names)
    if not cleaned:
        raise ValueError("column_map must map at least one field")

    try:
        parsed = family.params_model.model_validate(params)
    except ValidationError as exc:
        raise ValueError(_validation_message(exc))
    for field in parsed.default_values:
        if field not in family.field_names:
            raise ValueError(f"default_values: {field!r} is not a field of {family.label} (fields: {_names(family)})")
    return cleaned, parsed


def column_names(header: str) -> list[str]:
    """A mapped column's names as records key them (trimmed, lower case)."""
    return [name.strip().lower() for name in header.split("|") if name.strip()]


def _names(family: Family) -> str:
    return ", ".join(f.name for f in family.fields)


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(
        f"params.{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" if err["loc"] else err["msg"]
        for err in exc.errors()
    )


def params_json(params: BaseModel) -> dict:
    return params.model_dump(mode="json")


# --- Families -----------------------------------------------------------------


def _read_generic_assets(profile, row, values, record, ingestion, warnings):
    return validate_asset(row, values, profile.type_aliases(ingestion), warnings), []


def _read_generic_findings(profile, row, values, record, ingestion, warnings):
    return None, [validate_finding(row, values, warnings, raw=record)]


def _read_endpoint_agent(profile, row, values, record, ingestion, warnings):
    params: EndpointAgentParams = profile.params
    details = _details(values, ("endpoint_id", "agent_version", "last_heartbeat"))
    asset = validate_asset(row, values, profile.type_aliases(ingestion), warnings, details=details)
    finding = _finding_factory(profile, asset, record)
    findings = []

    threats = _count(values.get("threats_detected"), profile.column("threats_detected"), warnings)
    if threats >= params.threats_high_at:
        severity = Severity.critical if threats >= params.threats_critical_at else Severity.high
        findings.append(
            finding(
                Domain.incident_response,
                severity,
                "Active threats detected",
                f"The endpoint agent reported {threats} threat{'s' if threats != 1 else ''}.",
            )
        )

    status = _string(values.get("compliance_status"))
    if status and status.lower() not in params.compliant_values:
        severity = params.compliance_severity.get(status.lower())
        if severity is None:
            warnings.append(
                f"{profile.column('compliance_status')} {status!r} isn't a recognised value; no finding recorded"
            )
        else:
            findings.append(
                finding(Domain.compliance_alignment, severity, "Endpoint compliance", f"Compliance status: {status}.")
            )

    heartbeat = _string(values.get("last_heartbeat"))
    age = _stale_age(heartbeat, params.stale_after_days, params.day_first_dates, profile.column("last_heartbeat"),
                     "stale-agent check", warnings)
    if age is not None:
        findings.append(
            finding(
                Domain.monitoring_detection,
                Severity.medium,
                "Endpoint agent not reporting",
                f"Last heartbeat {heartbeat}, {age.days} days before the import "
                f"(threshold {params.stale_after_days} days).",
            )
        )
    return asset, findings


def _read_network_scan(profile, row, values, record, ingestion, warnings):
    params: NetworkScanParams = profile.params
    os_name = _string(values.get("os"))
    ports = _ports(values.get("open_ports"), profile.column("open_ports"), warnings)
    details = _details(values, ("os",))
    if ports:
        details["open_ports"] = ports

    fallback = None
    if _blank(values.get("type")):
        fallback = classify_os(os_name, profile.column("os"), warnings)
    asset = validate_asset(
        row, values, profile.type_aliases(ingestion), warnings, fallback_type=fallback, details=details
    )
    asset.type_known = fallback is None or os_category(os_name) is not None
    finding = _finding_factory(profile, asset, record)
    findings = []

    vulnerability = _string(values.get("vulnerabilities"))
    if vulnerability and vulnerability.lower() not in params.no_vulnerability_values:
        raw_score = _string(values.get("risk_score"))
        severity, score_read = _risk_severity(raw_score, params, profile.column("risk_score"), warnings)
        domains = {name.strip().lower(): domain for name, domain in params.vulnerability_domains.items()}
        findings.append(
            finding(
                domains.get(vulnerability.lower(), Domain.vulnerability_management),
                severity,
                vulnerability[:100],
                f"{vulnerability} (risk score {raw_score})." if score_read else f"{vulnerability}.",
            )
        )

    for port in ports:
        risky = params.risky_ports.get(str(port))
        if risky:
            findings.append(
                finding(
                    Domain.network_config,
                    risky.severity,
                    f"Open port {port} ({risky.label})",
                    f"{risky.label} (port {port}) is open.",
                )
            )
    return asset, findings


def _read_directory(profile, row, values, record, ingestion, warnings):
    params: DirectoryParams = profile.params
    details = _details(values, ("asset_id", "os", "owner", "last_login"))
    os_name = _string(values.get("os"))
    fallback = None
    if _blank(values.get("type")):
        fallback = classify_os(os_name, profile.column("os"), warnings)
    asset = validate_asset(
        row, values, profile.type_aliases(ingestion), warnings, fallback_type=fallback, details=details
    )
    asset.type_known = fallback is None or os_category(os_name) is not None
    finding = _finding_factory(profile, asset, record)
    findings = []

    status = _string(values.get("account_status"))
    if status:
        if status.lower() in params.disabled_values:
            findings.append(
                finding(
                    Domain.identity_access,
                    params.disabled_severity,
                    "Disabled directory account",
                    f"The directory lists this account as {status}; remove it if it is no longer needed.",
                )
            )
        elif status.lower() not in params.ok_values:
            warnings.append(
                f"{profile.column('account_status')} {status!r} isn't a recognised value; no finding recorded"
            )

    login = _string(values.get("last_login"))
    age = _stale_age(login, params.stale_login_days, params.day_first_dates, profile.column("last_login"),
                     "stale-account check", warnings)
    if age is not None:
        findings.append(
            finding(
                Domain.identity_access,
                params.stale_severity,
                "Stale directory account",
                f"Last login {login}, {age.days} days before the import (threshold {params.stale_login_days} days).",
            )
        )
    return asset, findings


def _read_cloud_inventory(profile, row, values, record, ingestion, warnings):
    details = _details(values, ("region",))
    return validate_asset(row, values, profile.type_aliases(ingestion), warnings, details=details), []


FAMILIES: dict[str, Family] = {
    family.key: family
    for family in (
        Family(
            key="generic_assets",
            label="Generic asset list",
            creates_assets=True,
            creates_findings=False,
            json_list_key="assets",
            fields=ASSET_FIELDS,
            default_column_map={f.name: f.name for f in ASSET_FIELDS},
            params_model=GenericAssetsParams,
            read=_read_generic_assets,
        ),
        Family(
            key="generic_findings",
            label="Generic findings",
            creates_assets=False,
            creates_findings=True,
            json_list_key="findings",
            fields=FINDING_FIELDS,
            default_column_map={f.name: f.name for f in FINDING_FIELDS},
            params_model=GenericFindingsParams,
            read=_read_generic_findings,
        ),
        Family(
            key="endpoint_agent",
            label="Endpoint agent export",
            creates_assets=True,
            creates_findings=True,
            json_list_key="records",
            fields=(
                ProfileField(name="endpoint_id", label="Endpoint ID", detail=True),
                *ASSET_FIELDS,
                ProfileField(name="agent_version", label="Agent version", detail=True),
                ProfileField(name="last_heartbeat", label="Last heartbeat", detail=True),
                ProfileField(name="threats_detected", label="Threats detected"),
                ProfileField(name="compliance_status", label="Compliance status"),
            ),
            default_column_map={
                "endpoint_id": "EndPointID|DeviceID|AgentID",
                "hostname": "DeviceName|Hostname|ComputerName",
                "agent_version": "AgentVersion|SensorVersion",
                "last_heartbeat": "LastHeartbeat|LastSeen|LastCheckIn",
                "threats_detected": "ThreatsDetected|Threats|Detections",
                "compliance_status": "ComplianceStatus|Compliance",
            },
            params_model=EndpointAgentParams,
            read=_read_endpoint_agent,
        ),
        Family(
            key="network_scan",
            label="Network scan export",
            creates_assets=True,
            creates_findings=True,
            json_list_key="records",
            fields=(
                *ASSET_FIELDS,
                ProfileField(name="os", label="Operating system", detail=True),
                ProfileField(name="open_ports", label="Open ports", detail=True),
                ProfileField(name="vulnerabilities", label="Vulnerabilities"),
                ProfileField(name="risk_score", label="Risk score"),
            ),
            default_column_map={
                "ip": "IPAddress|IP",
                "hostname": "Hostname|DNSName",
                "os": "OSDetected|OS|OperatingSystem",
                "open_ports": "OpenPorts|Ports",
                "vulnerabilities": "Vulnerabilities|Vulnerability",
                "risk_score": "RiskScore|Risk|CVSS",
            },
            params_model=NetworkScanParams,
            read=_read_network_scan,
        ),
        Family(
            key="cloud_inventory",
            label="Cloud inventory export",
            creates_assets=True,
            creates_findings=False,
            json_list_key="records",
            fields=(*ASSET_FIELDS, ProfileField(name="region", label="Region", detail=True)),
            default_column_map={
                "cloud_id": "ResourceID|ARN|InstanceID",
                "hostname": "ResourceName|Name",
                "type": "ResourceType|Type",
                "region": "Region|Location",
                "environment": "Environment|Env",
                "tags": "Tags|Labels",
            },
            params_model=CloudInventoryParams,
            read=_read_cloud_inventory,
        ),
        Family(
            key="directory",
            label="Directory (Active Directory) export",
            creates_assets=True,
            creates_findings=True,
            json_list_key="records",
            fields=(
                ProfileField(name="asset_id", label="Directory ID", detail=True),
                *ASSET_FIELDS,
                ProfileField(name="os", label="Operating system", detail=True),
                ProfileField(name="owner", label="Owner", detail=True),
                ProfileField(name="last_login", label="Last login", detail=True),
                ProfileField(name="account_status", label="Account status"),
            ),
            default_column_map={
                "asset_id": "AssetID|ObjectGUID|DistinguishedName",
                "hostname": "Hostname|DNSHostName|ComputerName|Name",
                "type": "Type|DeviceType",
                "os": "OS|OperatingSystem",
                "owner": "Owner|ManagedBy",
                "last_login": "LastLogin|LastLogonDate|LastLogon",
                "account_status": "Status|AccountStatus|Enabled",
            },
            params_model=DirectoryParams,
            read=_read_directory,
        ),
    )
}

# --- Rules and value helpers -------------------------------------------------

# Checked in order; the first pattern found in the OS name wins.
_OS_TYPES: tuple[tuple[str, re.Pattern], ...] = (
    ("network_device", re.compile(r"\b(cisco|junos|fortios|pan-os|routeros|nx-os|arista)\b", re.I)),
    ("workstation", re.compile(r"\b(windows (7|8|8\.1|10|11)|macos|mac os|os x|chrome ?os)\b", re.I)),
    (
        "server",
        re.compile(
            r"\b(windows server|linux|ubuntu|centos|debian|red ?hat|rhel|suse|fedora|rocky|alma|"
            r"amazon linux|oracle linux|freebsd|openbsd|unix|aix|solaris|esxi)\b",
            re.I,
        ),
    ),
)


def os_category(os_name: str | None) -> str | None:
    """The category an OS name points to, or None if it isn't recognised."""
    for category, pattern in _OS_TYPES:
        if os_name and pattern.search(os_name):
            return category
    return None


def classify_os(os_name: str | None, column: str, warnings: list[str]) -> tuple[str, str | None]:
    """(category, subtype) from a scanned OS name; the OS name is the subtype.
    Unrecognised or missing -> server, with a warning (the reader marks that
    type a guess)."""
    if os_name:
        category = os_category(os_name)
        if category:
            return category, os_name[:100]
        warnings.append(f"{column} {os_name!r} isn't a recognised operating system; recorded as a server")
        return "server", os_name[:100]
    warnings.append(f"{column} is blank; recorded as a server")
    return "server", None


_DATE_FORMATS = ("{d} %H:%M:%S", "{d} %H:%M", "{d} %I:%M %p", "{d} %I:%M:%S %p", "{d}")


def parse_datetime(value: str, day_first: bool = False) -> datetime | None:
    """ISO 8601, or a slash date month-first (9/21/2026 15:48) unless
    day_first. No timezone -> UTC. None if it can't be read."""
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
        date_formats = ("%d/%m/%Y", "%d/%m/%y") if day_first else ("%m/%d/%Y", "%m/%d/%y")
        for date_format in date_formats:
            for pattern in _DATE_FORMATS:
                try:
                    parsed = datetime.strptime(value, pattern.format(d=date_format))
                    break
                except ValueError:
                    continue
            if parsed:
                break
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _stale_age(
    text: str | None, threshold_days: int, day_first: bool, column: str, check: str, warnings: list[str]
) -> timedelta | None:
    """How long ago `text` was, if longer than the threshold. An unreadable
    date gets a warning and no finding."""
    if not text:
        return None
    seen = parse_datetime(text, day_first=day_first)
    if seen is None:
        warnings.append(f"{column} {text!r} isn't a date this profile can read; {check} skipped")
        return None
    age = utc_now() - seen
    return age if age > timedelta(days=threshold_days) else None


def _other_columns(record: dict, read: set[str]) -> dict:
    """The record's columns that no field reads, for the asset's details."""
    extra: dict[str, Any] = {}
    for key, value in record.items():
        if not isinstance(key, str) or key in read or _blank(value) or len(extra) >= MAX_OTHER_COLUMNS:
            continue
        if isinstance(value, (dict, list)):
            text = json.dumps(value)
            extra[key] = value if len(text) <= 500 else text[:500]
        else:
            extra[key] = str(value).strip()[:500]
    return extra


def _risk_severity(
    raw: str | None, params: NetworkScanParams, column: str, warnings: list[str]
) -> tuple[Severity, bool]:
    """(severity, whether the score could be read)."""
    score = None
    if raw:
        try:
            score = float(raw)
        except ValueError:
            pass
    if score is None or not 0 <= score <= 10:
        shown = repr(raw) if raw else "blank"
        warnings.append(f"{column} is {shown}, not a score from 0 to 10; recorded as medium")
        return Severity.medium, False
    if score >= params.risk_critical_at:
        return Severity.critical, True
    if score >= params.risk_high_at:
        return Severity.high, True
    if score >= params.risk_medium_at:
        return Severity.medium, True
    return Severity.low, True


def _count(value: Any, column: str, warnings: list[str]) -> int:
    """A non-negative whole number; blank -> 0, anything else -> 0 + warning."""
    text = _string(value)
    if text is None:
        return 0
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is None or number < 0 or number != int(number):
        warnings.append(f"{column} {text!r} isn't a count; treated as 0")
        return 0
    return int(number)


def _ports(value: Any, column: str, warnings: list[str]) -> list[int]:
    """Port numbers from a list or a "22,80;443" string, in order, without
    repeats. Entries that aren't port numbers are skipped with a warning."""
    if _blank(value):
        return []
    parts = value if isinstance(value, list) else re.split(r"[,;\s]+", str(value))
    ports: list[int] = []
    for part in parts:
        text = str(part).strip()
        if not text:
            continue
        if text.isdigit() and 1 <= int(text) <= 65535:
            if int(text) not in ports:
                ports.append(int(text))
        else:
            warnings.append(f"{column}: {text!r} isn't a port number; skipped")
    return ports


def _details(values: dict, fields: tuple[str, ...]) -> dict:
    details = {}
    for field in fields:
        text = _string(values.get(field))
        if text:
            details[field] = text[:500]
    return details


def _finding_factory(profile: ProfileConfig, asset: AssetRow, record: dict):
    """Findings from a row all belong to that row's asset. Their source is the
    family, so copying or renaming a profile keeps duplicate detection."""

    def make(domain: Domain, severity: Severity, category: str, description: str) -> FindingRow:
        return FindingRow(
            row=asset.row,
            hostname=asset.hostname,
            ip=asset.ip,
            domain=domain,
            severity=severity,
            category=category,
            description=description,
            source=profile.family.key,
            raw_data=record,
            cloud_id=asset.cloud_id,
        )

    return make


def _string(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == []
