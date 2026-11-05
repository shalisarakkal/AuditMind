"""Measure added list-index write cost in disposable local-demo clones.

Only randomly named clone tables are changed. No accounts, source rows,
organization settings or source indexes are modified. This isolates index
cost; it does not measure ingestion parsing or production concurrency.
"""
import json
from pathlib import Path
import statistics
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from app.core.config import settings
from scripts.demo import demo_url


NEW_INDEXES = {
    "ix_assets_active_created_page", "ix_findings_active_created_page",
    "ix_assets_active_created_desc_page",
    "ix_assets_active_ip_desc_page",
    "ix_assets_active_ip_asc_page",
    "ix_findings_active_severity_page", "ix_assets_active_hostname_asc_page",
    "ix_assets_active_hostname_desc_page", "ix_findings_active_text_asc_page",
    "ix_findings_active_text_desc_page", "ix_findings_active_long_text",
    "ix_findings_active_domain_page",
    "ix_findings_active_workflow_status_group_page", "ix_findings_active_assignee_id_group_page",
    "ix_findings_active_due_presence", "ix_findings_active_review_presence",
    *[f"ix_findings_active_{field}_{direction}_page" for field in ("category","source") for direction in ("asc","desc")],
    *[f"ix_assets_org_label_{direction}_page" for direction in ("asc","desc")],
}


def writes(connection, table):
    measurements = {"insert_ms": [], "update_ms": []}
    organization = uuid.uuid4()
    for _ in range(3):
        start = time.perf_counter()
        if table == "assets":
            statement = """INSERT INTO assets(id,org_id,type,hostname,type_known,details,created_at)
                SELECT gen_random_uuid(),:org,'server','write-bench-'||i,true,'{}'::jsonb,now()
                FROM generate_series(1,5000) i"""
            update = "UPDATE assets SET hostname=hostname||'-updated' WHERE org_id=:org"
        else:
            statement = """INSERT INTO findings(id,org_id,domain,severity,description,created_at)
                SELECT gen_random_uuid(),:org,'identity_access','high','Write benchmark finding '||i,now()
                FROM generate_series(1,5000) i"""
            update = "UPDATE findings SET description=description||' updated' WHERE org_id=:org"
        connection.execute(text(statement), {"org": organization})
        connection.commit()
        measurements["insert_ms"].append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        connection.execute(text(update), {"org": organization})
        connection.commit()
        measurements["update_ms"].append((time.perf_counter()-start)*1000)
        connection.execute(text(f"DELETE FROM {table} WHERE org_id=:org"), {"org": organization})
        connection.commit()
    return {name: round(statistics.median(values), 2) for name, values in measurements.items()}


def main():
    engine = create_engine(demo_url(settings.DATABASE_URL))
    schema = "list_write_bench_" + uuid.uuid4().hex
    created = False
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == "auditmind_demo"
            source = connection.execute(text("""SELECT tablename,indexname,indexdef FROM pg_indexes
                WHERE schemaname='auditmind_demo' AND tablename IN ('assets','findings')""")).all()
            assert NEW_INDEXES <= {row.indexname for row in source}, "Apply 0039 before benchmarking"
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.commit()
            created = True
            connection.execute(text(f'SET search_path TO "{schema}", auditmind_demo, public'))
            for table in ("assets", "findings"):
                connection.execute(text(f"CREATE TABLE {table} (LIKE auditmind_demo.{table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"))
                connection.execute(text(f"INSERT INTO {table} SELECT * FROM auditmind_demo.{table} WHERE archived_at IS NULL LIMIT 100000"))
            for row in source:
                if row.indexname not in NEW_INDEXES:
                    connection.execute(text(row.indexdef.replace(f" ON auditmind_demo.{row.tablename} ", f' ON "{schema}".{row.tablename} ')))
            connection.commit()
            for phase in ("baseline", "with_navigation_indexes"):
                if phase != "baseline":
                    for row in source:
                        if row.indexname in NEW_INDEXES:
                            connection.execute(text(row.indexdef.replace(f" ON auditmind_demo.{row.tablename} ", f' ON "{schema}".{row.tablename} ')))
                    connection.commit()
                for table in ("assets", "findings"):
                    print(json.dumps({"phase":phase,"table":table,"batch_rows":5000,**writes(connection,table)}), flush=True)
    finally:
        if created:
            with engine.begin() as cleanup:
                assert schema.startswith("list_write_bench_") and len(schema) == len("list_write_bench_")+32
                cleanup.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


if __name__ == "__main__":
    main()
