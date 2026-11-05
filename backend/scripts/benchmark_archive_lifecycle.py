"""Exercise real archive/restore/purge services in a disposable test schema.

Refuses nonlocal and non-test databases. No demo/application rows, uploads or
settings are changed. The private schema has the application's indexes and
statement triggers; each job uses its normal 20,000-row chunk transactions.
"""
import argparse
import json
import logging
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.base import Base
from app.models.enums import ArchiveAction, ArchiveItemType, ScanStatus
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.finding import Finding
from app.services import archive_service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=10000, choices=(10000,100000,500000))
    parser.add_argument("--manual", type=int, default=100, choices=(0,1,100,500))
    parser.add_argument("--statement-timeout", type=int, default=20, choices=(20,60,120))
    args = parser.parse_args()
    url = make_url(settings.TEST_DATABASE_URL)
    if (url.get_backend_name() != "postgresql" or url.host not in {"localhost","127.0.0.1","::1"}
            or not url.database or not url.database.endswith("_test")):
        raise SystemExit("Archive performance checks require a local *_test database")
    schema = "archive_perf_"+uuid.uuid4().hex
    admin = create_engine(url)
    engine = None
    created = False
    logging.getLogger(archive_service.__name__).setLevel(logging.CRITICAL)
    try:
        with admin.begin() as connection:
            assert connection.scalar(text("SELECT current_database()")) == url.database
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        engine = create_engine(url.update_query_dict({"options":f"-csearch_path={schema},public -cstatement_timeout={args.statement_timeout*1000}"}))
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
        # Force private copies: checkfirst otherwise sees public test tables.
        # Public remains visible only for extension types/operator classes.
        Base.metadata.create_all(engine, checkfirst=False)
        with engine.connect() as connection:
            for table in Base.metadata.tables:
                actual = connection.scalar(text("SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=to_regclass(:name)"), {"name":table})
                assert actual == schema, f"Benchmark table is not private: {table}"
        with Session(engine) as db:
            db.execute(text("SET statement_timeout='300s'"))
            organization = Organization(name="Synthetic archive performance")
            db.add(organization); db.flush()
            upload = Scan(org_id=organization.id,scan_type="findings_import",source="upload",
                filename="synthetic-archive-performance.csv",status=ScanStatus.completed)
            db.add(upload); db.flush()
            org_id, scan_id = organization.id, upload.id
            started = time.perf_counter()
            db.execute(text("""INSERT INTO assets(id,org_id,type,hostname,type_known,details,created_at)
                SELECT gen_random_uuid(),:org,'server','archive-perf-'||i,true,
                    jsonb_build_object('synthetic',true),now() FROM generate_series(1,:rows) i"""),{"org":org_id,"rows":args.rows})
            db.execute(text("""INSERT INTO asset_scans(scan_id,asset_id,created)
                SELECT :scan,id,true FROM assets WHERE org_id=:org"""),{"scan":scan_id,"org":org_id})
            db.execute(text("""INSERT INTO findings(id,org_id,scan_id,asset_id,domain,severity,source,category,description,created_at)
                SELECT gen_random_uuid(),:org,:scan,id,
                    'vulnerability_management','high','archive_perf',hostname,'Synthetic archive finding '||hostname,now()
                FROM assets WHERE org_id=:org"""),{"org":org_id,"scan":scan_id})
            manuals = [Finding(org_id=org_id,domain="identity_access",severity="low",source="manual",
                category=f"manual-{i}",description=f"Synthetic manual {i}") for i in range(args.manual)]
            db.add_all(manuals); db.commit()
            manual_ids = [item.id for item in manuals]
            db.execute(text("ANALYZE assets,findings,asset_scans,scans")); db.commit()
            db.execute(text(f"SET statement_timeout='{args.statement_timeout}s'")); db.commit()
            print(json.dumps({"phase":"seed","assets":args.rows,"findings":args.rows,"manual_findings":args.manual,
                "seconds":round(time.perf_counter()-started,3)}),flush=True)

            def run(action, item_id, kind=ArchiveItemType.upload):
                chunks, slow, duplicate_times = [], [], []
                def before(conn,cursor,statement,parameters,context,many):
                    context.archive_bench_start = time.perf_counter()
                def after(conn,cursor,statement,parameters,context,many):
                    elapsed = time.perf_counter()-context.archive_bench_start
                    if statement.lstrip().upper().startswith("DELETE FROM FINDINGS F "):
                        duplicate_times.append(elapsed)
                    if elapsed > .5:
                        slow.append({"seconds":round(elapsed,3),"sql":statement[:180].replace("\n"," ")})
                started = time.perf_counter()
                job = (archive_service.start_archive(db,org_id,kind,item_id,None) if action == ArchiveAction.archive else
                       archive_service.start_batch_job(db,org_id,item_id,action,None))
                def committed(session):
                    progress = job.__dict__.get("progress")
                    if progress and (not chunks or progress != chunks[-1]["progress"]):
                        chunks.append({"elapsed_seconds":round(time.perf_counter()-started,3),"progress":dict(progress)})
                event.listen(engine,"before_cursor_execute",before)
                event.listen(engine,"after_cursor_execute",after)
                event.listen(db,"after_commit",committed)
                try:
                    job = archive_service.run_job(db,job.id)
                    result = {"action":action.value,"kind":kind.value,"seconds":round(time.perf_counter()-started,3),
                        "status":job.status.value,"summary":job.summary,"progress_updates":chunks,"slow_queries":slow,
                        "duplicate_check":{"queries":len(duplicate_times),"total_seconds":round(sum(duplicate_times),3),
                            "max_seconds":round(max(duplicate_times,default=0),3)}}
                    if kind != ArchiveItemType.finding or args.manual == 1:
                        print(json.dumps(result),flush=True)
                    if job.status != ScanStatus.completed:
                        raise RuntimeError(f"{kind.value} {action.value} failed; inspect timing before increasing the timeout")
                    return job.batch_id
                finally:
                    event.remove(db,"after_commit",committed)
                    event.remove(engine,"before_cursor_execute",before)
                    event.remove(engine,"after_cursor_execute",after)

            batch = run(ArchiveAction.archive,scan_id)
            run(ArchiveAction.restore,batch)
            batch = run(ArchiveAction.archive,scan_id)
            run(ArchiveAction.purge,batch)
            assert db.scalar(text("SELECT count(*) FROM assets")) == 0
            assert db.scalar(text("SELECT count(*) FROM findings")) == args.manual
            assert db.scalar(text("SELECT count(*) FROM scans")) == 0
            if manual_ids:
                started = time.perf_counter()
                batches = [run(ArchiveAction.archive,identifier,ArchiveItemType.finding) for identifier in manual_ids]
                print(json.dumps({"phase":"manual_archive_total","items":len(batches),"seconds":round(time.perf_counter()-started,3)}),flush=True)
                started = time.perf_counter()
                for batch in batches:
                    run(ArchiveAction.restore,batch,ArchiveItemType.finding)
                assert db.scalar(text("SELECT count(*) FROM findings")) == args.manual
                print(json.dumps({"phase":"manual_restore_total","items":len(batches),"seconds":round(time.perf_counter()-started,3)}),flush=True)
                started = time.perf_counter()
                batches = [run(ArchiveAction.archive,identifier,ArchiveItemType.finding) for identifier in manual_ids]
                print(json.dumps({"phase":"manual_rearchive_total","items":len(batches),"seconds":round(time.perf_counter()-started,3)}),flush=True)
                started = time.perf_counter()
                for batch in batches:
                    run(ArchiveAction.purge,batch,ArchiveItemType.finding)
                print(json.dumps({"phase":"manual_purge_total","items":len(batches),"seconds":round(time.perf_counter()-started,3)}),flush=True)
            assert db.scalar(text("SELECT count(*) FROM findings")) == 0
            print(json.dumps({"verification":"synthetic rows purged; source application data untouched"}),flush=True)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.begin() as connection:
                assert schema.startswith("archive_perf_") and len(schema) == len("archive_perf_")+32
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
