import json

import pytest

from app.models.enums import Domain, Severity
from app.models.organization import Organization
from app.services.ingestion_service import (
    IngestionError,
    detect_format,
    nessus_finding,
    parse_csv,
    parse_json,
    scan_type_for,
    validate_asset,
    validate_finding,
)
from app.services.nessus_parser import NessusItem
from app.services.org_settings import resolve_ingestion_settings

# --- detect_format / scan types ---


@pytest.mark.parametrize(
    "filename, kind, expected",
    [
        ("assets.csv", "assets", "csv"),
        ("ASSETS.JSON", "assets", "json"),
        ("scan.nessus", "findings", "nessus"),
        ("my.findings.v2.csv", "findings", "csv"),
    ],
)
def test_detect_format(filename, kind, expected):
    assert detect_format(filename, kind) == expected


@pytest.mark.parametrize(
    "filename, kind",
    [("scan.nessus", "assets"), ("notes.txt", "findings"), ("noextension", "assets"), (None, "assets"), ("", "findings")],
)
def test_detect_format_rejects_unsupported(filename, kind):
    with pytest.raises(IngestionError, match="Unsupported file type"):
        detect_format(filename, kind)


def test_scan_types():
    assert scan_type_for("assets", "csv") == "asset_import"
    assert scan_type_for("assets", "json") == "asset_import"
    assert scan_type_for("findings", "csv") == "findings_csv"
    assert scan_type_for("findings", "json") == "findings_json"
    assert scan_type_for("findings", "nessus") == "nessus"


# --- parse_csv ---


def test_parse_csv_line_numbers_and_case_insensitive_headers():
    records = parse_csv(b"Type, HostName \nserver,a\nserver,b\n")
    assert records == [(2, {"type": "server", "hostname": "a"}), (3, {"type": "server", "hostname": "b"})]


def test_parse_csv_strips_excel_bom_and_ignores_extra_cells():
    records = parse_csv("﻿type,hostname\nserver,a,unexpected-extra\n".encode("utf-8"))
    assert records == [(2, {"type": "server", "hostname": "a"})]


def test_parse_csv_multiline_quoted_field_keeps_counting_lines():
    records = parse_csv(b'type,description\nserver,"line one\nline two"\nserver,x\n')
    assert [line for line, _ in records] == [3, 4]


def test_parse_csv_errors():
    with pytest.raises(IngestionError, match="no header"):
        parse_csv(b"")
    with pytest.raises(IngestionError, match="UTF-8"):
        parse_csv("type\nserveur\xe9".encode("latin-1"))


# --- parse_json ---


def test_parse_json_list_or_wrapped():
    assert parse_json(b'[{"Type": "server"}]', "assets") == [(1, {"type": "server"})]
    assert parse_json(b'{"assets": [{"type": "server"}, 5]}', "assets") == [(1, {"type": "server"}), (2, 5)]


@pytest.mark.parametrize("content", [b"{not json", b'{"other": []}', b'"a string"'])
def test_parse_json_errors(content):
    with pytest.raises(IngestionError):
        parse_json(content, "assets")


# --- validate_asset ---


def test_validate_asset_normalises_fields():
    row = validate_asset(
        7,
        {"type": " Server ", "hostname": "web-01", "ip": " 10.0.0.1 ", "tags": "a; b,,c", "environment": ""},
    )
    assert row.row == 7
    assert row.type == "server"
    assert row.ip == "10.0.0.1"
    assert row.tags == ["a", "b", "c"]
    assert row.environment is None


def test_validate_asset_accepts_ip_or_hostname_alone_and_json_types():
    assert validate_asset(1, {"type": "workstation", "ip": "2001:DB8::1"}).ip == "2001:db8::1"
    assert validate_asset(1, {"type": "database", "hostname": "db", "tags": ["x", " "]}).tags == ["x"]
    assert validate_asset(1, {"type": "server", "hostname": 12345}).hostname == "12345"


@pytest.mark.parametrize(
    "record, message",
    [
        ({"hostname": "a"}, "type is required"),
        ({"type": "hologram", "hostname": "a"}, "type 'hologram' must be one of"),
        ({"type": "server"}, "hostname, ip or cloud_id is required"),
        ({"type": "server", "ip": "999.1.1.1"}, "not a valid IP address"),
        ({"type": "server", "hostname": "x" * 256}, "hostname is longer than 255"),
        ({"type": "server", "hostname": "a", "tags": 5}, "tags must be"),
        ({"type": "server", "hostname": {"nested": 1}}, "hostname must be text"),
        ({"type": True, "hostname": "a"}, "type must be text"),
        ("not an object", "record must be an object"),
    ],
)
def test_validate_asset_errors(record, message):
    with pytest.raises(ValueError, match=message):
        validate_asset(1, record)


# --- validate_finding ---


def test_validate_finding_enums_are_case_insensitive_and_source_defaults():
    row = validate_finding(2, {"hostname": "a", "domain": "Identity_Access", "severity": "HIGH"})
    assert row.domain == Domain.identity_access
    assert row.severity == Severity.high
    assert row.source == "manual"
    assert row.category is None
    assert row.raw_data == {"hostname": "a", "domain": "Identity_Access", "severity": "HIGH"}


@pytest.mark.parametrize(
    "record, message",
    [
        ({"hostname": "a", "severity": "high"}, "domain is required"),
        ({"hostname": "a", "domain": "nope", "severity": "high"}, "domain 'nope' must be one of"),
        ({"hostname": "a", "domain": "network_config", "severity": "urgent"}, "severity 'urgent' must be one of"),
        ({"domain": "network_config", "severity": "low"}, "hostname, ip or cloud_id is required"),
    ],
)
def test_validate_finding_errors(record, message):
    with pytest.raises(ValueError, match=message):
        validate_finding(1, record)


# --- nessus_finding ---


def _item(**overrides) -> NessusItem:
    values = dict(
        row=1,
        hostname="web-01",
        ip="10.0.0.1",
        plugin_id="187095",
        plugin_name="Apache Vulns",
        plugin_family="Firewalls",
        severity="4",
        port="443",
        protocol="tcp",
        synopsis="Multiple issues.",
        raw={"plugin_id": "187095"},
    )
    return NessusItem(**{**values, **overrides})


def _settings(**overrides):
    return resolve_ingestion_settings(Organization(name="x", ingestion_overrides=overrides))


def test_nessus_finding_maps_fields():
    row = nessus_finding(_item(), _settings())
    assert row.severity == Severity.critical
    assert row.domain == Domain.network_config  # "Firewalls" in the built-in map
    assert row.category == "Nessus 187095 (443/tcp)"
    assert row.description == "Apache Vulns: Multiple issues."
    assert row.source == "nessus"
    assert row.raw_data == {"plugin_id": "187095"}


def test_nessus_finding_port_zero_and_unmapped_family():
    row = nessus_finding(_item(port="0", plugin_family="General", synopsis=None), _settings())
    assert row.category == "Nessus 187095"
    assert row.description == "Apache Vulns"
    assert row.domain == Domain.vulnerability_management


def test_nessus_finding_info_items_follow_settings():
    assert nessus_finding(_item(severity="0"), _settings()) is None
    assert nessus_finding(_item(severity="0"), _settings(nessus_info_severity="low")).severity == Severity.low


def test_nessus_finding_invalid_severity_and_missing_host():
    with pytest.raises(ValueError, match="invalid Nessus severity"):
        nessus_finding(_item(severity="9"), _settings())
    with pytest.raises(ValueError, match="hostname, ip or cloud_id is required"):
        nessus_finding(_item(hostname=None, ip=None), _settings())


def test_json_raw_data_round_trips():
    row = validate_finding(1, {"ip": "10.0.0.1", "domain": "backup_recovery", "severity": "low", "extra": [1, 2]})
    assert json.loads(json.dumps(row.raw_data))["extra"] == [1, 2]


# --- Type names, subtypes and warnings ---


def test_validate_asset_resolves_type_names_to_a_category_and_subtype():
    row = validate_asset(1, {"type": "Laptop", "hostname": "pc-1"})
    assert (row.type, row.subtype) == ("workstation", "Laptop")
    # An explicit subtype column wins over the name.
    row = validate_asset(1, {"type": "vm", "subtype": "hyper-v guest", "hostname": "vm-1"})
    assert (row.type, row.subtype) == ("server", "hyper-v guest")
    # A category name has no subtype.
    assert validate_asset(1, {"type": "Workstation", "hostname": "pc-2"}).subtype is None


def test_validate_asset_uses_the_given_type_names():
    with pytest.raises(ValueError, match="must be one of"):
        validate_asset(1, {"type": "hypervisor", "hostname": "h"}, {})
    assert validate_asset(1, {"type": "hypervisor", "hostname": "h"}, {"hypervisor": "server"}).type == "server"


@pytest.mark.parametrize(
    "ip, kind",
    [
        ("127.12.12.238", "loopback"),
        ("::1", "loopback"),
        ("0.0.0.0", "unspecified"),
        ("169.254.10.1", "link-local"),
        ("fe80::1", "link-local"),
        ("224.0.0.5", "multicast"),
        ("251.88.70.177", "reserved"),
    ],
)
def test_unusual_ips_are_accepted_with_a_warning(ip, kind):
    warnings = []
    row = validate_asset(1, {"type": "server", "ip": ip}, warnings=warnings)
    assert row.ip == ip
    article = "an" if kind == "unspecified" else "a"
    assert warnings == [f"ip {ip} is {article} {kind} address; imported anyway"]


@pytest.mark.parametrize("ip", ["10.0.0.1", "192.168.1.20", "172.16.4.4", "8.8.8.8", "2001:db8::1"])
def test_normal_and_private_ips_have_no_warning(ip):
    warnings = []
    validate_asset(1, {"type": "server", "ip": ip}, warnings=warnings)
    assert warnings == []


def test_findings_and_nessus_items_warn_about_unusual_ips_too():
    warnings = []
    validate_finding(1, {"ip": "127.0.0.1", "domain": "backup_recovery", "severity": "low"}, warnings)
    nessus_finding(_item(hostname=None, ip="0.0.0.0"), _settings(), warnings)
    assert warnings == [
        "ip 127.0.0.1 is a loopback address; imported anyway",
        "ip 0.0.0.0 is an unspecified address; imported anyway",
    ]


def test_profile_imports_accept_csv_and_json_only():
    assert detect_format("export.csv", "profile") == "csv"
    assert detect_format("export.json", "profile") == "json"
    with pytest.raises(IngestionError):
        detect_format("scan.nessus", "profile")


def test_a_cloud_id_alone_identifies_assets_and_findings():
    row = validate_asset(1, {"type": "Lambda", "cloud_id": "arn:aws:lambda:x"})
    assert (row.type, row.hostname, row.ip, row.cloud_id) == ("cloud_resource", None, None, "arn:aws:lambda:x")
    finding = validate_finding(1, {"cloud_id": "arn:aws:lambda:x", "domain": "network_config", "severity": "low"})
    assert finding.cloud_id == "arn:aws:lambda:x"


@pytest.mark.parametrize(
    "tags, expected",
    [({"env": "prod", "app": "risk"}, ["env:prod", "app:risk"]), ({"pci": ""}, ["pci"]), ({}, None)],
)
def test_tags_given_as_an_object(tags, expected):
    assert validate_asset(1, {"type": "server", "hostname": "h", "tags": tags}).tags == expected
