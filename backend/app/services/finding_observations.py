"""Conservative observation snapshots; legacy duplicate keys are NOT stable identities."""
import uuid
from datetime import datetime, timezone

from psycopg.types.json import Jsonb


def observation_values(row, asset, scan, finding_id, occurrence):
    raw = row.raw_data or {}
    # Only named native Nessus fields have a reviewed source mapping. Generic
    # category/CVE/description and profile-generated rules are not stable IDs.
    identity = {key: raw[key] for key in ("source_instance_id", "source_finding_id", "instance_discriminator", "port", "protocol")
        if isinstance(raw.get(key), (str, int)) and not isinstance(raw.get(key), bool)}
    if scan.scan_type == "nessus" and row.source == "nessus":
        identity.update({key: raw.get(key) for key in ("plugin_id", "port", "protocol")})
    reasons = ["source_instance_not_configured", "stable_asset_mapping_not_verified"]
    if not (identity.get("plugin_id") or identity.get("source_finding_id")):
        reasons.append("stable_source_identifier_unavailable")
    if identity.get("plugin_id") and (identity.get("port") in (None, "") or not identity.get("protocol")):
        reasons.append("source_instance_discriminator_missing")
    observed_at = row.last_seen
    if observed_at is None and raw.get("observed_at") is not None:
        try:
            supplied = raw["observed_at"]
            if not isinstance(supplied, str) or len(supplied) > 80:
                raise ValueError("Expected an ISO timestamp")
            observed_at = datetime.fromisoformat(supplied.replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                raise ValueError("Source observation time must include an offset")
            observed_at = observed_at.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            observed_at = None
            reasons.append("source_observed_time_invalid")
    # PB-1.1 does not authorize reconciliation. No current import supplies a
    # verified tool-instance namespace and stable canonical asset mapping.
    reasons.append("legacy_matching_only")
    return dict(id=uuid.uuid4(), org_id=scan.org_id, finding_id=finding_id,
        import_id=scan.id, scan_id=scan.id, occurrence=occurrence, source_row=row.row,
        source=row.source, scan_type=scan.scan_type, profile=scan.profile, filename=scan.filename,
        observed_at=observed_at, recorded_at=datetime.now(timezone.utc),
        asset_identity=dict(asset_id=str(asset.id) if asset else None,
            hostname=row.hostname, ip=row.ip, cloud_id=row.cloud_id),
        source_identity=identity, reconciliation_eligible=False,
        ineligibility_reasons=Jsonb(reasons),
        payload=dict(domain=row.domain.value, severity=row.severity.value, category=row.category,
            description=row.description, event_count=row.event_count,
            first_seen=row.first_seen.isoformat() if row.first_seen else None,
            last_seen=row.last_seen.isoformat() if row.last_seen else None,
            details=row.details, raw_data=raw))
