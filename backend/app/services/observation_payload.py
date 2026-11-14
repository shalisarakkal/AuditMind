"""Strict server-captured native snapshots; a mapping stamp is not approval."""
import hashlib
import json
from datetime import datetime, timezone

from app.models.enums import Domain, Severity
from app.services.finding_identity import assess_identity

MAPPING_VERSION = "nessus-observation-payload-v1"
MAPPING_KEY = "mapping_version"
MAX_BYTES = 16 * 1024 * 1024
FIELDS = ("severity", "description", "details", "raw_data", "first_seen", "last_seen")
PAYLOAD_KEYS = frozenset((*FIELDS, "domain", "category", "event_count", MAPPING_KEY))
RAW_KEYS = frozenset(("host", "plugin_id", "plugin_name", "plugin_family", "severity",
    "port", "protocol", "svc_name", "risk_factor", "synopsis", "description", "solution",
    "cve", "cvss3_base_score", "plugin_output"))


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError("Expected a bounded offset-aware timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source timestamps require an offset")
    return parsed.astimezone(timezone.utc).isoformat()


def validate(payload, *, org_id, source_identity):
    """Validate full retained data after the database size gate, never truncate it."""
    if not isinstance(payload, dict) or payload.get(MAPPING_KEY) != MAPPING_VERSION:
        raise ValueError("Observation has no supported versioned native payload mapping")
    if payload.keys() != PAYLOAD_KEYS:
        raise ValueError("Snapshot fields do not match the strict native payload contract")
    if len(encode(payload).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Snapshot exceeds the supported payload size")
    if (not isinstance(payload["domain"], str) or not isinstance(payload["severity"], str)
            or payload["domain"] not in {v.value for v in Domain} or payload["severity"] not in {v.value for v in Severity}):
        raise ValueError("Unsupported native classification")
    if payload["event_count"] is not None or payload["details"] is not None:
        raise ValueError("Aggregate event fields are outside this native mapping")
    raw = payload["raw_data"]
    if not isinstance(raw, dict) or raw.keys() != RAW_KEYS:
        raise ValueError("Raw scanner fields do not match the native allowlist")
    if any(not (isinstance(v, str) or v is None) for k, v in raw.items() if k != "cve"):
        raise ValueError("Raw native scalar fields must be strings or null")
    if not isinstance(raw["cve"], list) or any(not isinstance(v, str) for v in raw["cve"]):
        raise ValueError("Native CVE values must be a string list")
    if raw["plugin_output"] is not None and len(raw["plugin_output"]) > 4000:
        raise ValueError("Native plugin output exceeds the captured mapping limit")
    assessment = assess_identity(org_id=org_id, scan_type="nessus", source="nessus", profile=None, raw=raw)
    if not isinstance(source_identity, dict):
        raise ValueError("Retained source identity must be a native object")
    expected = assess_identity(org_id=org_id, scan_type="nessus", source="nessus", profile=None, raw=source_identity)
    if len(assessment.source_material) != 3 or assessment.source_material != expected.source_material:
        raise ValueError("Payload native identity differs from the retained observation")
    mapped = {"0": "low", "1": "low", "2": "medium", "3": "high", "4": "critical"}.get(raw["severity"])
    if mapped != payload["severity"]:
        raise ValueError("Payload severity differs from its native scanner value")
    location = f" ({raw['port']}/{raw['protocol']})" if raw["port"] and raw["port"] != "0" else ""
    category = f"Nessus {raw['plugin_id']}{location}"[:100]
    description = (raw["plugin_name"] or "") + (f": {raw['synopsis']}" if raw["synopsis"] else "")
    if payload["category"] != category or payload["description"] != (description or None):
        raise ValueError("Mapped category/description differs from the native payload")
    values = {field: payload[field] for field in FIELDS}
    for field in ("first_seen", "last_seen"):
        values[field] = timestamp(values[field])
    if values["first_seen"] and values["last_seen"] and values["first_seen"] > values["last_seen"]:
        raise ValueError("First seen must not follow last seen")
    return values, assessment.source_material


def summary(value):
    serialized = encode(value)
    shown = value if value is None or isinstance(value, (str, int, bool)) else serialized
    truncated = isinstance(shown, str) and len(shown) > 2000
    return dict(value=shown[:2000] if truncated else shown, truncated=truncated,
        bytes=len(serialized.encode("utf-8")), sha256=digest(value))
