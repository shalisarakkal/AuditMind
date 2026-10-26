"""Real PostgreSQL waits with stale authorization/reference identity maps."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from threading import Event

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import authorize_org_write
from app.api.routes.findings import create_finding
from app.models.asset import Asset
from app.models.enums import ArchiveItemType, UserRole
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.finding import FindingCreate
from app.services import archive_service, platform
from app.services.org_lock import lock_org
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def inventory(db_session):
    org = Organization(name="Synthetic admission organization")
    actor = User(email="admission@example.test", name="Synthetic admin")
    db_session.add_all([org, actor]); db_session.flush()
    db_session.add(OrgMembership(org_id=org.id, user_id=actor.id, role=UserRole.admin))
    asset = Asset(org_id=org.id, type="server", hostname="synthetic-host")
    db_session.add(asset); db_session.commit()
    return org.id, actor.id, asset.id


@pytest.mark.parametrize("change,expected", [("archive", 409), ("demote", 403), ("remove", 403), ("deactivate", 403)])
def test_waiting_write_rechecks_lifecycle_and_authorization(db_session, inventory, change, expected):
    org_id, actor_id, _ = inventory
    ready, proceed = Event(), Event()
    engine = db_session.get_bind()
    def write():
        with Session(engine) as db:
            cached = db.get(OrgMembership, (actor_id, org_id))
            assert cached.role == UserRole.admin
            assert cached.organization.archived_at is None
            ready.set(); assert proceed.wait(5)
            try:
                member = authorize_org_write(db, org_id, actor_id, (UserRole.admin,))
                create_finding(org_id, FindingCreate(domain="network_config", severity="high"), db, member)
                return 201
            except HTTPException as error:
                db.rollback(); return error.status_code
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(write)
        assert ready.wait(5)
        org = db_session.get(Organization, org_id, with_for_update=True)
        member = db_session.get(OrgMembership, (actor_id, org_id))
        if change == "archive":
            org.archived_at = datetime.now(timezone.utc)
        elif change == "demote":
            member.role = UserRole.viewer
        elif change == "remove":
            db_session.delete(member)
        else:
            db_session.get(User, actor_id).is_active = False
        proceed.set()
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        db_session.commit()
        assert future.result(timeout=5) == expected
    assert db_session.scalar(select(func.count()).select_from(Finding)) == 0


def test_admitted_write_fences_organization_archive_until_commit(db_session, inventory):
    org_id, actor_id, _ = inventory
    engine = db_session.get_bind()
    authorize_org_write(db_session, org_id, actor_id, (UserRole.admin,))
    attempted = Event()
    def archive():
        with Session(engine) as db:
            org, actor = db.get(Organization, org_id), db.get(User, actor_id)
            attempted.set()
            platform.archive_org(db, org, actor)
            db.commit()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(archive)
        assert attempted.wait(5)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        db_session.commit()
        future.result(timeout=5)
    db_session.expire_all()
    assert db_session.get(Organization, org_id).archived_at is not None


def test_finding_rejects_pending_asset_archive(db_session, inventory):
    org_id, actor_id, asset_id = inventory
    archive_service.start_archive(db_session, org_id, ArchiveItemType.asset, asset_id, actor_id)
    member = authorize_org_write(db_session, org_id, actor_id, (UserRole.admin,))
    with pytest.raises(HTTPException) as refused:
        create_finding(org_id, FindingCreate(domain="network_config", severity="high", asset_id=asset_id), db_session, member)
    assert refused.value.status_code == 409


def test_finding_rejects_pending_upload_archive(db_session, inventory):
    from app.models.scan import Scan
    org_id, actor_id, _ = inventory
    scan = Scan(org_id=org_id, scan_type="findings_csv", source="upload", status="completed")
    db_session.add(scan); db_session.commit()
    scan_id = scan.id
    archive_service.start_archive(db_session, org_id, ArchiveItemType.upload, scan_id, actor_id)
    member = authorize_org_write(db_session, org_id, actor_id, (UserRole.admin,))
    with pytest.raises(HTTPException) as refused:
        create_finding(org_id, FindingCreate(domain="network_config", severity="high", scan_id=scan_id), db_session, member)
    assert refused.value.status_code == 409


def test_admission_fence_allows_worker_foreign_key_inserts(db_session, inventory):
    org_id, actor_id, _ = inventory
    authorize_org_write(db_session, org_id, actor_id, (UserRole.admin,))
    engine = db_session.get_bind()
    def publish():
        with Session(engine) as db:
            lock_org(db, org_id)
            db.add(Asset(org_id=org_id, type="server", hostname="synthetic-worker-host"))
            db.commit()
            return True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish)
        try:
            assert future.result(timeout=5) is True
        finally:
            db_session.rollback()


def test_finding_refreshes_cached_asset_after_waiting_for_archive_chunk(db_session, inventory):
    org_id, actor_id, asset_id = inventory
    ready, proceed = Event(), Event()
    engine = db_session.get_bind()
    def create():
        with Session(engine) as db:
            cached = db.get(Asset, asset_id)
            assert cached.archived_at is None
            member = authorize_org_write(db, org_id, actor_id, (UserRole.admin,))
            ready.set(); assert proceed.wait(5)
            try:
                create_finding(org_id, FindingCreate(domain="network_config", severity="high", asset_id=asset_id), db, member)
                return 201
            except HTTPException as error:
                db.rollback(); return error.status_code
    lock_org(db_session, org_id)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(create)
        assert ready.wait(5)
        db_session.get(Asset, asset_id).archived_at = datetime.now(timezone.utc)
        proceed.set()
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        db_session.commit()
        assert future.result(timeout=5) == 422
    assert db_session.scalar(select(func.count()).select_from(Finding)) == 0


def test_bulk_archive_returns_prior_jobs_and_refuses_after_demotion(db_session, inventory, monkeypatch):
    from app.api.routes.archive import BulkRequest, start_bulk
    from app.models.archive import ArchiveJob
    org_id, actor_id, _ = inventory
    findings = [Finding(org_id=org_id, domain="network_config", severity="high", source="manual") for _ in range(2)]
    db_session.add_all(findings); db_session.commit()
    ids = [finding.id for finding in findings]
    original = archive_service.start_archive
    engine = db_session.get_bind()
    def start(*args):
        job = original(*args)
        with Session(engine) as other:
            other.get(OrgMembership, (actor_id, org_id)).role = UserRole.viewer
            other.commit()
        return job
    monkeypatch.setattr(archive_service, "start_archive", start)
    result = start_bulk(org_id, BulkRequest(action="archive", item_type="finding", ids=ids),
        db_session, db_session.get(OrgMembership, (actor_id, org_id)))
    assert len(result.jobs) == 1
    assert [refused.id for refused in result.refused] == [ids[1]]
    assert db_session.scalar(select(func.count()).select_from(ArchiveJob)) == 1
