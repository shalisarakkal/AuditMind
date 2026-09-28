from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.models.enums import Domain, Severity
from app.models.import_profile import ImportProfile
from app.models.organization import Organization
from app.schemas.import_profile import EndpointAgentParams, NetworkScanParams
from app.services import import_profiles
from app.services.import_profiles import (
    FAMILIES,
    builtin_profile,
    classify_os,
    custom_profile,
    parse_datetime,
    validate_profile_parts,
)
from app.services.ingestion_service import parse_csv, parse_json
from app.services.org_settings import resolve_ingestion_settings
from tests.helpers import FIXTURES

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
INGESTION = resolve_ingestion_settings(Organization(name="Acme", ingestion_overrides={}))


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(import_profiles, "utc_now", lambda: NOW)


def read(family, record, profile=None, ingestion=INGESTION):
    profile = profile or builtin_profile(FAMILIES[family])
    warnings = []
    asset, findings = profile.read_row(2, {k.lower(): v for k, v in record.items()}, ingestion, warnings)
    return asset, findings, warnings


def summary(findings):
    return [(f.domain, f.severity, f.category) for f in findings]


# --- Endpoint agent ------------------------------------------------------------

ENDPOINT = {
    "EndPointID": "EP-1",
    "DeviceName": "DEV-1",
    "AgentVersion": "v5.3",
    "LastHeartbeat": "9/27/2026 08:00",
    "ThreatsDetected": "0",
    "ComplianceStatus": "Compliant",
}


def test_healthy_endpoint_is_a_workstation_with_details_and_no_findings():
    asset, findings, warnings = read("endpoint_agent", ENDPOINT)

    assert (asset.type, asset.subtype, asset.hostname, asset.ip) == ("workstation", "endpoint", "DEV-1", None)
    assert asset.details == {"endpoint_id": "EP-1", "agent_version": "v5.3", "last_heartbeat": "9/27/2026 08:00"}
    assert findings == []
    assert warnings == []


@pytest.mark.parametrize(
    "threats, severity",
    [("0", None), ("", None), ("1", Severity.high), ("4", Severity.high), ("5", Severity.critical), ("12", Severity.critical)],
)
def test_threat_count_bands(threats, severity):
    _, findings, warnings = read("endpoint_agent", {**ENDPOINT, "ThreatsDetected": threats})

    expected = [(Domain.incident_response, severity, "Active threats detected")] if severity else []
    assert summary(findings) == expected
    assert warnings == []


@pytest.mark.parametrize("threats", ["-3", "many", "2.5"])
def test_unreadable_threat_count_is_zero_with_a_warning(threats):
    _, findings, warnings = read("endpoint_agent", {**ENDPOINT, "ThreatsDetected": threats})

    assert findings == []
    assert warnings == [f"ThreatsDetected {threats!r} isn't a count; treated as 0"]


@pytest.mark.parametrize(
    "status, severity", [("Warning", Severity.low), ("NON-COMPLIANT", Severity.medium), ("compliant", None), ("", None)]
)
def test_compliance_status(status, severity):
    _, findings, warnings = read("endpoint_agent", {**ENDPOINT, "ComplianceStatus": status})

    expected = [(Domain.compliance_alignment, severity, "Endpoint compliance")] if severity else []
    assert summary(findings) == expected
    assert warnings == []


def test_unknown_compliance_status_warns_without_a_finding():
    _, findings, warnings = read("endpoint_agent", {**ENDPOINT, "ComplianceStatus": "Unknown"})

    assert findings == []
    assert warnings == ["ComplianceStatus 'Unknown' isn't a recognised value; no finding recorded"]


@pytest.mark.parametrize(
    "heartbeat, stale",
    [
        ("9/27/2026 08:00", False),
        ("9/21/2026 12:00", False),  # exactly 7 days: not yet stale
        ("9/21/2026 11:59", True),
        ("8/8/2026 21:14", True),
        ("2026-07-01T11:30:00Z", True),
        ("2026-09-25", False),
    ],
)
def test_stale_heartbeat(heartbeat, stale):
    _, findings, _ = read("endpoint_agent", {**ENDPOINT, "LastHeartbeat": heartbeat})

    expected = [(Domain.monitoring_detection, Severity.medium, "Endpoint agent not reporting")] if stale else []
    assert summary(findings) == expected


def test_unreadable_heartbeat_skips_the_check_with_a_warning():
    asset, findings, warnings = read("endpoint_agent", {**ENDPOINT, "LastHeartbeat": "not-a-date"})

    assert findings == []
    assert warnings == ["LastHeartbeat 'not-a-date' isn't a date this profile can read; stale-agent check skipped"]
    assert asset.details["last_heartbeat"] == "not-a-date"


def test_endpoint_with_no_device_name_fails_the_row():
    with pytest.raises(ValueError, match="hostname, ip or cloud_id is required"):
        read("endpoint_agent", {**ENDPOINT, "DeviceName": ""})


def test_one_row_can_raise_several_findings_all_on_its_asset():
    asset, findings, _ = read(
        "endpoint_agent",
        {**ENDPOINT, "ThreatsDetected": "2", "ComplianceStatus": "Warning", "LastHeartbeat": "8/8/2026 21:14"},
    )

    assert len(findings) == 3
    assert {(f.row, f.hostname, f.source) for f in findings} == {(2, "DEV-1", "endpoint_agent")}
    assert findings[0].raw_data["devicename"] == "DEV-1"


def test_endpoint_settings_change_the_rules():
    params = EndpointAgentParams(
        threats_high_at=3, threats_critical_at=10, stale_after_days=30, compliance_severity={"Warning": "high"}
    )
    profile = builtin_profile(FAMILIES["endpoint_agent"])
    profile = replace(profile, params=params)

    _, findings, _ = read(
        "endpoint_agent",
        {**ENDPOINT, "ThreatsDetected": "2", "ComplianceStatus": "warning", "LastHeartbeat": "9/1/2026 12:00"},
        profile,
    )

    assert summary(findings) == [(Domain.compliance_alignment, Severity.high, "Endpoint compliance")]


# --- Network scan ----------------------------------------------------------------

SCAN = {
    "IPAddress": "10.0.5.21",
    "Hostname": "SRV-1",
    "OSDetected": "Ubuntu 22.04",
    "OpenPorts": "22,80,443",
    "Vulnerabilities": "",
    "RiskScore": "",
}


def test_clean_host_is_classified_by_os_with_ports_in_details():
    asset, findings, warnings = read("network_scan", SCAN)

    assert (asset.type, asset.subtype, asset.ip) == ("server", "Ubuntu 22.04", "10.0.5.21")
    assert asset.details == {"os": "Ubuntu 22.04", "open_ports": [22, 80, 443]}
    assert findings == []
    assert warnings == []


@pytest.mark.parametrize(
    "os_name, category",
    [
        ("Windows Server 2022", "server"),
        ("CentOS 8", "server"),
        ("Red Hat Enterprise Linux 9", "server"),
        ("Windows 11", "workstation"),
        ("Windows 10 Pro", "workstation"),
        ("macOS 14", "workstation"),
        ("Cisco IOS 15", "network_device"),
        ("JunOS 21", "network_device"),
        ("FortiOS 7.2", "network_device"),
    ],
)
def test_os_classification(os_name, category):
    warnings = []
    assert classify_os(os_name, "OSDetected", warnings) == (category, os_name)
    assert warnings == []


@pytest.mark.parametrize(
    "os_name, warning",
    [
        ("Plan 9", "OSDetected 'Plan 9' isn't a recognised operating system; recorded as a server"),
        (None, "OSDetected is blank; recorded as a server"),
    ],
)
def test_unrecognised_os_is_a_server_with_a_warning(os_name, warning):
    warnings = []
    assert classify_os(os_name, "OSDetected", warnings)[0] == "server"
    assert warnings == [warning]


def test_a_mapped_type_column_beats_the_os():
    profile = builtin_profile(FAMILIES["network_scan"])
    profile = replace(profile, column_map={**profile.column_map, "type": "Kind"})

    asset, _, warnings = read("network_scan", {**SCAN, "Kind": "Firewall", "OSDetected": "Plan 9"}, profile)

    assert (asset.type, asset.subtype) == ("network_device", "Firewall")
    assert warnings == []


@pytest.mark.parametrize(
    "score, severity",
    [("9.4", Severity.critical), ("9", Severity.critical), ("8.1", Severity.high), ("7", Severity.high),
     ("6.3", Severity.medium), ("4", Severity.medium), ("3.9", Severity.low), ("0", Severity.low)],
)
def test_risk_score_bands(score, severity):
    _, findings, warnings = read("network_scan", {**SCAN, "Vulnerabilities": "Outdated Software", "RiskScore": score})

    assert summary(findings) == [(Domain.vulnerability_management, severity, "Outdated Software")]
    assert findings[0].description == f"Outdated Software (risk score {score})."
    assert warnings == []


@pytest.mark.parametrize("score", ["", "eleven", "11", "-1"])
def test_unreadable_risk_score_is_medium_with_a_warning(score):
    _, findings, warnings = read("network_scan", {**SCAN, "Vulnerabilities": "Outdated Software", "RiskScore": score})

    assert summary(findings) == [(Domain.vulnerability_management, Severity.medium, "Outdated Software")]
    # An unreadable score isn't quoted back in the finding.
    assert findings[0].description == "Outdated Software."
    shown = repr(score) if score else "blank"
    assert warnings == [f"RiskScore is {shown}, not a score from 0 to 10; recorded as medium"]


def test_no_vulnerability_means_no_finding_even_with_a_bad_score():
    _, findings, warnings = read("network_scan", {**SCAN, "RiskScore": "eleven"})
    assert findings == []
    assert warnings == []


@pytest.mark.parametrize("vulnerability", ["TLS1.0", "tls1.0", "Weak Ciphers"])
def test_mapped_vulnerabilities_go_to_their_domain(vulnerability):
    _, findings, _ = read("network_scan", {**SCAN, "Vulnerabilities": vulnerability, "RiskScore": "4.6"})
    assert findings[0].domain == Domain.network_config


def test_risky_ports_each_raise_a_finding():
    _, findings, warnings = read("network_scan", {**SCAN, "OpenPorts": "135,779,21,23,21"})

    assert summary(findings) == [
        (Domain.network_config, Severity.medium, "Open port 135 (RPC)"),
        (Domain.network_config, Severity.medium, "Open port 21 (FTP)"),
        (Domain.network_config, Severity.high, "Open port 23 (Telnet)"),
    ]
    assert warnings == []


def test_bad_port_entries_are_skipped_with_a_warning():
    asset, _, warnings = read("network_scan", {**SCAN, "OpenPorts": "22; abc 70000,443"})

    assert asset.details["open_ports"] == [22, 443]
    assert warnings == ["OpenPorts: 'abc' isn't a port number; skipped", "OpenPorts: '70000' isn't a port number; skipped"]


def test_ports_can_be_a_json_list():
    asset, _, _ = read("network_scan", {**SCAN, "OpenPorts": [3389, "445"]})
    assert asset.details["open_ports"] == [3389, 445]


def test_unusual_ip_warns_but_imports():
    asset, _, warnings = read("network_scan", {**SCAN, "IPAddress": "127.12.12.238"})
    assert asset.ip == "127.12.12.238"
    assert warnings == ["ip 127.12.12.238 is a loopback address; imported anyway"]


def test_invalid_ip_fails_the_row():
    with pytest.raises(ValueError, match="not a valid IP address"):
        read("network_scan", {**SCAN, "IPAddress": "999.1.1.1"})


# --- Cloud inventory and generic profiles --------------------------------------

CLOUD = {
    "ResourceID": "arn:aws:lambda:us-east-1:1:function:x",
    "ResourceName": "invoice-processor",
    "ResourceType": "Lambda",
    "Region": "us-east-1",
    "Environment": "production",
    "Tags": "billing;pci",
}


def test_cloud_resource_type_names_resolve():
    asset, findings, warnings = read("cloud_inventory", CLOUD)

    assert (asset.type, asset.subtype, asset.hostname) == ("cloud_resource", "Lambda", "invoice-processor")
    assert (asset.cloud_id, asset.environment, asset.tags) == (CLOUD["ResourceID"], "production", ["billing", "pci"])
    assert asset.details == {"region": "us-east-1"}
    assert (findings, warnings) == ([], [])


def test_unknown_cloud_type_fails_the_row():
    with pytest.raises(ValueError, match="type 'Hologram' must be one of"):
        read("cloud_inventory", {**CLOUD, "ResourceType": "Hologram"})


def test_type_names_layer_org_then_profile():
    ingestion = resolve_ingestion_settings(
        Organization(name="Acme", ingestion_overrides={"asset_type_aliases": {"Hologram": "application"}})
    )
    asset, _, _ = read("cloud_inventory", {**CLOUD, "ResourceType": "Hologram"}, ingestion=ingestion)
    assert (asset.type, asset.subtype) == ("application", "Hologram")

    profile = builtin_profile(FAMILIES["cloud_inventory"])
    params = profile.params.model_copy(update={"type_aliases": {"Hologram": "server"}})
    profile = replace(profile, params=params)
    asset, _, _ = read("cloud_inventory", {**CLOUD, "ResourceType": "Hologram"}, profile, ingestion)
    assert asset.type == "server"  # the profile's own name wins


def test_generic_profiles_behave_like_the_plain_imports():
    asset, findings, _ = read("generic_assets", {"type": "laptop", "hostname": "pc-1", "tags": "a;b"})
    assert (asset.type, asset.subtype, asset.tags, findings) == ("workstation", "laptop", ["a", "b"], [])

    asset, findings, _ = read("generic_findings", {"hostname": "pc-1", "domain": "network_config", "severity": "LOW"})
    assert asset is None
    assert summary(findings) == [(Domain.network_config, Severity.low, None)]
    assert findings[0].source == "manual"


def test_renamed_columns_and_default_values():
    profile = builtin_profile(FAMILIES["generic_assets"])
    params = profile.params.model_copy(update={"default_values": {"type": "server", "environment": "production"}})
    profile = replace(
        profile, column_map={"hostname": "Device_Name", "ip": "IP Addr", "environment": "Env"}, params=params
    )

    asset, _, _ = read("generic_assets", {"Device_Name": "web-9", "IP Addr": "10.1.1.9", "Env": ""}, profile)

    assert (asset.type, asset.hostname, asset.ip, asset.environment) == ("server", "web-9", "10.1.1.9", "production")


def test_non_object_json_record_fails_the_row():
    with pytest.raises(ValueError, match="record must be an object"):
        builtin_profile(FAMILIES["cloud_inventory"]).read_row(1, ["not", "an", "object"], INGESTION, [])


# --- The sample exports, end to end (no DB) -----------------------------------


@pytest.mark.parametrize(
    "family, filename, ok_rows, failed_rows, finding_count, warning_count",
    [
        ("endpoint_agent", "endpoint_agents.csv", 7, [7], 8, 3),
        ("network_scan", "network_scan.csv", 7, [8], 12, 4),
        ("cloud_inventory", "cloud_inventory.csv", 7, [9], 0, 0),
    ],
)
def test_sample_exports(family, filename, ok_rows, failed_rows, finding_count, warning_count):
    profile = builtin_profile(FAMILIES[family])
    ok, failed, findings, warnings = 0, [], 0, 0
    for row, record in parse_csv((FIXTURES / filename).read_bytes()):
        row_warnings = []
        try:
            _, row_findings = profile.read_row(row, record, INGESTION, row_warnings)
        except ValueError:
            failed.append(row)
            continue
        ok += 1
        findings += len(row_findings)
        warnings += len(row_warnings)
    assert (ok, failed, findings, warnings) == (ok_rows, failed_rows, finding_count, warning_count)


# --- Profile validation ------------------------------------------------------------


def test_parse_datetime_formats():
    assert parse_datetime("9/21/2026 15:48") == datetime(2026, 9, 21, 15, 48, tzinfo=timezone.utc)
    assert parse_datetime("03/04/2026") == datetime(2026, 3, 4, tzinfo=timezone.utc)
    assert parse_datetime("03/04/2026", day_first=True) == datetime(2026, 4, 3, tzinfo=timezone.utc)
    assert parse_datetime("21/09/2026 15:48", day_first=True) == datetime(2026, 9, 21, 15, 48, tzinfo=timezone.utc)
    assert parse_datetime("9/21/2026 3:48 PM") == datetime(2026, 9, 21, 15, 48, tzinfo=timezone.utc)
    assert parse_datetime("2026-09-21T15:48:00+02:00").utcoffset().total_seconds() == 7200
    assert parse_datetime("21/09/2026") is None  # month 21
    assert parse_datetime("yesterday") is None


def test_validate_profile_parts_accepts_a_good_copy():
    family = FAMILIES["endpoint_agent"]
    column_map, params = validate_profile_parts(
        family, {"hostname": " Device_Name ", "threats_detected": "Threats"}, {"stale_after_days": 14}
    )
    assert column_map == {"hostname": "Device_Name", "threats_detected": "Threats"}
    assert params.stale_after_days == 14
    assert params.threats_high_at == 1  # unspecified settings take the defaults


@pytest.mark.parametrize(
    "column_map, params, message",
    [
        ({"colour": "X"}, {}, "'colour' is not a field of Endpoint agent export"),
        ({"hostname": " "}, {}, "the column for 'hostname' can't be blank"),
        ({}, {}, "must map at least one field"),
        ({"hostname": "H"}, {"stale_after_days": 0}, "params.stale_after_days"),
        ({"hostname": "H"}, {"threats_high_at": 5, "threats_critical_at": 2}, "threats_critical_at must be at least"),
        ({"hostname": "H"}, {"compliance_severity": {"warning": "urgent"}}, "params.compliance_severity.warning"),
        ({"hostname": "H"}, {"type_aliases": {"pc": "desk"}}, "must be one of"),
        ({"hostname": "H"}, {"default_values": {"colour": "red"}}, "default_values: 'colour' is not a field"),
        ({"hostname": "H"}, {"formula": "=1+1"}, "params.formula: Extra inputs are not permitted"),
    ],
)
def test_validate_profile_parts_rejects(column_map, params, message):
    with pytest.raises(ValueError, match=message):
        validate_profile_parts(FAMILIES["endpoint_agent"], column_map, params)


@pytest.mark.parametrize(
    "params, message",
    [
        ({"risky_ports": {"http": {"label": "HTTP", "severity": "low"}}}, "'http' is not a port number"),
        ({"risky_ports": {"80": {"label": "", "severity": "low"}}}, "params.risky_ports.80.label"),
        ({"risk_high_at": 9.5}, "risk bands must go critical >= high >= medium"),
        ({"vulnerability_domains": {"X": "nope"}}, "params.vulnerability_domains.X"),
    ],
)
def test_network_settings_validation(params, message):
    with pytest.raises(ValueError, match=message):
        validate_profile_parts(FAMILIES["network_scan"], {"ip": "IP"}, params)


def test_network_port_keys_are_normalised():
    params = NetworkScanParams(risky_ports={"0080": {"label": "HTTP", "severity": "low"}})
    assert list(params.risky_ports) == ["80"]


def test_custom_profile_from_a_stored_row():
    row = ImportProfile(
        name="Our EDR", family="endpoint_agent", column_map={"hostname": "Host"}, params={"stale_after_days": 3}
    )
    profile = custom_profile(row)
    assert (profile.name, profile.builtin, profile.family.key, profile.params.stale_after_days) == (
        "Our EDR", False, "endpoint_agent", 3,
    )

    row.params = {"stale_after_days": -1}
    with pytest.raises(ValueError):
        custom_profile(row)


# --- Alternative column names, other columns, cloud IDs --------------------------


def test_the_first_alternative_column_present_is_read():
    asset, _, _ = read("cloud_inventory", {"ResourceID": "res-1", "Type": "Lambda", "Name": "fn-a"})
    assert (asset.cloud_id, asset.type, asset.subtype, asset.hostname) == ("res-1", "cloud_resource", "Lambda", "fn-a")

    # ResourceType is listed first, so it wins over Type when both are present.
    asset, _, _ = read("cloud_inventory", {"ResourceID": "res-1", "ResourceType": "Bucket", "Type": "Lambda"})
    assert asset.subtype == "Bucket"


def test_a_cloud_id_alone_identifies_an_asset_and_object_tags_are_flattened():
    asset, _, warnings = read(
        "cloud_inventory",
        {"Provider": "Azure", "ResourceID": "res-00000", "Type": "Lambda", "Region": "us-east-1",
         "Owner": "team1", "Tags": {"env": "test", "app": "risk"}, "Status": "Running"},
    )

    assert (asset.hostname, asset.ip, asset.cloud_id) == (None, None, "res-00000")
    assert asset.tags == ["env:test", "app:risk"]
    # Region is a field; the columns no field reads are kept as details.
    assert asset.details == {"region": "us-east-1", "provider": "Azure", "owner": "team1", "status": "Running"}
    assert warnings == []


def test_other_columns_are_kept_only_when_the_profile_says_so():
    asset, _, _ = read("generic_assets", {"type": "server", "hostname": "h", "rack": "B2"})
    assert asset.details == {}

    profile = builtin_profile(FAMILIES["generic_assets"])
    profile = replace(profile, params=profile.params.model_copy(update={"keep_other_columns": True}))
    asset, _, _ = read("generic_assets", {"type": "server", "hostname": "h", "rack": "B2", "empty": " "}, profile)
    assert asset.details == {"rack": "B2"}


def test_a_mapped_fields_value_wins_over_a_kept_column_of_the_same_name():
    profile = builtin_profile(FAMILIES["network_scan"])
    asset, _, _ = read("network_scan", {**SCAN, "os": "ignored"}, profile)
    # "os" is an alternative name of the OS field, so it counts as read.
    assert asset.details["os"] == "Ubuntu 22.04"


@pytest.mark.parametrize("value", ["None", "n/a", "NULL", "-"])
def test_no_vulnerability_markers_raise_no_finding(value):
    _, findings, warnings = read("network_scan", {**SCAN, "Vulnerabilities": value, "RiskScore": "9.9"})
    assert (findings, warnings) == ([], [])


def test_blank_alternative_column_names_are_rejected():
    with pytest.raises(ValueError, match="has a blank alternative"):
        validate_profile_parts(FAMILIES["cloud_inventory"], {"type": "ResourceType||Type"}, {})
    column_map, _ = validate_profile_parts(FAMILIES["cloud_inventory"], {"type": " ResourceType | Type "}, {})
    assert column_map == {"type": "ResourceType|Type"}


# --- Directory (Active Directory) export ---------------------------------------------

DIRECTORY = {
    "AssetID": "AD-1",
    "Hostname": "HOST-1",
    "Type": "Laptop",
    "OS": "Windows 11",
    "Owner": "user1@acme.io",
    "LastLogin": "2026-09-25 08:48:47",
    "Status": "Active",
}


def test_active_directory_account_becomes_an_asset_with_details():
    asset, findings, warnings = read("directory", DIRECTORY)

    assert (asset.type, asset.subtype, asset.hostname) == ("workstation", "Laptop", "HOST-1")
    assert asset.details == {
        "asset_id": "AD-1", "os": "Windows 11", "owner": "user1@acme.io", "last_login": "2026-09-25 08:48:47",
    }
    assert (findings, warnings) == ([], [])


def test_directory_type_falls_back_to_the_os():
    asset, _, _ = read("directory", {**DIRECTORY, "Type": ""})
    assert (asset.type, asset.subtype) == ("workstation", "Windows 11")


@pytest.mark.parametrize(
    "status, finding, warning",
    [
        ("Disabled", True, None),
        ("LOCKED", True, None),
        ("False", True, None),
        ("Pending", False, None),
        ("Enabled", False, None),
        ("Quarantined", False, "Status 'Quarantined' isn't a recognised value; no finding recorded"),
    ],
)
def test_directory_account_status(status, finding, warning):
    _, findings, warnings = read("directory", {**DIRECTORY, "Status": status})

    expected = [(Domain.identity_access, Severity.low, "Disabled directory account")] if finding else []
    assert summary(findings) == expected
    assert warnings == ([warning] if warning else [])


@pytest.mark.parametrize("login, stale", [("2026-06-30 12:00:00", False), ("2026-06-30 11:59:00", True), ("5/1/2026", True)])
def test_stale_directory_login(login, stale):
    _, findings, _ = read("directory", {**DIRECTORY, "LastLogin": login})
    expected = [(Domain.identity_access, Severity.medium, "Stale directory account")] if stale else []
    assert summary(findings) == expected


def test_directory_settings_change_the_rules():
    profile = builtin_profile(FAMILIES["directory"])
    params = profile.params.model_copy(update={"stale_login_days": 2, "stale_severity": Severity.high, "ok_values": ["active", "quarantined"]})
    profile = replace(profile, params=params)

    _, findings, warnings = read("directory", {**DIRECTORY, "Status": "Quarantined"}, profile)

    assert summary(findings) == [(Domain.identity_access, Severity.high, "Stale directory account")]
    assert warnings == []


def test_directory_statuses_cannot_be_both_disabled_and_fine():
    with pytest.raises(ValueError, match="can't be both disabled and fine"):
        validate_profile_parts(FAMILIES["directory"], {"hostname": "Hostname"}, {"ok_values": ["Disabled"]})


@pytest.mark.parametrize(
    "family, filename, ok_rows, failed_rows, finding_count, warning_count",
    [
        ("directory", "active_directory.csv", 5, [7], 2, 2),
        ("cloud_inventory", "cloud_assets.json", 4, [5, 6], 0, 0),
    ],
)
def test_more_sample_exports(family, filename, ok_rows, failed_rows, finding_count, warning_count):
    profile = builtin_profile(FAMILIES[family])
    content = (FIXTURES / filename).read_bytes()
    records = parse_csv(content) if filename.endswith(".csv") else parse_json(content, profile.json_list_key)
    ok, failed, findings, warnings = 0, [], 0, 0
    for row, record in records:
        row_warnings = []
        try:
            _, row_findings = profile.read_row(row, record, INGESTION, row_warnings)
        except ValueError:
            failed.append(row)
            continue
        ok += 1
        findings += len(row_findings)
        warnings += len(row_warnings)
    assert (ok, failed, findings, warnings) == (ok_rows, failed_rows, finding_count, warning_count)
