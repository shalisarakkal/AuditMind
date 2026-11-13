"""Bounded group proof digest, evaluated only for the approved finding subset.

Hash source rows independently before aggregating, so full scanner payloads are
never assembled into a single unbounded JSON object. No workflow/proof fields
enter the source digest; status changes have their existing history predicate.
"""
from sqlalchemy import event

SQL = r"""
CREATE OR REPLACE FUNCTION am_consolidation_hash_v1(material text)
RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $hash$
    SELECT CASE WHEN octet_length(material)<=16777216
        THEN encode(sha256(convert_to(material,'UTF8')),'hex') ELSE NULL END
$hash$;
CREATE OR REPLACE FUNCTION am_consolidation_proof_v1(owner uuid, group_id uuid)
RETURNS text LANGUAGE sql STABLE SET timezone='UTC' AS $proof$
WITH root AS (
    SELECT g.* FROM finding_consolidations g
    WHERE g.org_id=owner AND g.id=group_id AND g.state='active'
), members AS (
    SELECT f.id, f.scan_id, f.asset_id, m.role,
        am_consolidation_hash_v1(jsonb_build_array(f.id,f.org_id,f.scan_id,f.asset_id,
            f.domain,f.severity,f.category,f.description,f.raw_data,f.details,
            f.source,f.event_count,f.first_seen,f.last_seen)::text) AS digest
    FROM root g JOIN finding_consolidation_members m ON m.org_id=g.org_id AND m.consolidation_id=g.id
        AND m.generation=g.version
    JOIN findings f ON f.org_id=m.org_id AND f.id=m.finding_id
    JOIN scans s ON s.org_id=f.org_id AND s.id=f.scan_id AND s.archived_at IS NULL AND s.status='completed'
    JOIN assets a ON a.org_id=f.org_id AND a.id=f.asset_id AND a.archived_at IS NULL
    WHERE f.archived_at IS NULL AND f.suppression_id IS NULL AND f.consolidation_id=g.id
        AND f.id IN (g.finding_a_id,g.finding_b_id)
        AND ((m.role='canonical' AND f.id=g.canonical_finding_id AND f.consolidation_alias_id IS NULL)
          OR (m.role='alias' AND f.id<>g.canonical_finding_id AND f.consolidation_alias_id=g.id))
), occurrences AS MATERIALIZED (
    SELECT bounded.* FROM members m CROSS JOIN LATERAL (
        SELECT o.* FROM finding_observations o WHERE o.org_id=owner AND o.finding_id=m.id
        ORDER BY o.recorded_at,o.id LIMIT 1001
    ) bounded ORDER BY bounded.id LIMIT 1001
), occurrence_digests AS (
    SELECT o.id, o.finding_id,
        am_consolidation_hash_v1(to_jsonb(o)::text) AS digest,
        am_consolidation_hash_v1(to_jsonb(b)::text) AS binding_digest,
        am_consolidation_hash_v1((to_jsonb(s)-ARRAY['dismissed_at','progress','heartbeat_at','publication_pid','publication_backend_start','publication_xact_start','publication_xid','retry_count','run_started_at','abort_requested_at','started_by'])::text) AS scan_digest,
        am_consolidation_hash_v1(to_jsonb(a)::text) AS asset_digest
    FROM occurrences o
    LEFT JOIN LATERAL (SELECT b.* FROM observation_identity_bindings b
        WHERE b.org_id=owner AND b.observation_id=o.id ORDER BY b.version DESC LIMIT 1) b ON true
    LEFT JOIN scans s ON s.org_id=owner AND s.id=o.scan_id
    LEFT JOIN assets a ON a.org_id=owner AND a.id=CASE WHEN pg_input_is_valid(o.asset_identity->>'asset_id','uuid') THEN (o.asset_identity->>'asset_id')::uuid END
    WHERE (SELECT coalesce(sum(octet_length(payload::text)),0) FROM occurrences)<=16777216
        AND b.state='bound' AND b.tool_id=(SELECT tool_id FROM root)
        AND b.canonical_asset_id=(SELECT canonical_asset_id FROM root) AND s.archived_at IS NULL AND s.status='completed'
        AND a.id IS NOT NULL AND a.archived_at IS NULL
), sources AS (
    SELECT d.resource_kind,d.resource_id,
        am_consolidation_hash_v1(CASE d.resource_kind
            WHEN 'asset' THEN (SELECT to_jsonb(a) FROM assets a WHERE a.org_id=owner AND a.id=d.resource_id)
            WHEN 'scan' THEN (SELECT to_jsonb(s)-ARRAY['dismissed_at','progress','heartbeat_at','publication_pid','publication_backend_start','publication_xact_start','publication_xid','retry_count','run_started_at','abort_requested_at','started_by'] FROM scans s WHERE s.org_id=owner AND s.id=d.resource_id)
            WHEN 'tool' THEN (SELECT to_jsonb(t) FROM identity_tools t WHERE t.org_id=owner AND t.id=d.resource_id)
            WHEN 'canonical_decision' THEN (SELECT to_jsonb(c) FROM finding_canonical_decisions c WHERE c.org_id=owner AND c.pair_key=(SELECT pair_key FROM finding_canonical_decisions WHERE org_id=owner AND id=d.resource_id) ORDER BY c.version DESC LIMIT 1)
        END::text) AS digest
    FROM root g JOIN finding_consolidation_dependencies d ON d.org_id=g.org_id
        AND d.consolidation_id=g.id AND d.generation=g.version
    WHERE d.resource_kind IN ('asset','scan','tool','canonical_decision')
)
SELECT CASE WHEN (SELECT count(*) FROM members)=2
    AND (SELECT count(*) FROM occurrences) BETWEEN 2 AND 1000
    AND (SELECT count(DISTINCT finding_id) FROM occurrences)=2
    AND (SELECT count(*) FROM occurrence_digests)=(SELECT count(*) FROM occurrences)
    AND NOT EXISTS(SELECT 1 FROM sources WHERE digest IS NULL)
    AND NOT EXISTS(SELECT 1 FROM members WHERE digest IS NULL)
    AND NOT EXISTS(SELECT 1 FROM occurrence_digests WHERE digest IS NULL OR binding_digest IS NULL OR scan_digest IS NULL OR asset_digest IS NULL)
THEN encode(sha256(convert_to(jsonb_build_object(
    'contract','consolidated-proof-v1','root',(SELECT to_jsonb(g) FROM root g),
    'members',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.id) FROM members m),
    'observations',(SELECT jsonb_agg(to_jsonb(o) ORDER BY o.id) FROM occurrence_digests o),
    'sources',(SELECT jsonb_agg(to_jsonb(s) ORDER BY s.resource_kind,s.resource_id) FROM sources s)
)::text,'UTF8')),'hex') ELSE NULL END
$proof$;
"""


def register(metadata):
    @event.listens_for(metadata, 'after_create')
    def install(target, connection, **kwargs):
        if 'finding_consolidation_members' in {table.name for table in kwargs.get('tables', [])}:
            connection.exec_driver_sql(SQL)

    @event.listens_for(metadata, 'after_drop')
    def uninstall(target, connection, **kwargs):
        connection.exec_driver_sql('DROP FUNCTION IF EXISTS am_consolidation_proof_v1(uuid,uuid)')
        connection.exec_driver_sql('DROP FUNCTION IF EXISTS am_consolidation_hash_v1(text)')
