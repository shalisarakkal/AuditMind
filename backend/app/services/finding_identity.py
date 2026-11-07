"""Versioned identity candidates, never reconciliation or suppression authority.

Only server-established namespaces may be passed as bindings. Uploaded IDs,
hostnames/IPs and existing legacy deduplication matches cannot establish them.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import uuid
from typing import Any

IDENTITY_VERSION = "finding-identity-v1"
NESSUS_MAPPING = "nessus-plugin-service-v1"


@dataclass(frozen=True)
class IdentityBinding:
    """Reviewed server binding lookup output; not an upload/request schema.

    A caller must resolve an unambiguous tool instance and canonical asset in the
    organization. The current publisher intentionally never constructs this.
    """
    org_id: uuid.UUID
    tool_instance_id: uuid.UUID
    canonical_asset_id: uuid.UUID


@dataclass(frozen=True)
class IdentityAssessment:
    version: str
    mapping: str | None
    candidate_key: str | None
    source_material: dict
    blocking_reasons: tuple[str, ...]

    def snapshot(self) -> dict:
        result = asdict(self)
        result["blocking_reasons"] = list(self.blocking_reasons)
        return result


def _number(value: Any, maximum: int, *, minimum: int = 0) -> int | None:
    # No bools, floats, signs, Unicode digits, truncation or unbounded integers.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    if isinstance(value, int):
        return value if minimum <= value <= maximum else None
    if not re.fullmatch(r"[0-9]{1,20}", value):
        return None
    number = int(value)
    return number if minimum <= number <= maximum else None


def assess_identity(*, org_id: uuid.UUID, scan_type: str, source: str,
                    profile: str | None, raw: dict,
                    binding: IdentityBinding | None = None) -> IdentityAssessment:
    reasons: list[str] = []
    material: dict = {}
    mapping = None
    if scan_type != "nessus" or source != "nessus" or profile is not None:
        reasons.append("source_identity_mapping_unavailable")
    else:
        mapping = NESSUS_MAPPING
        plugin = _number(raw.get("plugin_id"), 2**63 - 1, minimum=1)
        port = _number(raw.get("port"), 65535)
        protocol = raw.get("protocol")
        protocol = protocol.strip().lower() if isinstance(protocol, str) else None
        if plugin is None:
            reasons.append("stable_source_identifier_unavailable")
        if port is None or protocol not in {"tcp", "udp", "icmp", "icmpv6"}:
            reasons.append("source_instance_discriminator_invalid")
        if plugin is not None:
            material["plugin_id"] = str(plugin)
        if port is not None:
            material["port"] = port
        if protocol in {"tcp", "udp", "icmp", "icmpv6"}:
            material["protocol"] = protocol
    if binding is None:
        reasons.extend(("source_instance_not_configured", "stable_asset_mapping_not_verified"))
    elif (not isinstance(binding, IdentityBinding)
          or not all(isinstance(value, uuid.UUID) and value.int != 0 for value in
                     (org_id, binding.org_id, binding.tool_instance_id, binding.canonical_asset_id))
          or binding.org_id != org_id):
        reasons.append("identity_binding_invalid")
    key = None
    if not reasons:
        # Structural serialization prevents delimiter ambiguities. Changes to the
        # identity contract require a new version, never silent reinterpretation.
        value = dict(version=IDENTITY_VERSION, mapping=mapping, org_id=str(org_id),
                     tool_instance_id=str(binding.tool_instance_id),
                     canonical_asset_id=str(binding.canonical_asset_id), **material)
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        key = f"{IDENTITY_VERSION}:{digest}"
    return IdentityAssessment(IDENTITY_VERSION, mapping, key, material, tuple(reasons))
