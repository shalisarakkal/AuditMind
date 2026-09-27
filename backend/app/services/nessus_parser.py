"""Parser for native Nessus exports (.nessus, "NessusClientData_v2" XML).

Uploaded XML is untrusted, so it is parsed with defusedxml: DTDs and entity
declarations are rejected outright, which blocks XXE (reading local files or
URLs) and entity-expansion ("billion laughs") attacks.

The parser only extracts data. Mapping Nessus severities and plugin families
onto our Severity/Domain enums is done by the map_* functions below, which take
their settings as arguments so per-org overrides apply (org_settings.py).
"""

import ipaddress
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.models.enums import Domain, Severity

# Nessus plugin family -> domain. Families not listed fall back to the
# configured default domain (vulnerability_management unless overridden).
DEFAULT_NESSUS_DOMAIN_MAP: dict[str, Domain] = {
    "Firewalls": Domain.network_config,
    "Port scanners": Domain.network_config,
    "SNMP": Domain.network_config,
    "DNS": Domain.network_config,
    "Windows : User management": Domain.identity_access,
    "Default Unix Accounts": Domain.identity_access,
    "Brute force attacks": Domain.identity_access,
    "Backdoors": Domain.incident_response,
    "Policy Compliance": Domain.compliance_alignment,
}

_NESSUS_SEVERITIES = {1: Severity.low, 2: Severity.medium, 3: Severity.high, 4: Severity.critical}
_MAX_PLUGIN_OUTPUT = 4000


@dataclass
class NessusItem:
    """One <ReportItem>, with its host's identity."""

    row: int  # 1-based position of the ReportItem in the file
    hostname: str | None
    ip: str | None
    plugin_id: str
    plugin_name: str
    plugin_family: str
    severity: str  # raw attribute value, "0".."4"
    port: str
    protocol: str
    synopsis: str | None
    raw: dict = field(default_factory=dict)


def parse_nessus(content: bytes) -> list[NessusItem]:
    """Raises ValueError for anything that isn't a well-formed, safe .nessus file."""
    try:
        root = ElementTree.fromstring(content)
    except DefusedXmlException:
        raise ValueError("Invalid .nessus file: DTDs and entity declarations are not allowed")
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid .nessus file: {exc}")

    if root.tag != "NessusClientData_v2":
        raise ValueError("Invalid .nessus file: expected a NessusClientData_v2 export")

    items: list[NessusItem] = []
    for host in root.iter("ReportHost"):
        hostname, ip = _host_identity(host)
        for report_item in host.iter("ReportItem"):
            items.append(_parse_item(report_item, len(items) + 1, hostname, ip))
    return items


def map_nessus_severity(raw: str, info_severity: str) -> Severity | None:
    """1-4 -> low/medium/high/critical. 0 ("Info") -> None (skip) or low,
    per info_severity ("skip" | "low"). Raises ValueError for anything else."""
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"invalid Nessus severity {raw!r}")
    if value == 0:
        return Severity.low if info_severity == "low" else None
    if value not in _NESSUS_SEVERITIES:
        raise ValueError(f"invalid Nessus severity {raw!r}")
    return _NESSUS_SEVERITIES[value]


def map_nessus_domain(plugin_family: str, domain_map: dict[str, Domain], default_domain: Domain) -> Domain:
    return domain_map.get(plugin_family, default_domain)


def _host_identity(host: Element) -> tuple[str | None, str | None]:
    tags = {tag.get("name"): (tag.text or "").strip() for tag in host.iter("tag")}
    name = (host.get("name") or "").strip()

    ip = tags.get("host-ip") or None
    hostname = tags.get("host-fqdn") or tags.get("hostname") or None
    if name:
        if _is_ip(name):
            ip = ip or name
        else:
            hostname = hostname or name
    return hostname, ip


def _parse_item(item: Element, row: int, hostname: str | None, ip: str | None) -> NessusItem:
    def text(tag: str) -> str | None:
        value = item.findtext(tag)
        return value.strip() if value else None

    plugin_output = text("plugin_output")
    raw = {
        "host": hostname or ip,
        "plugin_id": item.get("pluginID", ""),
        "plugin_name": item.get("pluginName", ""),
        "plugin_family": item.get("pluginFamily", ""),
        "severity": item.get("severity", ""),
        "port": item.get("port", ""),
        "protocol": item.get("protocol", ""),
        "svc_name": item.get("svc_name", ""),
        "risk_factor": text("risk_factor"),
        "synopsis": text("synopsis"),
        "description": text("description"),
        "solution": text("solution"),
        "cve": [cve.text.strip() for cve in item.iter("cve") if cve.text],
        "cvss3_base_score": text("cvss3_base_score"),
        "plugin_output": plugin_output[:_MAX_PLUGIN_OUTPUT] if plugin_output else None,
    }
    return NessusItem(
        row=row,
        hostname=hostname,
        ip=ip,
        plugin_id=raw["plugin_id"],
        plugin_name=raw["plugin_name"],
        plugin_family=raw["plugin_family"],
        severity=raw["severity"],
        port=raw["port"],
        protocol=raw["protocol"],
        synopsis=raw["synopsis"],
        raw=raw,
    )


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False
