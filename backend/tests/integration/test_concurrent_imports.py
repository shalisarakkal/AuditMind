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

    # Widen the race: pause between looking a host up and creating it, so
    # without serialisation both imports would miss and both insert.
    find_asset = ingestion_service._find_asset

    def slow_find_asset(*args, **kwargs):
        match = find_asset(*args, **kwargs)
        time.sleep(0.5)
        return match

    monkeypatch.setattr(ingestion_service, "_find_asset", slow_find_asset)

    Session = sessionmaker(bind=db_session.get_bind(), autoflush=False)
    errors: list[BaseException] = []

    def run(scan_id):
        with Session() as db:
            try:
                ingestion_service.process_import(db, db.get(Scan, scan_id), "findings", "csv", FINDINGS)
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
