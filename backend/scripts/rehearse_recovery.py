"""Opt-in synthetic logical-backup/worker-recovery rehearsal.

Creates its own loopback PostgreSQL cluster and two databases. Never connects to
configured application/test databases, changes their roles, or restarts services.
Keeps synthetic backup/evidence files; stops and removes only its own cluster.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid
import zipfile

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
ARTIFACTS = ROOT / "temp" / "testing" / "recovery"
sys.path.insert(0, str(BACKEND))
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
DATABASES = {"recovery_source_test", "recovery_restored_test"}


def emit(**record):
    print(json.dumps(record), flush=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def guarded_root(value):
    assert ARTIFACTS.resolve().is_relative_to(ROOT.resolve())
    assert not Path(value).is_symlink()
    path = Path(value).resolve()
    assert path.parent == ARTIFACTS.resolve() and path.name.startswith("recovery_")
    suffix = path.name[len("recovery_"):]
    assert uuid.UUID(hex=suffix).hex == suffix
    return path


def configure(url, files, key):
    parsed = make_url(url)
    assert parsed.host == "127.0.0.1" and parsed.database in DATABASES
    assert parsed.port == int(os.environ["RECOVERY_PORT"])
    values = dict(DATABASE_URL=url, UPLOAD_DIR=str(files), SECRET_KEY=key,
        ANTHROPIC_API_KEY="", OPENAI_API_KEY="", VOYAGE_API_KEY="", OPENROUTER_API_KEY="",
        OPENROUTER_INFERENCE_ENABLED="false", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        ARCHIVE_AUTO_PURGE="false", WORKER_STALE_SECONDS="30", WORKER_CONCURRENCY="1",
        RULE_BASED_TEST_REPORTS_ENABLED="true", REPORT_EVIDENCE_V3_ENABLED="false")
    os.environ.update(values)
    from app.core.config import Settings, settings
    refreshed = Settings()
    for name in Settings.model_fields:
        setattr(settings,name,getattr(refreshed,name))
    import httpx
    import httpx2
    def forbidden(*args,**kwargs):
        raise RuntimeError("External HTTP disabled in synthetic recovery rehearsal")
    for module in (httpx,httpx2):
        module.HTTPTransport.handle_request = forbidden
        module.AsyncHTTPTransport.handle_async_request = forbidden


def worker(mode, root):
    root = guarded_root(root)
    url = os.environ["RECOVERY_DATABASE_URL"]
    pid_record = (root/"cluster"/"postmaster.pid").read_text().splitlines()
    assert int(pid_record[3]) == make_url(url).port
    assert Path(pid_record[1]).resolve() == (root/"cluster").resolve()
    configure(url,root/os.environ["RECOVERY_FILES"],os.environ["RECOVERY_KEY"])
    from app.services import ingestion_service, import_staging
    from app.worker import runner
    from app.db.session import engine
    marker = root / ("paused.json" if mode == "pause" else "resumed.json")
    if mode == "pause":
        original = ingestion_service._PendingWrites.flush
        def flush(pending):
            original(pending)
            if pending.rows_done > 0 and not marker.exists():
                uncommitted = pending.db.scalar(text("SELECT count(*) FROM assets WHERE hostname LIKE 'queued-host-%'"))
                marker.write_text(json.dumps({"uncommitted_assets":uncommitted}),encoding="utf-8")
                # Parent terminates only this owned child tree at the marker.
                until = time.monotonic()+90
                while time.monotonic()<until:
                    time.sleep(.1)
                raise RuntimeError("Rehearsal parent did not interrupt worker")
        ingestion_service._PendingWrites.flush = flush
    else:
        original = import_staging.DbStaging.load
        def load(staging):
            state = original(staging)
            marker.write_text(json.dumps({"rows_seen":state.rows_seen,"read_done":state.read_done}),encoding="utf-8")
            return state
        import_staging.DbStaging.load = load
    with Session(engine) as db:
        runner.reap_stale(db)
        worked = runner.run_once(db,allow_org_purge=False)
    emit(worker=mode,worked=worked)
    engine.dispose()


def canonical_check(definition):
    """Normalize only pg_dump's unbounded-varchar -> text array cast rewrite."""
    literal = r"'(?:[^']|'')*'"
    definition = re.sub(rf"\(({literal})::character varying\)::text",r"\1::text",definition)
    def array(match):
        items = re.sub(rf"({literal})::character varying",r"\1::text",match.group(1))
        return "ARRAY["+items+"]"
    return re.sub(rf"\(ARRAY\[({literal}::character varying(?:, {literal}::character varying)*)\]\)::text\[\]",array,definition)


def snapshot(engine, raw_schema_path=None):
    result = {"tables":{}}
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
        for table in sorted(inspect(c).get_table_names(schema="public")):
            quoted = c.dialect.identifier_preparer.quote(table)
            fingerprint = hashlib.sha256(); count = 0
            for row in c.execute(text(f"SELECT to_jsonb(t)::text FROM public.{quoted} t ORDER BY to_jsonb(t)::text")):
                fingerprint.update(row[0].encode()); fingerprint.update(b"\n"); count += 1
            result["tables"][table] = {"rows":count,"sha256":fingerprint.hexdigest()}
        definitions = c.execute(text("""SELECT 'index',indexname,indexdef FROM pg_indexes WHERE schemaname='public'
            UNION ALL SELECT 'constraint',conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace
            UNION ALL SELECT 'trigger',tgname,pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal
                AND tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace)
            UNION ALL SELECT 'function',proname,pg_get_functiondef(oid) FROM pg_proc
                WHERE pronamespace='public'::regnamespace AND proname LIKE 'am_%'
            ORDER BY 1,2,3""")).all()
        if raw_schema_path:
            raw_schema_path.write_text(json.dumps([list(row) for row in definitions],indent=2),encoding="utf-8")
        result["schema_definitions"] = [[kind,name,canonical_check(sql) if kind in {"constraint","index"} else sql] for kind,name,sql in definitions]
        result["schema_sha256"] = digest(json.dumps(result["schema_definitions"]).encode())
        result["invalid_indexes"] = c.scalar(text("SELECT count(*) FROM pg_index WHERE NOT indisvalid"))
    return result


def file_manifest(folder):
    return {p.relative_to(folder).as_posix():digest(p.read_bytes()) for p in sorted(folder.rglob("*")) if p.is_file()}


def verify_files(folder, expected):
    if file_manifest(folder) != expected:
        raise ValueError("Restored file set/hash mismatch")


def verify_archive(path, expected_digest):
    if digest(path.read_bytes()) != expected_digest:
        raise ValueError("Backup archive checksum mismatch")


def run(args):
    root = ARTIFACTS / ("recovery_"+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False); guarded_root(root)
    cluster = root/"cluster"
    pg_bin = Path(args.pg_bin).resolve()
    tools = {name:pg_bin/(name+(".exe" if os.name=="nt" else "")) for name in ("initdb","pg_ctl","pg_dump","pg_restore")}
    assert all(p.is_file() for p in tools.values()), "PostgreSQL client/server binaries required"
    result = {"run":root.name,"synthetic_only":True,"checks":[],"timings_seconds":{},"production_approval":False}
    engines, children = [], []
    secret_file = root/"bootstrap-password.txt"
    password = secrets.token_urlsafe(32); key = secrets.token_urlsafe(40)
    secret_file.write_text(password,encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1",0)); port = probe.getsockname()[1]
    os.environ["RECOVERY_PORT"] = str(port)
    env = {**os.environ,"PGPASSWORD":password,"PGHOST":"127.0.0.1","PGPORT":str(port),
           "PGUSER":"recovery_fixture","PGSSLMODE":"disable","PGCONNECT_TIMEOUT":"5"}
    source_url = URL.create("postgresql+psycopg",username="recovery_fixture",password=password,
        host="127.0.0.1",port=port,database="recovery_source_test")
    target_url = source_url.set(database="recovery_restored_test")
    def command(name,*arguments,timeout=180):
        # A server started by pg_ctl can inherit PIPE handles on Windows and
        # keep communicate() waiting after pg_ctl exits. Use an owned log file.
        with (root/(name+".log")).open("a",encoding="utf-8") as log:
            completed = subprocess.run([str(tools[name]),*map(str,arguments)],env=env,cwd=BACKEND,
                stdout=log,stderr=subprocess.STDOUT,text=True,timeout=timeout,creationflags=NO_WINDOW)
        if completed.returncode:
            raise RuntimeError(f"{name} failed ({completed.returncode}); inspect the synthetic run log")
        return completed.returncode
    def check(message):
        result["checks"].append(message); emit(check=message)
    def start_worker(mode,url,files):
        child_env = {**os.environ,"RECOVERY_DATABASE_URL":url.render_as_string(hide_password=False),
            "RECOVERY_FILES":files,"RECOVERY_KEY":key,"RECOVERY_PORT":str(port)}
        with (root/(mode+"-worker.log")).open("w",encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker",mode,"--root",str(root)],
                env=child_env,cwd=BACKEND,stdout=log,stderr=log,creationflags=NO_WINDOW)
        children.append(process); return process
    def stop_child(process):
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],check=True,capture_output=True,creationflags=NO_WINDOW)
            else:
                process.kill()
            process.wait(timeout=15)
    try:
        t = time.perf_counter()
        command("initdb","-D",cluster,"-U","recovery_fixture","--pwfile",secret_file,
            "--auth-local=scram-sha-256","--auth-host=scram-sha-256","--encoding=UTF8","--locale=C")
        secret_file.unlink()
        command("pg_ctl","-D",cluster,"-l",root/"postgres.log","-o",f"-h 127.0.0.1 -p {port}","-w","-t","30","start")
        bootstrap = create_engine(source_url.set(database="postgres"),isolation_level="AUTOCOMMIT",hide_parameters=True)
        engines.append(bootstrap)
        with bootstrap.connect() as c:
            for database in sorted(DATABASES):
                c.execute(text(f'CREATE DATABASE "{database}"'))
        configure(source_url.render_as_string(hide_password=False),root/"source_files",key)
        source = create_engine(source_url,hide_parameters=True); target = create_engine(target_url,hide_parameters=True)
        engines.extend([source,target])
        from alembic import command as migration
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        config = Config(str(BACKEND/"alembic.ini")); config.set_main_option("script_location",str(BACKEND/"alembic")); config.config_file_name = None
        head = ScriptDirectory.from_config(config).get_current_head()
        with source.connect() as c:
            config.attributes.update(connection=c,version_table_schema="public")
            migration.upgrade(config,"head")
        result["migration_head"] = head
        result["timings_seconds"]["isolated_cluster_and_migrations"] = round(time.perf_counter()-t,3)
        check("Fresh private loopback cluster and separate source/restore databases migrated without application access")

        from app.models.organization import Organization
        from app.models.user import User
        from app.models.membership import OrgMembership
        from app.models.asset import Asset
        from app.models.finding import Finding
        from app.models.finding_history import FindingHistory
        from app.models.scan import Scan
        from app.models.knowledge import KnowledgeDocument, KnowledgeVersion
        from app.models.organization_logo import OrganizationLogo
        from app.models.enums import ArchiveItemType, ArchiveAction
        from app.models.report import Report
        from app.schemas.finding_workflow import WorkflowTarget, WorkflowPatch
        from app.services import finding_workflow, report_service, archive_service
        from PIL import Image
        files = root/"source_files"; files.mkdir()
        policy = "# Synthetic recovery policy\nThis is test evidence only.\n"
        (files/"documents").mkdir(); (files/"documents"/"policy.md").write_text(policy,encoding="utf-8")
        with Session(source) as db:
            org, other = Organization(name="Recovery synthetic"),Organization(name="Recovery foreign tenant")
            actor = User(email="owner@recovery.invalid",name="Synthetic recovery owner")
            db.add_all([org,other,actor]); db.flush()
            member = OrgMembership(org_id=org.id,user_id=actor.id,role="admin"); db.add(member)
            asset = Asset(org_id=org.id,type="server",hostname="baseline-host",environment="test")
            db.add(asset); db.flush()
            finding = Finding(org_id=org.id,asset_id=asset.id,domain="network_config",severity="high",source="manual",description="Synthetic recovery finding")
            db.add(finding); db.commit()
            finding_workflow.update_workflows(db,org.id,member,[WorkflowTarget(finding_id=finding.id,expected_version=0)],
                WorkflowPatch(status="mitigated",rationale="Synthetic remediation note",verification="Synthetic verification proof"))
            job = archive_service.start_archive(db,org.id,ArchiveItemType.finding,finding.id,actor.id)
            job = archive_service.run_job(db,job.id); assert job.status.value == "completed"
            archived_batch = job.batch_id
            document = KnowledgeDocument(org_id=org.id,title="Synthetic recovery policy")
            db.add(document); db.flush()
            version = KnowledgeVersion(document_id=document.id,number=1,edition="fixture-v1",source="fixture://policy",
                content_kind="org_policy",rights="Synthetic test fixture",content=policy,content_hash=digest(policy.encode()),current=True)
            db.add(version)
            image = io.BytesIO(); Image.new("RGB",(16,16),"blue").save(image,format="PNG")
            db.add(OrganizationLogo(org_id=org.id,version=str(uuid.uuid4()),image=image.getvalue())); db.commit()
            report = report_service.create_rule_based_test_report(db,org.id,"Synthetic recovery report",actor.id)
            (files/"report.html").write_text(report_service.render_report_html(report),encoding="utf-8")
            scan = Scan(org_id=org.id,scan_type="asset_import",source="upload",filename="recovery.csv",started_by=actor.id,
                started_at=datetime.now(timezone.utc),status="pending")
            db.add(scan); db.flush()
            csv = ("type,hostname,environment\n"+"".join(f"server,queued-host-{i},test\n" for i in range(args.rows))).encode()
            scan.content_hash = digest(csv); (files/f"{scan.id}.upload").write_bytes(csv); db.commit()
            org_id, foreign_id, finding_id, scan_id, version_id, report_id, actor_id = org.id,other.id,finding.id,scan.id,version.id,report.id,actor.id
        source_worker = start_worker("pause",source_url,"source_files")
        until = time.monotonic()+60
        while not (root/"paused.json").exists():
            assert source_worker.poll() is None, "Source worker stopped before its interruption marker"
            if time.monotonic()>until: raise TimeoutError("Worker did not reach an uncommitted publication")
            time.sleep(.1)
        marker = json.loads((root/"paused.json").read_text())
        assert marker["uncommitted_assets"] >= 2000
        with source.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM assets WHERE hostname LIKE 'queued-host-%'")) == 0
        interrupted = time.perf_counter(); stop_child(source_worker)
        with source.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM assets WHERE hostname LIKE 'queued-host-%'")) == 0
            assert c.scalar(text("SELECT count(*) FROM import_staging_chunks")) > 0
        check("Actual worker killed after uncommitted publication; zero partial assets visible and committed staging/file retained")

        expected = snapshot(source,root/"source-schema-raw.json"); expected_files = file_manifest(files)
        bundle = root/"bundle"; bundle.mkdir()
        t = time.perf_counter()
        command("pg_dump","--dbname","recovery_source_test","--format=custom","--file",bundle/"database.dump","--no-owner","--no-acl")
        with zipfile.ZipFile(bundle/"files.zip","w",compression=zipfile.ZIP_DEFLATED) as archive:
            for name in expected_files: archive.write(files/name,name)
        manifest = {"migration_head":head,"tables":expected,"files":expected_files,
            "database_sha256":digest((bundle/"database.dump").read_bytes()),"files_zip_sha256":digest((bundle/"files.zip").read_bytes())}
        (bundle/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        result["timings_seconds"]["quiesced_database_and_files_backup"] = round(time.perf_counter()-t,3)
        result["backup_bytes"] = {p.name:p.stat().st_size for p in bundle.iterdir()}
        check("Quiesced database custom archive and companion files captured with SHA-256 manifest")

        restore_started = time.perf_counter()
        verify_archive(bundle/"database.dump",manifest["database_sha256"])
        verify_archive(bundle/"files.zip",manifest["files_zip_sha256"])
        bad = bytearray((bundle/"database.dump").read_bytes()); bad[0] ^= 1
        corrupt_archive = root/"corrupted-database.dump"; corrupt_archive.write_bytes(bad)
        try: verify_archive(corrupt_archive,manifest["database_sha256"])
        except ValueError: pass
        else: raise AssertionError("Corrupted archive was not rejected")
        check("Corrupted database archive fails the manifest check before restore")
        command("pg_restore","--dbname","recovery_restored_test","--exit-on-error","--no-owner","--no-acl",bundle/"database.dump")
        restored_files = root/"restored_files"; restored_files.mkdir()
        with zipfile.ZipFile(bundle/"files.zip") as archive:
            for name in archive.namelist():
                destination = (restored_files/name).resolve()
                assert destination.is_relative_to(restored_files.resolve())
                destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(archive.read(name))
        verify_files(restored_files,expected_files)
        actual = snapshot(target,root/"restored-schema-raw.json")
        (root/"restored-snapshot.json").write_text(json.dumps(actual,indent=2),encoding="utf-8")
        if actual != expected:
            result["restore_differences"] = {
                "tables":[name for name in expected["tables"] if expected["tables"][name] != actual["tables"].get(name)],
                "schema_equal":actual["schema_sha256"] == expected["schema_sha256"],
                "invalid_indexes":actual["invalid_indexes"],
            }
            emit(restore_differences=result["restore_differences"])
        assert actual == expected, "Restored database row/schema fingerprints differ"
        assert actual["invalid_indexes"] == 0
        result["table_rows"] = {name:row["rows"] for name,row in actual["tables"].items()}
        result["timings_seconds"]["restore_and_full_verification"] = round(time.perf_counter()-restore_started,3)
        check("Every table row hash/count, app schema definition and file hash matches in the separate restore database")
        missing = restored_files/f"{scan_id}.upload"; saved = missing.read_bytes(); missing.unlink()
        try: verify_files(restored_files,expected_files)
        except ValueError: pass
        else: raise AssertionError("Missing upload was not detected")
        missing.write_bytes(saved); verify_files(restored_files,expected_files)
        check("Missing restored queued file detected, then repaired from the captured bytes")
        with target.connect() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == head
            config.attributes.update(connection=c,version_table_schema="public"); c.commit(); migration.upgrade(config,"head")
        with Session(target) as db:
            state = finding_workflow.read_workflow(db,db.get(Finding,finding_id))
            assert state.status == "mitigated" and state.version == 1
            assert db.scalar(select(FindingHistory.rationale).where(FindingHistory.finding_id==finding_id)) == "Synthetic remediation note"
            assert db.get(KnowledgeVersion,version_id).content == policy
            assert "Synthetic recovery report" in report_service.render_report_html(db.get(Report,report_id))
            from fastapi import HTTPException
            try: finding_workflow.get_finding(db,foreign_id,finding_id)
            except HTTPException as error: assert error.status_code == 404
            else: raise AssertionError("Foreign tenant could read restored finding")
            # Wait for the real configured stale interval; no clock/heartbeat edit.
            heartbeat = db.get(Scan,scan_id).heartbeat_at
        check("Restored workflow/history, document version, report rendering, tenant boundary and migration no-op verified")
        stale_wait = max(0,30-(datetime.now(timezone.utc)-heartbeat).total_seconds()+.2)
        if stale_wait:
            emit(waiting_seconds=round(stale_wait,2),reason="Real rehearsal stale threshold, no simulated clock")
            time.sleep(stale_wait)
        t = time.perf_counter()
        recovered = start_worker("recover",target_url,"restored_files"); recovered.wait(timeout=60)
        assert recovered.returncode == 0, "Restored worker failed"
        resumed = json.loads((root/"resumed.json").read_text())
        assert resumed == {"rows_seen":args.rows,"read_done":True}
        with Session(target) as db:
            completed = db.get(Scan,scan_id)
            assert completed.status.value == "completed" and completed.retry_count == 1
            assert completed.summary["created"] == args.rows
            assert db.scalar(text("SELECT count(*) FROM assets WHERE hostname LIKE 'queued-host-%'")) == args.rows
            assert db.scalar(text("SELECT count(DISTINCT hostname) FROM assets WHERE hostname LIKE 'queued-host-%'")) == args.rows
            assert db.scalar(text("SELECT count(*) FROM import_staging_state")) == 0
            assert not (restored_files/f"{scan_id}.upload").exists()
        result["timings_seconds"]["worker_restart_to_completed"] = round(time.perf_counter()-t,3)
        result["timings_seconds"]["interruption_to_restored_completed_job"] = round(time.perf_counter()-interrupted,3)
        result["worker_stale_threshold_seconds"] = 30
        check("Restored real worker reaps stale job once, authenticates/resumes staging and publishes exactly the queued rows")
        before_restart = snapshot(target)
        restarted = start_worker("drain",target_url,"restored_files"); restarted.wait(timeout=30)
        assert restarted.returncode == 0 and snapshot(target) == before_restart
        check("Second worker restart performs no duplicate work or durable data changes")
        with Session(target) as db:
            restore_job = archive_service.start_batch_job(db,org_id,archived_batch,ArchiveAction.restore,actor_id)
            restore_job = archive_service.run_job(db,restore_job.id)
            assert restore_job.status.value == "completed"
            assert db.get(Finding,finding_id).archived_at is None
            assert db.scalar(select(FindingHistory.rationale).where(FindingHistory.finding_id==finding_id)) == "Synthetic remediation note"
            assert db.scalar(text("SELECT count(*) FROM ai_usage")) == 0
        assert snapshot(source) == expected, "Restore/recovery changed the source fixture database"
        check("Restored archived finding can be recovered with history intact; source fixture unchanged and no AI usage")
        result["status"] = "passed"
    except Exception as error:
        result["status"] = "failed"; result["failure_type"] = type(error).__name__
        raise
    finally:
        for child in children:
            try:
                stop_child(child)
            except Exception as error:
                result.setdefault("cleanup_errors",[]).append(type(error).__name__)
        for engine in engines: engine.dispose()
        if cluster.exists():
            if (cluster/"postmaster.pid").exists():
                try:
                    command("pg_ctl","-D",cluster,"-m","fast","-w","stop")
                except Exception as error:
                    result.setdefault("cleanup_errors",[]).append(type(error).__name__)
            # Recursive deletion is restricted to this newly created owned cluster.
            assert guarded_root(root) == root and cluster.resolve().parent == root
            assert cluster.name == "cluster" and not cluster.is_symlink()
            if not (cluster/"postmaster.pid").exists():
                shutil.rmtree(cluster)
                result["private_cluster_removed"] = True
        secret_file.unlink(missing_ok=True)
        cleanup_failed = bool(result.get("cleanup_errors")) or not result.get("private_cluster_removed")
        if cleanup_failed and result.get("status") == "passed":
            result["status"] = "failed_cleanup"
        (root/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        emit(status=result.get("status"),checks=len(result["checks"]),artifacts=str(root),private_cluster_removed=result.get("private_cluster_removed",False))
        if cleanup_failed and sys.exc_info()[0] is None:
            raise RuntimeError("Private fixture cleanup incomplete; inspect results.json")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("Recovery rehearsal requires assertions enabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin")
    parser.add_argument("--rows",type=int,choices=(5000,10000),default=5000)
    parser.add_argument("--worker",choices=("pause","recover","drain"))
    parser.add_argument("--root")
    arguments = parser.parse_args()
    if arguments.worker:
        worker(arguments.worker,arguments.root)
    else:
        if not arguments.pg_bin: parser.error("--pg-bin is required")
        run(arguments)
