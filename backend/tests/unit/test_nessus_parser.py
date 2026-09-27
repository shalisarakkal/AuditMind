import time
from pathlib import Path

import pytest

from app.models.enums import Domain, Severity
from app.services.nessus_parser import (
    DEFAULT_NESSUS_DOMAIN_MAP,
    map_nessus_domain,
    map_nessus_severity,
    parse_nessus,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parses_every_report_item_with_host_identity():
    items = parse_nessus((FIXTURES / "sample.nessus").read_bytes())

    assert len(items) == 9
    assert [item.row for item in items] == list(range(1, 10))

    apache = items[1]
    assert (apache.hostname, apache.ip) == ("web-01.acme.io", "10.0.1.10")
    assert (apache.plugin_id, apache.severity, apache.port, apache.protocol) == ("187095", "4", "443", "tcp")
    assert apache.plugin_name == "Apache 2.4.x < 2.4.58 Multiple Vulnerabilities"
    assert apache.raw["cve"] == ["CVE-2023-45802", "CVE-2023-43622"]
    assert apache.raw["solution"] == "Upgrade to Apache version 2.4.58 or later."
    assert apache.raw["cvss3_base_score"] == "9.8"

    # ReportHost named by IP, hostname from the "hostname" tag.
    assert (items[4].hostname, items[4].ip) == ("db-01", "10.0.2.20")
    # IP only.
    assert (items[7].hostname, items[7].ip) == (None, "10.0.3.30")


def test_long_plugin_output_is_truncated():
    output = "x" * 10_000
    content = f"""<NessusClientData_v2><Report name="r"><ReportHost name="10.0.0.1">
      <ReportItem port="0" protocol="tcp" severity="1" pluginID="1" pluginName="n" pluginFamily="f">
        <plugin_output>{output}</plugin_output></ReportItem></ReportHost></Report></NessusClientData_v2>"""
    [item] = parse_nessus(content.encode())
    assert len(item.raw["plugin_output"]) == 4000


def test_rejects_external_entities():
    with pytest.raises(ValueError, match="DTDs and entity declarations are not allowed"):
        parse_nessus((FIXTURES / "malicious_xxe.nessus").read_bytes())


def test_rejects_entity_expansion_quickly():
    started = time.monotonic()
    with pytest.raises(ValueError, match="DTDs and entity declarations are not allowed"):
        parse_nessus((FIXTURES / "billion_laughs.nessus").read_bytes())
    assert time.monotonic() - started < 1


@pytest.mark.parametrize(
    "content, message",
    [
        (b"<not-closed>", "Invalid .nessus file"),
        (b"<Report/>", "expected a NessusClientData_v2 export"),
        (b"", "Invalid .nessus file"),
    ],
)
def test_rejects_malformed_or_foreign_xml(content, message):
    with pytest.raises(ValueError, match=message):
        parse_nessus(content)


@pytest.mark.parametrize(
    "raw, info, expected",
    [
        ("1", "skip", Severity.low),
        ("2", "skip", Severity.medium),
        ("3", "skip", Severity.high),
        ("4", "skip", Severity.critical),
        ("0", "skip", None),
        ("0", "low", Severity.low),
    ],
)
def test_map_nessus_severity(raw, info, expected):
    assert map_nessus_severity(raw, info) == expected


@pytest.mark.parametrize("raw", ["5", "-1", "", "high"])
def test_map_nessus_severity_rejects_invalid(raw):
    with pytest.raises(ValueError, match="invalid Nessus severity"):
        map_nessus_severity(raw, "skip")


def test_map_nessus_domain():
    assert map_nessus_domain("Firewalls", DEFAULT_NESSUS_DOMAIN_MAP, Domain.vulnerability_management) == (
        Domain.network_config
    )
    assert map_nessus_domain("Web Servers", DEFAULT_NESSUS_DOMAIN_MAP, Domain.compliance_alignment) == (
        Domain.compliance_alignment
    )
