"""Diagnostic source manifest construction. No persistence or visibility authority."""
import hashlib
import json
import uuid

from sqlalchemy import select

from app.models.enums import ScanStatus
from app.models.finding_identity_binding import IdentityTool, ObservationIdentityBinding
from app.services.identity_bindings import _assets, _scans, _source_asset

MAX_OBSERVATIONS = 1000


def manifest(db, org_id, decision, findings, observations, identity):
    """Called only after bounded independent identity admission has succeeded.

    Pin both physical retention owners and all observation sources. Observation
    sources can differ from a finding's original scan/asset ownership.
    Return None if a physical owner is missing, cross-tenant or inactive.
    All lookups are batched and explicitly scoped; no raw payload is read.
    """
    if (not isinstance(identity, dict) or len(findings) != 2 or not observations or len(observations) > MAX_OBSERVATIONS
            or decision.org_id != org_id or decision.canonical_finding_id not in findings
            or set(findings) != {decision.finding_a_id, decision.finding_b_id}
            or any(row.org_id != org_id for row in findings.values())
            or any(row.org_id != org_id or row.finding_id not in findings for row in observations)):
        return None
    try:
        canonical_asset_id = uuid.UUID(str(identity["canonical_asset_id"]))
        tool_id = uuid.UUID(str(identity["tool_id"]))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    asset_ids = {row.asset_id for row in findings.values()} | {
        _source_asset(row) for row in observations} | {canonical_asset_id}
    scan_ids = {row.scan_id for row in findings.values()} | {row.scan_id for row in observations}
    if None in asset_ids or None in scan_ids:
        return None
    assets, scans = _assets(db, org_id, asset_ids), _scans(db, org_id, scan_ids)
    if (set(assets) != asset_ids or set(scans) != scan_ids
            or any(row.archived_at is not None for row in assets.values())
            or any(row.archived_at is not None or row.status != ScanStatus.completed for row in scans.values())):
        return None
    bindings = {row.observation_id: row for row in db.execute(select(ObservationIdentityBinding.id,
        ObservationIdentityBinding.observation_id, ObservationIdentityBinding.version).where(
            ObservationIdentityBinding.org_id == org_id,
            ObservationIdentityBinding.observation_id.in_([row.id for row in observations]))
        .order_by(ObservationIdentityBinding.observation_id, ObservationIdentityBinding.version.desc())
        .distinct(ObservationIdentityBinding.observation_id))}
    if len(bindings) != len(observations):
        return None
    resources = {}

    def add(kind, identifier, version=None):
        resources[(kind, str(identifier))] = dict(resource_kind=kind,
            resource_id=str(identifier), resource_version=version)

    for row in findings.values():
        add("finding", row.id)
    for identifier in asset_ids:
        add("asset", identifier)
    for identifier in scan_ids:
        add("scan", identifier)
    for row in observations:
        add("observation", row.id)
        binding = bindings[row.id]
        add("identity_binding", binding.id, binding.version)
    tool_version = db.scalar(select(IdentityTool.version).where(IdentityTool.org_id == org_id,
        IdentityTool.id == tool_id, IdentityTool.active.is_(True)))
    if tool_version is None:
        return None
    add("tool", tool_id, tool_version)
    add("canonical_decision", decision.id, decision.version)
    members = sorted([dict(finding_id=str(row.id),
        role="canonical" if row.id == decision.canonical_finding_id else "alias")
        for row in findings.values()], key=lambda row: row["role"])
    refs = [resources[key] for key in sorted(resources)]
    material = dict(contract="consolidation-dependencies-v1", org_id=str(org_id),
        members=members, resources=refs)
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    counts = {kind: sum(row["resource_kind"] == kind for row in refs) for kind in sorted({key[0] for key in resources})}
    return dict(**material, fingerprint=digest, resource_count=len(refs), resource_counts=counts)
