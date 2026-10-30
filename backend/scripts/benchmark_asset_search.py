"""Compare combined search on a disposable 100k-row local-demo clone.

Only the randomly named prototype schema is written/dropped. Source rows,
accounts, settings and running application indexes are never changed here.
"""
import inspect
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.params import Param
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.asset_search import INDEX, install_v1
from app.models.asset import Asset
from app.models.organization import Organization
from app.api.paging import PageParams
from app.api.routes.assets import list_assets
from scripts.demo import demo_url


def call_list(db, function, org, filters):
    args = {name: param.default.default if isinstance(param.default, Param) else param.default
            for name, param in inspect.signature(function).parameters.items()}
    args.update(org_id=org, db=db, _=None, page=PageParams(100, 0), **filters)
    start = time.perf_counter()
    result = function(**args)
    return round((time.perf_counter()-start)*1000, 2), (result.total, tuple(row.id for row in result.items))


def writes(connection):
    org = uuid.uuid4()
    timings = {"insert_ms": [], "update_ms": []}
    for _ in range(3):
        start = time.perf_counter()
        connection.execute(text("""INSERT INTO assets(id,org_id,type,hostname,tags,environment,type_known,details,created_at)
            SELECT gen_random_uuid(),:org,'server','prototype-insert-'||i,
            ARRAY['generated','production']::varchar[],'prod',true,'{}'::jsonb,now()
            FROM generate_series(1,5000) AS i"""), {"org": org})
        connection.commit()
        timings["insert_ms"].append((time.perf_counter()-start)*1000)
        start = time.perf_counter()
        connection.execute(text("UPDATE assets SET tags=ARRAY['updated','production']::varchar[],environment='updated' WHERE org_id=:org"), {"org": org})
        connection.commit()
        timings["update_ms"].append((time.perf_counter()-start)*1000)
        connection.execute(text("DELETE FROM assets WHERE org_id=:org"), {"org": org})
        connection.commit()
    return {name: round(statistics.median(values), 2) for name, values in timings.items()}


def main():
    engine = create_engine(demo_url(settings.DATABASE_URL))
    schema = "asset_search_bench_" + uuid.uuid4().hex[:12]
    source = subprocess.check_output(["git", "show", "1b2286f:backend/app/api/routes/assets.py"], text=True)
    legacy = types.ModuleType("asset_search_legacy")
    sys.modules[legacy.__name__] = legacy
    exec(compile(source, "1b2286f:assets.py", "exec"), legacy.__dict__)
    try:
        with engine.connect() as c:
            assert c.scalar(text("SELECT current_schema()")) == "auditmind_demo"
            org = c.scalar(select(Organization.id).where(Organization.name == "SA01"))
            if org is None:
                raise RuntimeError("Local SA01 demo organization missing")
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
            c.execute(text(f'SET search_path TO "{schema}", auditmind_demo, public'))
            c.execute(text("SET statement_timeout = '120s'"))
            c.execute(text("""CREATE TABLE assets AS SELECT a.* FROM auditmind_demo.assets AS a
                TABLESAMPLE SYSTEM(8) WHERE a.org_id=:org AND a.archived_at IS NULL LIMIT 100000"""), {"org": org})
            c.execute(text("CREATE UNIQUE INDEX assets_bench_pk ON assets(id)"))
            install_v1(c)
            for index in Asset.__table__.indexes:
                if index.name != INDEX:
                    index.create(c)
            c.execute(text("ANALYZE assets"))
            c.commit()
            rows = c.scalar(text("SELECT count(*) FROM assets"))
            tag = c.scalar(text("SELECT tag FROM assets CROSS JOIN LATERAL unnest(tags) AS tag WHERE char_length(tag)>=3 LIMIT 1"))
            environment = c.scalar(text("SELECT environment FROM assets WHERE char_length(environment)>=3 LIMIT 1"))
            c.commit()
            cases = [("no_match", {"q": "no-such-host-93c7"}), ("hostname", {"q": "NET-499"}),
                ("tag", {"q": "production"}), ("tag_filter", {"tags": "production"}),
                ("environment", {"q": "prod"}), ("type_label", {"q": "Network device"}),
                ("common_type", {"q": "server"}),
                ("short", {"q": "a"}), ("literal_percent", {"q": "%"}),
                ("combined", {"q": "prod", "environment": ["prod"]})]
            if tag:
                cases += [("existing_tag", {"q": tag}), ("existing_tag_filter", {"tags": tag})]
            if environment:
                cases += [("existing_environment", {"q": environment, "environment": [environment]})]
            baseline = {}
            with Session(bind=c) as db:
                for name, filters in cases:
                    baseline[name] = call_list(db, legacy.list_assets, org, filters)
                db.rollback()
            before_writes = writes(c)
            start = time.perf_counter()
            next(i for i in Asset.__table__.indexes if i.name == INDEX).create(c)
            c.commit()
            build_ms = round((time.perf_counter()-start)*1000, 2)
            c.execute(text("ANALYZE assets")); c.commit()
            results = []
            with Session(bind=c) as db:
                for name, filters in cases:
                    elapsed, result = call_list(db, list_assets, org, filters)
                    if result != baseline[name][1]:
                        raise AssertionError(f"Results changed: {name}")
                    results.append({"case": name, "before_ms": baseline[name][0], "after_ms": elapsed, "total": result[0]})
                db.rollback()
            after_writes = writes(c)
            size = c.scalar(text("SELECT pg_relation_size(:name)"), {"name": f"{schema}.{INDEX}"})
            print(json.dumps({"schema": schema, "rows": rows, "index_build_ms": build_ms,
                "index_bytes": size, "queries": results, "write_batch_rows": 5000,
                "writes_before": before_writes, "writes_after": after_writes}), flush=True)
    finally:
        with engine.begin() as c:
            # The target is an internally generated identifier, never a caller path.
            assert schema.startswith("asset_search_bench_") and schema.replace("_", "").isalnum()
            c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


if __name__ == "__main__":
    main()
