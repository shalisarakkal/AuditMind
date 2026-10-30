"""Versioned, immutable text-only expression used by the Assets search index."""
import re
from sqlalchemy import event, func, select, text

FUNCTION = "am_asset_search_v1"
INDEX = "ix_assets_active_search_trgm"
SIGNATURE = "text,text,text,text,text,text,text,character varying[]"


def install_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    # array_to_string is stable for arbitrary element types (timestamps, etc.).
    # Here the signature accepts only varchar[], whose text output does not
    # depend on timezone/DateStyle. Never broaden these inputs or change v1:
    # changing an indexed immutable function requires rebuilding its index.
    connection.exec_driver_sql(f"""CREATE OR REPLACE FUNCTION {schema}.{FUNCTION}(
        hostname text, ip text, cloud_id text, asset_type text, subtype text,
        environment text, criticality text, tags character varying[])
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE
        SET search_path = pg_catalog AS $body$
        SELECT coalesce(hostname,'') || chr(10) || coalesce(ip,'') || chr(10) ||
            coalesce(cloud_id,'') || chr(10) || coalesce(asset_type,'') || chr(10) ||
            replace(coalesce(asset_type,''),'_',' ') || chr(10) || coalesce(subtype,'') || chr(10) ||
            coalesce(environment,'') || chr(10) || coalesce(criticality,'') || chr(10) ||
            coalesce(array_to_string(tags,' '),'')
        $body$""")


def uninstall_v1(connection):
    schema = connection.dialect.identifier_preparer.quote_schema(connection.exec_driver_sql("SELECT current_schema()").scalar_one())
    connection.exec_driver_sql(f"DROP FUNCTION IF EXISTS {schema}.{FUNCTION}({SIGNATURE})")


def register(table):
    # Production is managed by Alembic; metadata fixtures need the same function
    # before creating the expression index and cleanup after dropping the table.
    event.listen(table, "before_create", lambda target, connection, **kw: install_v1(connection))
    event.listen(table, "after_drop", lambda target, connection, **kw: uninstall_v1(connection))


def expression(asset):
    return getattr(func, FUNCTION)(asset.hostname, asset.ip, asset.cloud_id, asset.type,
        asset.subtype, asset.environment, asset.criticality, asset.tags)


def useful_trigrams(value):
    """Keep the existing scan path for short/non-word searches."""
    return bool(value and re.search(r"[^\W_]{3}", value, re.UNICODE))


def selective_candidates(db, asset, org_id, predicates):
    """Use the index only for estimated selective searches; never change matches.

    EXPLAIN plans but does not execute a scan. Common terms can otherwise force
    expensive evaluation of the combined expression over most of an inventory.
    Estimates influence strategy only; original predicates still decide results.
    """
    if not predicates:
        return []
    connection = db.connection()
    base = select(asset.id).where(asset.org_id == org_id, asset.archived_at.is_(None))

    def estimate(statement):
        compiled = statement.compile(dialect=connection.dialect, compile_kwargs={"render_postcompile": True})
        plan = connection.exec_driver_sql("EXPLAIN (FORMAT JSON) " + str(compiled), compiled.params).scalar_one()
        return plan[0]["Plan"]["Plan Rows"]

    size = max(1, estimate(base))
    selected = []
    for candidate, original, pattern in predicates:
        # Ordinary column/type statistics describe common metadata much better
        # than the combined function. array_to_string itself has no tag-element
        # frequency estimate, so also inspect matching most-common tag elements.
        fraction = estimate(base.where(original)) / size
        if fraction > 0.05:
            continue
        # Element frequencies exclude null arrays; scale back to all rows.
        tag_fraction = connection.execute(text("""SELECT LEAST(1.0, COALESCE(sum(
                s.most_common_elem_freqs[e.position::integer] * (1.0 - s.null_frac)), 0))
            FROM pg_stats s CROSS JOIN LATERAL unnest(
                (s.most_common_elems::text)::text[]) WITH ORDINALITY e(value, position)
            WHERE s.schemaname=current_schema() AND s.tablename=:table
                AND s.attname='tags' AND NOT s.inherited
                AND e.value ILIKE :pattern ESCAPE '\\'
            """), {"table": asset.__tablename__, "pattern": pattern}).scalar_one()
        if max(fraction, tag_fraction) <= 0.05:
            selected.append(candidate)
    return selected
