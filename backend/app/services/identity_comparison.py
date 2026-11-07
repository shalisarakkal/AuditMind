"""Bounded cross-import review. Never discovers, merges or suppresses findings.

An earlier review is a proposed namespace/asset mapping, not an upload claim.
The administrator must review and confirm this target independently. The token
pins both decisions and their live context, so a preview cannot authorize a
different target context later. No inventory-wide search or importer work.
"""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.models.finding import Finding
from app.models.enums import ScanStatus
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import IdentityTool
from app.schemas.identity_binding import IdentityBind
from app.services.finding_identity import IdentityBinding, assess_identity
from app.services.identity_bindings import (
    _assets, _context, _scans, _source_asset, latest_bindings,
    read_observations, write_binding,
)


def compare_observation(db, org_id, target, source_id, *, include_context=False):
    source = db.scalar(select(FindingObservation).where(
        FindingObservation.org_id == org_id, FindingObservation.id == source_id))
    if source is None:
        raise HTTPException(404, "Reference observation not found")
    if (source.import_id == target.import_id or source.recorded_at >= target.recorded_at):
        raise HTTPException(409, "Choose an observation from an earlier import")
    views = read_observations(db, org_id, [source, target])
    reference = views[0].identity_binding
    if not reference or not reference["current"]:
        raise HTTPException(409, "Reference identity review is not current; review it first")
    decisions = latest_bindings(db, org_id, [source.id, target.id])
    decision = decisions.get(source.id)
    if decision is None or decision.state != "bound" or decision.version != reference["version"]:
        raise HTTPException(409, "Reference identity changed; compare again")
    tool = db.get(IdentityTool, decision.tool_id)
    if tool is None or not tool.active or tool.version != decision.context.get("tool_version"):
        raise HTTPException(409, "Reference tool changed; compare again")
    assets = _assets(db, org_id, {decision.canonical_asset_id, _source_asset(target)} - {None})
    canonical, captured = assets.get(decision.canonical_asset_id), assets.get(_source_asset(target))
    scans = _scans(db, org_id, [target.scan_id] if target.scan_id else [])
    scan = scans.get(target.scan_id)
    finding = db.execute(select(Finding.id, Finding.archived_at).where(
        Finding.org_id == org_id, Finding.id == target.finding_id)).one_or_none()
    if (canonical is None or captured is None or canonical.archived_at is not None
            or captured.archived_at is not None or scan is None or scan.archived_at is not None
            or scan.status != ScanStatus.completed or finding is None or finding.archived_at is not None):
        raise HTTPException(409, "Active findings/assets and retained completed scans are required")
    proposed = assess_identity(org_id=org_id, scan_type=target.scan_type, source=target.source,
        profile=target.profile, raw=target.source_identity,
        binding=IdentityBinding(org_id, tool.id, canonical.id))
    if proposed.candidate_key is None:
        raise HTTPException(409, "Target source identity is unsupported or incomplete")
    if proposed.candidate_key != views[0].identity_assessment["candidate_key"]:
        raise HTTPException(409, "Native plugin, port or protocol differs; do not carry forward this identity")
    target_decision = decisions.get(target.id)
    if target_decision is not None:
        # A revoked/stale or differently reviewed target requires its own explicit
        # editor; carry-forward never overrides a conflicting review decision.
        target_review = views[1].identity_binding
        if (not target_review or target_review["version"] != target_decision.version
                or not target_review["current"]
                or views[1].identity_assessment["candidate_key"] != proposed.candidate_key):
            raise HTTPException(409, "Target already has a different or withdrawn review; review it independently")
    context = _context(target, tool, canonical, captured, scan)
    token_material = dict(org_id=str(org_id), source_id=str(source.id), target_id=str(target.id),
        source_version=decision.version, source_context=decision.context,
        target_version=target_decision.version if target_decision else 0, target_context=context,
        source_finding=str(source.finding_id), target_finding=str(target.finding_id))
    token = hashlib.sha256(json.dumps(token_material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = dict(review_token=token, source_observation_id=str(source.id), target_observation_id=str(target.id),
        source_finding_id=str(source.finding_id), target_finding_id=str(target.finding_id),
        source_version=decision.version, target_version=target_decision.version if target_decision else 0,
        tool_id=str(tool.id), tool_name=tool.name, tool_version=tool.version,
        canonical_asset_id=str(canonical.id), target_asset_id=str(captured.id),
        source_material=proposed.source_material, candidate_key=proposed.candidate_key,
        result="same_finding" if source.finding_id == target.finding_id else "canonical_conflict",
        already_reviewed=target_decision is not None,
        reconciliation_eligible=False)
    if include_context:
        result["binding_context"] = context
    return result


def carry_forward(db, org_id, target, actor_id, payload):
    preview = compare_observation(db, org_id, target, payload.source_observation_id, include_context=True)
    if preview["review_token"] != payload.review_token or preview["target_version"] != payload.expected_version:
        raise HTTPException(409, "Identity context changed; compare again before saving")
    if preview["already_reviewed"]:
        raise HTTPException(409, "Target identity is already reviewed; no new decision is needed")
    # Never collapse canonical duplicates under cover of a namespace review.
    # A separate explicit conflict resolution contract must preserve both histories.
    if preview["result"] == "canonical_conflict":
        raise HTTPException(409, "Separate canonical findings require conflict resolution; no mapping was carried forward")
    bind = IdentityBind(expected_version=payload.expected_version, rationale=payload.rationale,
        tool_id=preview["tool_id"], expected_tool_version=preview["tool_version"],
        canonical_asset_id=preview["canonical_asset_id"], confirm_mapping=payload.confirm_mapping)
    return write_binding(db, org_id, target, actor_id, bind, expected_context=preview["binding_context"], reviewed_from=dict(
        observation_id=preview["source_observation_id"], version=preview["source_version"]))
