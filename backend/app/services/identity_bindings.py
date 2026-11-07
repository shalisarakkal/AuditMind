"""Small reviewed identity decisions; never locks/imports or changes findings."""
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.scan import Scan
from app.models.enums import ScanStatus
from app.models.finding_identity_binding import IdentityTool, ObservationIdentityBinding
from app.models.user import User
from app.schemas.finding_observation import FindingObservationRead
from app.services.events import actor_label, record_event
from app.services.finding_identity import IdentityBinding, assess_identity


def latest_bindings(db, org_id, ids):
    if not ids:
        return {}
    rows = db.scalars(select(ObservationIdentityBinding).where(
        ObservationIdentityBinding.org_id == org_id,
        ObservationIdentityBinding.observation_id.in_(ids)).order_by(
        ObservationIdentityBinding.observation_id, ObservationIdentityBinding.version.desc()
        ).distinct(ObservationIdentityBinding.observation_id)).all()
    return {row.observation_id: row for row in rows}


def _source_asset(observation):
    try:
        return uuid.UUID(str(observation.asset_identity.get("asset_id")))
    except (ValueError, TypeError, AttributeError):
        return None


def _assets(db, org_id, ids):
    if not ids:
        return {}
    rows = db.execute(select(Asset.id, Asset.hostname, Asset.ip, Asset.cloud_id,
        Asset.type, Asset.archived_at).where(Asset.org_id == org_id, Asset.id.in_(ids))).all()
    return {row.id: row for row in rows}


def _asset_context(asset):
    return dict(id=str(asset.id), hostname=asset.hostname, ip=asset.ip,
                cloud_id=asset.cloud_id, type=asset.type)


def _context(observation, tool, canonical, source, scan):
    contract = assess_identity(org_id=observation.org_id, scan_type=observation.scan_type,
        source=observation.source, profile=observation.profile, raw=observation.source_identity)
    return dict(identity_version=contract.version, source_mapping=contract.mapping,
                source_material=contract.source_material, tool_version=tool.version, canonical=_asset_context(canonical),
                source_asset=_asset_context(source), scan_id=str(scan.id),
                scan_configuration=scan.ingestion_config_fingerprint,
                source_identity=observation.source_identity)


def _scans(db, org_id, ids):
    if not ids:
        return {}
    return {row.id: row for row in db.execute(select(Scan.id, Scan.status,
        Scan.archived_at, Scan.ingestion_config_fingerprint).where(
        Scan.org_id == org_id, Scan.id.in_(ids))).all()}


def read_observations(db, org_id, observations):
    """At most five extra bounded queries per page, no inventory scans/N+1."""
    decisions = latest_bindings(db, org_id, [row.id for row in observations])
    if not decisions:
        return [FindingObservationRead.model_validate(row) for row in observations]
    tools = {row.id: row for row in db.scalars(select(IdentityTool).where(
        IdentityTool.org_id == org_id, IdentityTool.id.in_([d.tool_id for d in decisions.values() if d.tool_id])))}
    assets = _assets(db, org_id, {value for value in
        [*[_source_asset(o) for o in observations], *[d.canonical_asset_id for d in decisions.values()]] if value})
    scans = _scans(db, org_id, {o.scan_id for o in observations if o.scan_id})
    findings = {row.id: row.archived_at for row in db.execute(select(Finding.id, Finding.archived_at).where(
        Finding.org_id == org_id, Finding.id.in_({o.finding_id for o in observations})))}
    result = []
    for observation in observations:
        item = FindingObservationRead.model_validate(observation)
        decision = decisions.get(observation.id)
        if decision is not None:
            tool, canonical = tools.get(decision.tool_id), assets.get(decision.canonical_asset_id)
            source, scan = assets.get(_source_asset(observation)), scans.get(observation.scan_id)
            valid = (observation.finding_id in findings and findings[observation.finding_id] is None
                and decision.state == "bound" and tool is not None and tool.active
                and canonical is not None and canonical.archived_at is None
                and source is not None and source.archived_at is None
                and scan is not None and scan.archived_at is None and scan.status == ScanStatus.completed
                and {k: v for k, v in decision.context.items() if k != "reviewed_from"}
                    == _context(observation, tool, canonical, source, scan))
            binding = IdentityBinding(org_id, tool.id, canonical.id) if valid else None
            assessment = assess_identity(org_id=org_id, scan_type=observation.scan_type,
                source=observation.source, profile=observation.profile,
                raw=observation.source_identity, binding=binding).snapshot()
            if not valid:
                assessment["blocking_reasons"].append("reviewed_identity_binding_not_current")
            item.identity_assessment = assessment
            item.identity_binding = dict(version=decision.version, state=decision.state,
                current=bool(valid), reviewed_identity_version=decision.context.get("identity_version"),
                reviewed_from=decision.context.get("reviewed_from"),
                reviewed_source_mapping=decision.context.get("source_mapping"), tool_id=str(decision.tool_id) if decision.tool_id else None,
                tool_name=tool.name if tool else "Unavailable", canonical_asset_id=str(decision.canonical_asset_id) if decision.canonical_asset_id else None,
                rationale=decision.rationale, actor_label=decision.actor_label,
                created_at=decision.created_at.isoformat())
        # Identity material is never comparability, absence or suppression authority.
        item.reconciliation_eligible = False
        result.append(item)
    return result


def write_binding(db, org_id, observation, actor_id, payload, *, revoke=False, reviewed_from=None):
    latest = latest_bindings(db, org_id, [observation.id]).get(observation.id)
    version = latest.version if latest else 0
    if version != payload.expected_version:
        raise HTTPException(409, "Identity binding changed; reload before retrying")
    if revoke:
        if latest is None or latest.state != "bound":
            raise HTTPException(409, "No binding to revoke")
        tool_id, asset_id, context = latest.tool_id, latest.canonical_asset_id, latest.context
    else:
        if payload.confirm_mapping is not True:
            raise HTTPException(422, "Confirm the tool instance and canonical asset mapping")
        tool = db.scalar(select(IdentityTool).where(IdentityTool.org_id == org_id,
            IdentityTool.id == payload.tool_id).execution_options(populate_existing=True))
        if tool is None:
            raise HTTPException(404, "Tool instance not found")
        if not tool.active or tool.version != payload.expected_tool_version:
            raise HTTPException(409, "Tool instance changed or retired; reload before retrying")
        assets = _assets(db, org_id, {payload.canonical_asset_id, _source_asset(observation)} - {None})
        canonical, source = assets.get(payload.canonical_asset_id), assets.get(_source_asset(observation))
        if canonical is None or source is None:
            raise HTTPException(404, "Asset not found")
        scans = _scans(db, org_id, [observation.scan_id] if observation.scan_id else [])
        scan = scans.get(observation.scan_id)
        if (canonical.archived_at is not None or source.archived_at is not None or
                scan is None or scan.archived_at is not None or scan.status != ScanStatus.completed):
            raise HTTPException(409, "Active assets and a retained completed scan are required")
        assessment = assess_identity(org_id=org_id, scan_type=observation.scan_type,
            source=observation.source, profile=observation.profile, raw=observation.source_identity,
            binding=IdentityBinding(org_id, tool.id, canonical.id))
        if assessment.candidate_key is None:
            raise HTTPException(409, "Source identity is unsupported or incomplete")
        tool_id, asset_id = tool.id, canonical.id
        context = _context(observation, tool, canonical, source, scan)
        if reviewed_from is not None:
            context["reviewed_from"] = reviewed_from
    actor = db.get(User, actor_id)
    decision = ObservationIdentityBinding(org_id=org_id, observation_id=observation.id,
        version=version + 1, state="revoked" if revoke else "bound", tool_id=tool_id,
        canonical_asset_id=asset_id, context=context, rationale=payload.rationale,
        actor_id=actor_id, actor_label=actor_label(actor))
    db.add(decision)
    db.flush()
    record_event(db, "identity_binding_revoked" if revoke else "identity_binding_reviewed",
        org_id=org_id, actor=actor, item=str(observation.id), details=dict(
            observation_id=str(observation.id), finding_id=str(observation.finding_id),
            version=decision.version, rationale=payload.rationale,
            **({"reviewed_from": reviewed_from} if reviewed_from is not None else {})))
    db.commit()
    return read_observations(db, org_id, [observation])[0]
