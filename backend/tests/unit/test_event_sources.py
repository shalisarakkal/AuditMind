"""Event logs summed up into findings (Phase 2f part 2)."""

import dataclasses
import pickle

import pytest

from app.models.enums import Severity
from app.services import event_sources
from app.services.event_sources import lookup
from app.services.import_profiles import FAMILIES, builtin_profile, validate_profile_parts
from app.services.org_settings import resolve_ingestion_settings


class _Org:
    ingestion_overrides: dict = {}


INGESTION = resolve_ingestion_settings(_Org())


def reader_for(key: str, params: dict | None = None):
    family = FAMILIES[key]
    profile = builtin_profile(family)
    if params is not None:
        _, parsed = validate_profile_parts(family, profile.column_map, params)
        profile = dataclasses.replace(profile, params=parsed)
    return profile.start()


def read(reader, records: list[dict], start: int = 1) -> None:
    for row, record in enumerate(records, start=start):
        # As the file reader gives them: top-level keys in lower case.
        reader.read_row(row, {k.lower(): v for k, v in record.items()}, INGESTION, [])


def findings_of(reader) -> dict:
    """{rule title: finding} (the description starts with the title)."""
    return {f.description.split(":")[0]: f for staged in reader.finish() for f in staged.findings}


def tally(key: str, records: list[dict], params: dict | None = None) -> dict:
    """The findings `records` give, as {rule title: finding}."""
    reader = reader_for(key, params)
    read(reader, records)
    return findings_of(reader)


def test_lookup_reads_columns_and_nested_paths():
    record = {"user.name": "ann", "useridentity": {"type": "Root", "arn": "arn:aws:iam::1:root"}}
    assert lookup(record, "user.name") == "ann"  # a dotted column (OSSEM CSV)
    assert lookup(record, "useridentity.arn") == "arn:aws:iam::1:root"
    assert lookup(record, "useridentity.type") == "Root"
    assert lookup(record, "useridentity.missing") is None
    assert lookup(record, "user.name.first") is None


def test_azure_activity_flat_and_as_exported():
    flat = {"time": "2026-06-10 07:13:48", "operation_name": "Microsoft.Authorization/roleAssignments/write",
            "status": "Succeeded", "caller": "ann@acme.io", "subscription_id": "sub-1"}
    exported = {"eventTimestamp": "2026-06-12T01:00:00Z",
                "operationName": {"value": "Microsoft.Authorization/roleAssignments/write"},
                "status": {"value": "Succeeded"}, "caller": "bob@acme.io", "subscriptionId": "sub-2"}
    findings = tally("azure_activity", [flat, exported, {**flat, "status": "Failed"}])
    created = findings["Role assignment created"]
    assert (created.event_count, created.severity) == (2, Severity.high)
    # Two subscriptions: counted, and which ones (so another log's differs).
    assert created.category.startswith("Role assignment created in 2 subscriptions [")
    assert created.category.endswith("] (2026-06-10 to 2026-06-12)")
    assert created.description == "Role assignment created: 2 events by 2 callers in 2 subscriptions."
    assert created.details["actors"] == {"distinct": "2", "top": [{"value": "ann@acme.io", "events": 1},
                                                                    {"value": "bob@acme.io", "events": 1}]}
    assert findings["Role assignment attempt failed"].event_count == 1
    assert "Failed operations" not in findings  # needs 10 or more


def test_cloudtrail_root_activity_and_failed_calls():
    exported = {"eventTime": "2026-07-01T00:00:00Z", "eventName": "ConsoleLogin",
                "userIdentity": {"type": "Root", "arn": "arn:aws:iam::1:root"}, "awsRegion": "us-east-1"}
    findings = tally("aws_cloudtrail", [
        exported,
        {"event_time": "2026-07-02 00:00:00", "event_name": "AuthorizeSecurityGroupIngress", "user_identity": "root"},
        # A call that failed opened nothing.
        {**exported, "eventName": "AuthorizeSecurityGroupIngress", "errorCode": "AccessDenied"},
        # A failed sign-in has no errorCode: its message and result say so.
        {**exported, "errorMessage": "Failed authentication", "responseElements": {"ConsoleLogin": "Failure"}},
        {**exported, "responseElements": {"ConsoleLogin": "Failure"}},
    ])
    assert findings["Root account console sign-in"].severity == Severity.critical
    assert findings["Root account console sign-in"].description.endswith("by 1 identity in 1 region.")
    assert findings["Activity by the root account"].event_count == 1
    assert findings["Security group opened"].event_count == 1


def test_gcp_success_and_permission_denied():
    exported = {"timestamp": "2026-08-01T00:00:00Z", "protoPayload": {
        "methodName": "v1.compute.firewalls.patch", "authenticationInfo": {"principalEmail": "ann@acme.io"}},
        "resource": {"labels": {"project_id": "p1"}}}
    findings = tally("gcp_audit", [
        exported,
        {**exported, "protoPayload": {**exported["protoPayload"], "status": {"code": 7}}},
        {"timestamp": "2026-08-02 00:00:00", "method_name": "compute.firewalls.patch", "status": "OK",
         "principal_email": "bob@acme.io", "project_id": "p2"},
    ])
    assert findings["Firewall rule changed"].event_count == 2  # the denied one changed nothing
    assert findings["Permission denied"].event_count == 1


def test_ossem_indicators_and_a_finding_per_host():
    row = {"timestamp": "2026-06-01 00:00:00", "user.name": "ann", "process.command_line": "powershell.exe -nop -enc AAAA",
           "registry.key": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "file.path": r"C:\Temp\payload.dll"}
    findings = tally("ossem_events", [row, {**row, "process.command_line": "cmd.exe /c whoami", "registry.key": "",
                                            "file.path": r"C:\Users\Public\script.py"}])
    assert {name: f.event_count for name, f in findings.items()} == {
        "Encoded PowerShell command": 1,
        "Run key persistence": 1,
        "DLL written to a Temp folder": 1,
        "whoami reconnaissance": 1,
    }
    assert all(f.hostname is None for f in findings.values())

    reader = builtin_profile(FAMILIES["ossem_events"]).start()
    for n, host in enumerate(["web-1", "web-2", "web-1"], start=1):
        reader.read_row(n, {**row, "host.name": host}, INGESTION, [])
    encoded = [f for staged in reader.finish() for f in staged.findings if f.category.startswith("Encoded")]
    assert sorted((f.hostname, f.event_count) for f in encoded) == [("web-1", 2), ("web-2", 1)]


def test_rules_can_be_turned_off_or_given_another_severity():
    record = {"time": "2026-06-10 07:13:48", "operation_name": "x/roleAssignments/write", "status": "Succeeded",
              "caller": "ann"}
    findings = tally("azure_activity", [record], {"rules": {"role_assignment_created": {"severity": "critical"}}})
    assert findings["Role assignment created"].severity == Severity.critical
    findings = tally("azure_activity", [record], {"rules": {"role_assignment_created": {"enabled": False}}})
    assert findings == {}
    with pytest.raises(ValueError, match="not a rule of Azure Activity Log"):
        validate_profile_parts(FAMILIES["azure_activity"], {"time": "time"}, {"rules": {"nope": {}}})


def test_events_without_a_readable_time_still_count():
    findings = tally("azure_activity", [{"operation_name": "x/roleAssignments/write", "status": "Succeeded"}])
    assert findings["Role assignment created"].category == "Role assignment created (no dates)"


def test_distinct_counts_stop_at_5000():
    records = [{"time": "2026-06-10 07:13:48", "operation_name": "x/roleAssignments/write", "status": "Succeeded",
                "caller": f"user{n}"} for n in range(5003)]
    finding = tally("azure_activity", records)["Role assignment created"]
    assert finding.description == "Role assignment created: 5,003 events by over 5,000 callers."
    assert len(finding.details["actors"]["top"]) == 10


def test_a_single_scope_is_named_in_the_title():
    record = {"time": "2026-06-10 07:13:48", "operation_name": "x/roleAssignments/write", "status": "Succeeded",
              "caller": "ann", "subscription_id": "sub-A"}
    finding = tally("azure_activity", [record])["Role assignment created"]
    assert finding.category == "Role assignment created in sub-A (2026-06-10 to 2026-06-10)"
    other = tally("azure_activity", [{**record, "subscription_id": "sub-B"}])["Role assignment created"]
    assert other.category != finding.category  # another subscription's log isn't a duplicate


def test_hosts_are_grouped_without_regard_to_case_and_capped(monkeypatch):
    monkeypatch.setattr(event_sources, "MAX_HOSTS", 2)
    row = {"timestamp": "2026-06-01 00:00:00", "process.command_line": "cmd.exe /c whoami"}
    reader = reader_for("ossem_events")
    read(reader, [{**row, "host.name": host} for host in ("WS01", "ws01", "web-2", "db-3", "db-4", "DB-4")])
    found = [f for staged in reader.finish() for f in staged.findings]
    assert [(f.hostname, f.event_count) for f in found] == [("WS01", 2), ("web-2", 1), (None, 3)]
    other = found[2]
    assert other.description.endswith("on 2 more hosts (the first 2 each have their own finding).")  # db-3, db-4
    assert "on other hosts [" in other.category


def test_values_and_examples_are_bounded():
    deep: dict = {"leaf": "x"}
    for _ in range(50):
        deep = {"next": deep}
    record = {"time": "2026-06-10 07:13:48", "operation_name": "x/roleAssignments/write", "status": "Succeeded",
              "caller": "c" * 10_000, "nested": deep, "big": ["y" * 300] * 100}
    finding = tally("azure_activity", [record])["Role assignment created"]
    [actor] = finding.details["actors"]["top"]
    assert len(actor["value"]) == event_sources.VALUE_MAX
    [example] = finding.details["examples"]
    assert len(str(example)) < event_sources.EXAMPLE_MAX + 100


def test_a_huge_command_line_is_checked_quickly():
    import time

    start = time.perf_counter()
    findings = tally("ossem_events", [{"process.command_line": "powershell " * 100_000}])
    assert time.perf_counter() - start < 1
    assert findings == {}


def test_the_minimum_number_of_events():
    record = {"time": "2026-06-10 07:13:48", "operation_name": "x/write", "status": "Failed", "caller": "ann"}
    assert "Failed operations" not in tally("azure_activity", [record] * 9)
    assert tally("azure_activity", [record] * 10)["Failed operations"].event_count == 10


def test_the_tally_survives_a_resume():
    """Saved with each staged chunk (pickled), restored into a fresh one."""
    record = {"time": "2026-06-10 07:13:48", "operation_name": "x/roleAssignments/write", "status": "Succeeded"}
    first = reader_for("azure_activity")
    read(first, [{**record, "caller": "ann"}] * 3)
    saved = pickle.loads(pickle.dumps(first.snapshot()))
    resumed = reader_for("azure_activity")
    resumed.restore(saved)
    read(resumed, [{**record, "caller": "bob"}] * 2, start=4)
    finding = findings_of(resumed)["Role assignment created"]
    assert finding.event_count == 5
    assert finding.details["actors"]["top"] == [{"value": "ann", "events": 3}, {"value": "bob", "events": 2}]
