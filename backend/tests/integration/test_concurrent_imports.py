"""Two imports into the same org at once (e.g. a background import overlapping
another upload) must not both create the same host."""

import threading
import time
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.models.asset import Asset
from app.models.enums import ScanStatus
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.scan import Scan
from app.services import ingestion_service
from tests.conftest import requires_db

pytestmark = requires_db

FINDINGS = b"hostname,domain,severity,category\nweb-01,network_config,high,OPEN-RDP\n"


def test_concurrent_imports_share_one_asset(db_session, monkeypatch):
    org = Organization(name="Acme")
    db_session.add(org)
    db_session.commit()
    scans = [
        Scan(org_id=org.id, scan_type="findings_csv", status=ScanStatus.pending, started_at=datetime.now(timezone.utc))
        for _ in range(2)
    ]
    db_session.add_all(scans)
    db_session.commit()
    scan_ids = [scan.id for scan in scans]

    # Widen the race: pause between loading the org's assets and writing, so
    # without serialisation both imports would load none and both insert.
    start_publishing = ingestion_service._Publisher.__init__

    def slow_start(*args, **kwargs):
        start_publishing(*args, **kwargs)
        time.sleep(0.5)

    monkeypatch.setattr(ingestion_service._Publisher, "__init__", slow_start)

    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    errors: list[BaseException] = []
    phases: dict = {scan_id: [] for scan_id in scan_ids}

    def run(scan_id):
        with Session() as db:
            try:
                ingestion_service.process_import(
                    db,
                    db.get(Scan, scan_id),
                    "findings",
                    "csv",
                    FINDINGS,
                    progress=lambda phase, done, total: phases[scan_id].append(phase),
                )
            except BaseException as exc:  # surfaced below
                errors.append(exc)

    threads = [threading.Thread(target=run, args=(scan_id,)) for scan_id in scan_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    db_session.expire_all()
    assert db_session.query(Asset).filter(Asset.hostname == "web-01").count() == 1
    assert db_session.query(Finding).count() == 1  # the second import saw it as a duplicate
    reports = sorted((db_session.get(Scan, s).summary["created"], db_session.get(Scan, s).summary["duplicates"]) for s in scan_ids)
    assert reports == [(0, 1), (1, 0)]
    # The one that had to wait for the lock said so.
    assert sorted("waiting" in p for p in phases.values()) == [False, True]
