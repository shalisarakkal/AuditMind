"""Opt-in synthetic directory benchmark; only an owned schema in local *_test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-old-control", action="store_true", help="Explicitly reproduce the regression, at most 10000 rows")
    parser.add_argument("--control-rows", type=int, default=2000)
    parser.add_argument("--rows", type=int, default=500000)
    parser.add_argument("--hosts", type=int, default=10800)
    args = parser.parse_args()
    if not (1 <= args.hosts <= args.rows <= 500000):
        raise SystemExit("Require 1 <= hosts <= rows <= 500000")
    if args.include_old_control and not (args.hosts <= args.control_rows <= min(args.rows,10000)):
        raise SystemExit("Old control requires hosts <= control rows <= min(rows,10000); use a small host count")
    from app.core.config import settings
    from sqlalchemy import create_engine, event, func, select, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    url = make_url(settings.TEST_DATABASE_URL)
    if url.get_backend_name() != "postgresql" or url.host not in ("localhost", "127.0.0.1") or not (url.database or "").endswith("_test"):
        raise SystemExit("Only local PostgreSQL *_test targets are allowed")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import httpx
    import httpx2
    def forbidden(*a, **kw):
        raise RuntimeError("External HTTP forbidden in synthetic benchmark")
    for module in (httpx,httpx2):
        module.HTTPTransport.handle_request = forbidden
        module.AsyncHTTPTransport.handle_async_request = forbidden
    from app.db.base import Base
    from app.models.organization import Organization
    from app.models.scan import Scan
    from app.models.asset import Asset
    from app.models.finding import Finding
    from app.models.finding_observation import FindingObservation
    from app.models.enums import ScanStatus
    from app.services import ingestion_service as ingestion
    from app.services.import_profiles import FAMILIES, builtin_profile
    schema = "observation_bench_" + uuid.uuid4().hex
    assert re.fullmatch(r"observation_bench_[0-9a-f]{32}", schema)
    root = Path(__file__).resolve().parents[2]
    output = root / "temp/testing/import-batching" / schema
    output.mkdir(parents=True)
    maintenance = create_engine(url)
    engine = create_engine(url.update_query_dict({"options": f"-csearch_path={schema},public"}))
    results = {"schema":schema,"hosts":args.hosts,"runs":[],"ordinary_data_changed":False}
    created = False
    original_observe = ingestion._PendingWrites.observe
    def old_observe(writes, values):
        writes.observations.append(values)
        if len(writes.observations) >= ingestion.WRITE_BATCH:
            writes.flush()
    def record(conn,cursor,statement,parameters,context,executemany):
        if statement.lower().startswith("update assets as target set"):
            results["runs"][-1]["asset_update_executions"] += 1
    def data_file(rows):
        path = output / f"directory-{rows}.csv"
        if not path.exists():
            with path.open("w",encoding="utf-8",newline="") as handle:
                handle.write("Hostname,Type,Owner,Status,LastLogin\n")
                for i in range(rows):
                    handle.write(f"batch-host-{i % args.hosts},Server,owner-{i},Disabled,2000-01-01 00:00:00\n")
        return path
    def run(db,org,rows,mode):
        item={"mode":mode,"rows":rows,"asset_update_executions":0}
        results["runs"].append(item)
        ingestion._PendingWrites.observe = old_observe if mode=="old-control" else original_observe
        scan=Scan(org_id=org.id,scan_type="directory_import",source="upload",profile="directory",
            filename=f"synthetic-{mode}-{rows}.csv",status=ScanStatus.pending,started_at=datetime.now(timezone.utc))
        db.add(scan);db.commit()
        source_path=data_file(rows)
        started=time.perf_counter()
        report=ingestion.process_import(db,scan,"profile","csv",source_path,builtin_profile(FAMILIES["directory"]))
        item["seconds"]=round(time.perf_counter()-started,3)
        db.refresh(scan)
        assert scan.status==ScanStatus.completed
        item["observations"]=db.scalar(select(func.count()).select_from(FindingObservation).where(FindingObservation.import_id==scan.id))
        item["duplicates"]=report.duplicates
        assert item["observations"]==rows*2
        assert db.scalar(select(func.count()).select_from(Asset))==args.hosts
        assert db.scalar(select(func.count()).select_from(Finding))==args.hosts*2
        if mode!="seed": assert report.duplicates==rows*2
        if mode=="fixed": assert item["asset_update_executions"]==(args.hosts+ingestion.UPDATE_BATCH-1)//ingestion.UPDATE_BATCH
        digest=hashlib.sha256()
        for row in db.execute(select(Asset.hostname,Asset.details).order_by(Asset.hostname)):
            host=int(row.hostname.rsplit('-',1)[1])
            last=host+((rows-1-host)//args.hosts)*args.hosts
            assert row.details['owner']==f'owner-{last}', 'Last-row-wins payload changed'
            digest.update(json.dumps(list(row),sort_keys=True).encode())
        item["asset_payload_digest"]=digest.hexdigest()
        (output/"results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
        print(json.dumps(item),flush=True)
    try:
        with maintenance.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
        created=True
        with engine.connect() as c:
            assert c.scalar(text("select current_schema()"))==schema
        Base.metadata.create_all(engine)
        event.listen(engine,"before_cursor_execute",record)
        with Session(engine,autoflush=False) as db:
            org=Organization(name="Synthetic observation batching benchmark")
            db.add(org);db.commit()
            run(db,org,args.hosts,"seed")
            if args.include_old_control:
                run(db,org,args.control_rows,"old-control")
                run(db,org,args.control_rows,"fixed")
                assert results["runs"][1]["asset_payload_digest"]==results["runs"][2]["asset_payload_digest"]
            if not args.include_old_control or args.rows!=args.control_rows:
                run(db,org,args.rows,"fixed")
        results["passed"]=True
    finally:
        ingestion._PendingWrites.observe=original_observe
        engine.dispose()
        if created:
            with maintenance.begin() as c:
                assert c.scalar(text("select current_database()"))==url.database
                assert re.fullmatch(r"observation_bench_[0-9a-f]{32}",schema)
                c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            results["schema_removed"]=True
        maintenance.dispose()
        (output/"results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
        print("Evidence: "+str(output),flush=True)


if __name__=="__main__":
    if not __debug__: raise SystemExit("Assertions must be enabled")
    main()
