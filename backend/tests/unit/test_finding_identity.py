"""Identity boundaries and fail-closed source mappings, not legacy deduplication."""
from dataclasses import replace
import uuid

import pytest

from app.services.finding_identity import IdentityBinding, assess_identity

ORG = uuid.UUID("11111111-1111-4111-8111-111111111111")
TOOL = uuid.UUID("22222222-2222-4222-8222-222222222222")
ASSET = uuid.UUID("33333333-3333-4333-8333-333333333333")
BINDING = IdentityBinding(ORG, TOOL, ASSET)
RAW = dict(plugin_id="187095", port="443", protocol="tcp")


def assess(raw=None, **changes):
    params = dict(org_id=ORG, scan_type="nessus", source="nessus", profile=None,
                  raw=RAW if raw is None else raw, binding=BINDING)
    params.update(changes)
    return assess_identity(**params)


def test_same_native_instance_is_stable_across_irrelevant_payload_changes():
    baseline = assess()
    changed = assess({**RAW, "description": "New text", "severity": "critical",
        "cve": "CVE-2026-1", "filename": "renamed.nessus", "row": 99})
    assert baseline.candidate_key == changed.candidate_key
    assert baseline.candidate_key.startswith("finding-identity-v1:")
    assert not baseline.blocking_reasons
    assert assess({**RAW, "plugin_id": 187095, "port": 443, "protocol": " TCP "}).candidate_key == baseline.candidate_key


@pytest.mark.parametrize("raw", [
    {**RAW, "plugin_id": "187096"}, {**RAW, "port": "8443"},
    {**RAW, "protocol": "udp"},
])
def test_service_instances_are_distinct(raw):
    assert assess(raw).candidate_key != assess().candidate_key


def test_namespaces_prevent_tenant_tool_and_asset_collisions():
    baseline = assess().candidate_key
    other = uuid.UUID("44444444-4444-4444-8444-444444444444")
    assert assess(binding=replace(BINDING, tool_instance_id=other)).candidate_key != baseline
    assert assess(binding=replace(BINDING, canonical_asset_id=other)).candidate_key != baseline
    assert assess(org_id=other, binding=replace(BINDING, org_id=other)).candidate_key != baseline
    refused = assess(org_id=other)
    assert refused.candidate_key is None
    assert "identity_binding_invalid" in refused.blocking_reasons


@pytest.mark.parametrize("port", [0, "0", "00000", 65535, "65535"])
def test_host_level_zero_and_valid_boundary_ports_are_supported(port):
    assert assess({**RAW, "port": port}).candidate_key is not None
    assert assess({**RAW, "port": "00000"}).candidate_key == assess({**RAW, "port": 0}).candidate_key


@pytest.mark.parametrize("field,value", [
    ("plugin_id", None), ("plugin_id", ""), ("plugin_id", 0),
    ("plugin_id", True), ("plugin_id", "9" * 1000),
    pytest.param("plugin_id", 10**5000, id="oversized-integer"),
    ("plugin_id", "1.0"), ("plugin_id", "-1"),
    ("port", None), ("port", False), ("port", -1), ("port", 65536),
    ("port", 443.0), ("port", "4|43"), ("protocol", "sctp"),
    ("protocol", None), ("protocol", ["tcp"]),
])
def test_invalid_or_missing_native_components_never_generate_keys(field, value):
    assert assess({**RAW, field: value}).candidate_key is None


@pytest.mark.parametrize("changes", [dict(scan_type="findings_json"),
    dict(source="qualys"), dict(profile="endpoint_agent")])
def test_unreviewed_mappings_do_not_borrow_nessus_identity(changes):
    result = assess(**changes)
    assert result.candidate_key is None
    assert "source_identity_mapping_unavailable" in result.blocking_reasons


def test_uploaded_binding_claims_are_not_trusted():
    result = assess({**RAW, "source_instance_id": str(TOOL),
        "asset_id": str(ASSET), "cloud_id": "resource", "verified": True}, binding=None)
    assert result.candidate_key is None
    assert set(result.blocking_reasons) == {"source_instance_not_configured", "stable_asset_mapping_not_verified"}
    assert "source_instance_id" not in result.source_material


@pytest.mark.parametrize("binding", [dict(org_id=ORG),
    replace(BINDING, canonical_asset_id=uuid.UUID(int=0)),
    replace(BINDING, tool_instance_id="tool"),
])
def test_invalid_internal_bindings_fail_closed(binding):
    assert assess(binding=binding).candidate_key is None


def test_assessment_has_no_authority_flag_and_snapshot_is_independent():
    result = assess()
    snapshot = result.snapshot()
    snapshot["source_material"]["port"] = 1
    assert result.source_material["port"] == 443
    assert "reconciliation_eligible" not in snapshot
