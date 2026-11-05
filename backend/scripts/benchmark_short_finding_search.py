"""Prototype short-pattern indexes in a disposable local-demo clone only.

No application migrations, source rows/indexes, settings or files are changed.
Includes current source indexes but excludes FK/statement-trigger costs, so write
timings isolate incremental index cost, not end-to-end ingestion throughput.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from app.core.config import settings
from scripts.demo import demo_url


def emit(**values):
    print(json.dumps(values, ensure_ascii=True), flush=True)


def timed(connection, statement, params=None):
    started = time.perf_counter()
    rows = connection.execute(text(statement), params or {}).all()
    return rows, (time.perf_counter()-started)*1000


def pattern(needle):
    return "%"+needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")+"%"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, choices=(100000,500000), default=100000)
    parser.add_argument("--batch", type=int, choices=(1000,5000), default=1000)
    parser.add_argument("--variant", action="append", choices=("punctuation","punctuation_regex","punctuation_bounded","grams"), default=[])
    args = parser.parse_args()
    engine = create_engine(demo_url(settings.DATABASE_URL))
    schema = "short_search_bench_"+uuid.uuid4().hex
    created = False
    phases = ("baseline", *(args.variant or ["punctuation_bounded","grams"]), "baseline_after")
    prototypes = {"punctuation","punctuation_regex","punctuation_bounded","grams"}
    needles = ("`", "%", "_", "\\", "a", "ab", "aa", "zz", "é", "🙂", "`a")
    try:
        with engine.connect() as c:
            assert c.scalar(text("SELECT current_schema()")) == "auditmind_demo"
            org = c.scalar(text("SELECT id FROM auditmind_demo.organizations WHERE name='SA01'"))
            if org is None:
                raise SystemExit("SA01 demo organization not found")
            indexes = c.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='auditmind_demo' AND tablename='findings' ORDER BY indexname")).all()
            c.execute(text(f'CREATE SCHEMA "{schema}"')); c.commit(); created = True
            c.execute(text(f'SET search_path TO "{schema}",auditmind_demo,public'))
            c.execute(text("SET statement_timeout='300s'"))
            # Separate primary measurements from driver's automatic generic
            # prepared-plan decisions. Explicit prepared probes below cover both.
            c.execute(text("SET plan_cache_mode='force_custom_plan'"))
            c.execute(text("CREATE TABLE findings (LIKE auditmind_demo.findings INCLUDING DEFAULTS INCLUDING CONSTRAINTS)"))
            started = time.perf_counter()
            # Stable hash sample across the organization, rather than the first
            # physical import. Only IDs are sorted; payloads load after LIMIT.
            c.execute(text("""INSERT INTO findings SELECT f.* FROM auditmind_demo.findings f JOIN
                (SELECT id FROM auditmind_demo.findings WHERE org_id=:org AND archived_at IS NULL
                 ORDER BY md5(id::text) LIMIT :rows) sample USING(id)"""), {"org":org,"rows":args.rows})
            assert c.scalar(text("SELECT count(*) FROM findings")) == args.rows
            # Known rare, escaped, repeated, Unicode and cross-field cases.
            for desc, category, archived, owner in (
                ("rare `a probe",None,False,org), ("literal % probe",None,False,org),
                ("literal _ probe",None,False,org), ("literal \\ probe",None,False,org),
                ("repeated aa",None,False,org), ("Unicode É é 🙂",None,False,org),
                ("a","b",False,org), (None,"` category",False,org),
                ("word"*4000+" `a end",None,False,org), ("letters"*3000,None,False,org),
                ("archived `",None,True,org), ("foreign `",None,False,uuid.uuid4()),
            ):
                c.execute(text("""INSERT INTO findings(id,org_id,domain,severity,description,category,created_at,archived_at)
                    VALUES(gen_random_uuid(),:org,'network_config','high',:d,:category,now(),CASE WHEN :archived THEN now() END)"""),
                    {"org":owner,"d":desc,"category":category,"archived":archived})
            for row in indexes:
                definition = row.indexdef.replace(" ON auditmind_demo.findings ", f' ON "{schema}".findings ')
                assert definition != row.indexdef
                c.execute(text(definition))
            c.commit()
            emit(phase="seed",rows=args.rows,seconds=round(time.perf_counter()-started,3),source_indexes=len(indexes))
            distribution = c.execute(text("SELECT round(avg(length(coalesce(description,'')||coalesce(category,'')))),max(length(coalesce(description,'')||coalesce(category,''))),pg_table_size('findings'),pg_indexes_size('findings') FROM findings")).one()
            emit(phase="sample_metadata",average_text_chars=int(distribution[0]),max_text_chars=distribution[1],table_bytes=distribution[2],baseline_index_bytes=distribution[3])
            c.execute(text(f"""CREATE FUNCTION "{schema}".punctuation(d text,cat text) RETURNS text[]
                LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path=pg_catalog AS $body$
                SELECT coalesce(array_agg(DISTINCT ch),'{{}}'::text[])
                FROM regexp_split_to_table(coalesce(d,'')||coalesce(cat,''),'') ch
                WHERE ascii(ch) BETWEEN 33 AND 126 AND ch !~ '[A-Za-z0-9]' $body$"""))
            c.execute(text(f"""CREATE FUNCTION "{schema}".grams(d text,cat text) RETURNS text[]
                LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path=pg_catalog AS $body$
                SELECT coalesce(array_agg(DISTINCT gram),'{{}}'::text[]) FROM
                  (SELECT substr(value,i,n) AS gram FROM (VALUES(lower(coalesce(d,''))),(lower(coalesce(cat,'')))) v(value)
                   CROSS JOIN generate_series(1,2) n CROSS JOIN LATERAL generate_series(1,length(value)-n+1) i) g $body$"""))
            c.execute(text(f"""CREATE FUNCTION "{schema}".punctuation_regex(d text,cat text) RETURNS text[]
                LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path=pg_catalog AS $body$
                SELECT coalesce(array_agg(DISTINCT m[1]),'{{}}'::text[])
                FROM regexp_matches(coalesce(d,'')||coalesce(cat,''),'[[:punct:]]','g') m
                WHERE ascii(m[1]) BETWEEN 33 AND 126 $body$"""))
            # A long value contributes every supported punctuation character.
            # This conservative superset avoids unbounded extraction work;
            # original LIKE/ILIKE still decides whether it really matches.
            c.execute(text(f"""CREATE FUNCTION "{schema}".punctuation_bounded(d text,cat text) RETURNS text[]
                LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path=pg_catalog AS $body$
                SELECT CASE WHEN octet_length(coalesce(d,''))+octet_length(coalesce(cat,''))>4096 THEN
                    ARRAY(SELECT chr(i) FROM generate_series(33,126) i WHERE chr(i) !~ '[A-Za-z0-9]')
                ELSE (SELECT coalesce(array_agg(DISTINCT ch),'{{}}'::text[])
                    FROM regexp_split_to_table(coalesce(d,'')||coalesce(cat,''),'') ch
                    WHERE ascii(ch) BETWEEN 33 AND 126 AND ch !~ '[A-Za-z0-9]') END $body$"""))
            assert c.scalar(text(f"""WITH chars AS (SELECT string_agg(chr(i),'') AS value FROM generate_series(33,126) i)
                SELECT "{schema}".punctuation(value,NULL) = "{schema}".punctuation_regex(value,NULL) FROM chars"""))
            assert c.scalar(text(f"""WITH chars AS (SELECT string_agg(chr(i),'') AS value FROM generate_series(33,126) i)
                SELECT "{schema}".punctuation(value,NULL) = "{schema}".punctuation_bounded(value,NULL) FROM chars"""))
            c.commit()
            columns = c.scalars(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:schema AND table_name='findings' ORDER BY ordinal_position"),{"schema":schema}).all()
            select_columns = ",".join("gen_random_uuid()" if name=="id" else ":write_org" if name=="org_id" else 'f."'+name+'"' for name in columns)
            write_org = uuid.uuid4()
            active = "org_id=:org AND archived_at IS NULL"
            order = "CASE WHEN severity='critical' THEN 0 WHEN severity='high' THEN 1 WHEN severity='medium' THEN 2 WHEN severity='low' THEN 3 ELSE 4 END,created_at DESC NULLS LAST,id"
            for phase in phases:
                c.execute(text(f'DROP INDEX IF EXISTS "{schema}".prototype_short_search')); c.commit()
                if phase in prototypes:
                    started = time.perf_counter()
                    c.execute(text(f'CREATE INDEX prototype_short_search ON findings USING gin ("{schema}".{phase}(description,category)) WHERE archived_at IS NULL'))
                    c.commit()
                    emit(phase=phase,index_build_seconds=round(time.perf_counter()-started,3),index_bytes=c.scalar(text("SELECT pg_relation_size('prototype_short_search')")))
                c.execute(text("ANALYZE findings")); c.commit()

                def predicate(needle, prototype=True):
                    op = "LIKE" if needle.isascii() and not any(ch.isalpha() for ch in needle) else "ILIKE"
                    exact = f"(description {op} :pattern ESCAPE '\\' OR category {op} :pattern ESCAPE '\\')"
                    extra, keys = "", []
                    if prototype and phase.startswith("punctuation"):
                        keys = sorted({ch for ch in needle if 33<=ord(ch)<=126 and not ch.isalnum()})
                    elif prototype and phase == "grams":
                        keys = [needle.lower()]
                    if keys:
                        extra = f'"{schema}".{phase}(description,category) @> CAST(:keys AS text[]) AND '
                    return extra+exact, {"org":org,"pattern":pattern(needle),"keys":keys}

                for needle in needles:
                    pred, params = predicate(needle)
                    baseline, _ = predicate(needle,False)
                    # Full set equality, including archived/tenant exclusions;
                    # candidate matches always retain the original recheck.
                    equivalent = c.scalar(text(f"""WITH expected AS (SELECT id FROM findings WHERE {active} AND {baseline}),
                        actual AS (SELECT id FROM findings WHERE {active} AND {pred})
                        SELECT NOT EXISTS ((SELECT id FROM expected EXCEPT SELECT id FROM actual)
                            UNION ALL (SELECT id FROM actual EXCEPT SELECT id FROM expected))"""),params)
                    assert equivalent, f"Candidate changed literal matching for {needle!r}"
                    durations, totals = [], []
                    for _ in range(3):
                        started = time.perf_counter()
                        sample = c.execute(text(f"SELECT id,domain,severity FROM findings WHERE {active} AND {pred} LIMIT 1001"),params).all()
                        if len(sample)<=1000:
                            total = len(sample)
                            if sample:
                                c.execute(text(f"SELECT id FROM findings WHERE id=ANY(:ids) ORDER BY {order} LIMIT 100"),{"ids":[row.id for row in sample]}).all()
                        else:
                            groups = c.execute(text(f"SELECT domain,severity,count(*) FROM findings WHERE {active} AND {pred} GROUP BY domain,severity"),params).all()
                            total = sum(row[2] for row in groups)
                            c.execute(text(f"SELECT id FROM findings WHERE {active} AND {pred} ORDER BY {order} LIMIT 100"),params).all()
                        durations.append((time.perf_counter()-started)*1000); totals.append(total)
                    assert len(set(totals)) == 1
                    plan = c.scalar(text("EXPLAIN (FORMAT JSON) SELECT id FROM findings WHERE "+active+" AND "+pred+" LIMIT 1001"),params)
                    emit(phase=phase,needle=needle,total=totals[0],first_ms=round(durations[0],2),median_ms=round(statistics.median(durations),2),uses_prototype="prototype_short_search" in json.dumps(plan))
                metrics = {name:[] for name in ("insert","workflow_update","text_update","archive","restore","delete")}
                for _ in range(3):
                    statements = {
                        "insert":f"INSERT INTO findings SELECT {select_columns} FROM findings f WHERE org_id=:org AND archived_at IS NULL LIMIT :batch",
                        "workflow_update":"UPDATE findings SET workflow_status='mitigated',workflow_version=workflow_version+1 WHERE org_id=:write_org",
                        "text_update":"UPDATE findings SET description=coalesce(description,'')||' ` updated ab' WHERE org_id=:write_org",
                        "archive":"UPDATE findings SET archived_at=now() WHERE org_id=:write_org",
                        "restore":"UPDATE findings SET archived_at=NULL WHERE org_id=:write_org",
                        "delete":"DELETE FROM findings WHERE org_id=:write_org",
                    }
                    for name, statement in statements.items():
                        started = time.perf_counter()
                        result = c.execute(text(statement),{"org":org,"write_org":write_org,"batch":args.batch})
                        assert result.rowcount == args.batch
                        c.commit(); metrics[name].append((time.perf_counter()-started)*1000)
                emit(phase=phase,batch_rows=args.batch,write_median_ms={key:round(statistics.median(values),2) for key,values in metrics.items()})
                if phase in prototypes:
                    for profile, value, minimum in (("mixed", "'x'||i::text||'`a'",16000),
                                                    ("dense", "'!%_`'||i::text",20000)):
                        started = time.perf_counter()
                        try:
                            with c.begin_nested():
                                c.execute(text("SET LOCAL statement_timeout='10s'"))
                                c.scalar(text(f'SELECT sum(cardinality("{schema}".{phase}(repeat({value},4000),NULL))) FROM generate_series(1,100) i'))
                                c.execute(text("SET LOCAL statement_timeout='300s'"))
                            emit(phase=phase,long_text_profile=profile,extraction_rows=100,min_chars=minimum,
                                extraction_ms=round((time.perf_counter()-started)*1000,2))
                        except DBAPIError as error:
                            if getattr(error.orig,"sqlstate",None) != "57014":
                                raise
                            emit(phase=phase,long_text_profile=profile,extraction_rows=100,min_chars=minimum,
                                timeout_seconds=10,unsafe_extraction_cost=True)
                # Explicitly inspect the plan actually EXECUTEd, rather than
                # EXPLAINing a separately parsed/custom version of the query.
                from psycopg import sql
                for needle in ("`","`a"):
                    pred, params = predicate(needle)
                    probe = (f"SELECT id FROM findings WHERE {active} AND {pred} LIMIT 1001"
                        .replace(":org","$1").replace(":pattern","$2").replace(":keys","$3"))
                    for mode in ("force_custom_plan","force_generic_plan"):
                        c.execute(text(f"SET plan_cache_mode='{mode}'"))
                        c.exec_driver_sql("PREPARE short_probe(uuid,text,text[]) AS "+probe)
                        statement = sql.SQL("EXPLAIN (ANALYZE, FORMAT JSON) EXECUTE short_probe ({},{},{})").format(
                            sql.Literal(org),sql.Literal(params["pattern"]),sql.Literal(params["keys"]))
                        with c.connection.driver_connection.cursor() as cursor:
                            cursor.execute(statement)
                            plan = cursor.fetchone()[0]
                        emit(phase=phase,prepared_needle=needle,plan_mode=mode,execution_ms=plan[0]["Execution Time"],uses_prototype="prototype_short_search" in json.dumps(plan))
                        c.exec_driver_sql("DEALLOCATE short_probe")
                    if phase.startswith("punctuation"):
                        exact, _ = predicate(needle,False)
                        probe = (f'WITH candidates AS MATERIALIZED (SELECT id,description,category FROM findings '
                            f'WHERE org_id=$1 AND archived_at IS NULL AND "{schema}".{phase}(description,category) @> $3::text[] LIMIT 1001) '
                            'SELECT id FROM candidates WHERE '+exact.replace(":pattern","$2")+' LIMIT 1001')
                        for mode in ("force_custom_plan","force_generic_plan"):
                            c.execute(text(f"SET plan_cache_mode='{mode}'"))
                            c.exec_driver_sql("PREPARE short_probe(uuid,text,text[]) AS "+probe)
                            with c.connection.driver_connection.cursor() as cursor:
                                cursor.execute(statement)
                                plan = cursor.fetchone()[0]
                            emit(phase=phase,prepared_needle=needle,plan_mode=mode,fenced=True,candidate_limit=1001,
                                execution_ms=plan[0]["Execution Time"],uses_prototype="prototype_short_search" in json.dumps(plan))
                            c.exec_driver_sql("DEALLOCATE short_probe")
                    c.execute(text("SET plan_cache_mode='force_custom_plan'"))
                if phase in prototypes:
                    # Query immediately after writes, including GIN's pending
                    # entries, then measure explicit pending-list maintenance.
                    pred, params = predicate("`")
                    _, elapsed = timed(c,f"SELECT count(*) FROM findings WHERE {active} AND {pred}",params)
                    started = time.perf_counter()
                    pages = c.scalar(text("SELECT gin_clean_pending_list('prototype_short_search'::regclass)")); c.commit()
                    emit(phase=phase,post_write_backtick_count_ms=round(elapsed,2),pending_cleanup_ms=round((time.perf_counter()-started)*1000,2),pending_pages=pages,index_bytes_after_writes=c.scalar(text("SELECT pg_relation_size('prototype_short_search')")))
            emit(verification="All candidate result sets equal original literal filters; source rows untouched")
    finally:
        if created:
            with engine.begin() as c:
                assert schema.startswith("short_search_bench_") and len(schema)==len("short_search_bench_")+32
                c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


if __name__ == "__main__":
    main()
