"""Independent PostgreSQL sessions, not shared TestClient-session concurrency."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.documents import ConsentChange, set_consent
from app.api.routes.orgs import update_ingestion_settings, update_security_settings
from app.models.enums import UserRole
from app.models.knowledge import KnowledgeConsent
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.org_settings import IngestionSettingsUpdate
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def organization(db_session):
    org = Organization(name="Concurrent synthetic organization")
    users = [User(email=f"concurrent-{i}@example.test", name=f"Admin {i}") for i in range(2)]
    db_session.add_all([org, *users]); db_session.flush()
    db_session.add_all([OrgMembership(org_id=org.id, user_id=user.id, role=UserRole.admin) for user in users])
    db_session.commit()
    return org.id, [user.id for user in users]


@pytest.mark.parametrize("security", [False, True])
def test_cached_settings_preserve_another_admins_omitted_fields(db_session, organization, security):
    org_id, actors = organization
    engine = db_session.get_bind()
    with Session(engine) as first, Session(engine) as stale:
        # Authorization has already populated both identity maps before either PATCH.
        cached = [session.get(Organization, org_id) for session in (first, stale)]
        members = [session.get(OrgMembership, (actor, org_id)) for session, actor in zip((first, stale), actors)]
        if security:
            update_security_settings(org_id, {"idle_minutes": 120}, first, members[0])
            update_security_settings(org_id, {"max_session_days": 3}, stale, members[1])
        else:
            update_ingestion_settings(org_id, IngestionSettingsUpdate(asset_existing_strategy="skip"), first, members[0])
            update_ingestion_settings(org_id, IngestionSettingsUpdate(import_partial_success=False), stale, members[1])
        assert len(cached) == 2  # Keep cached objects alive throughout the requests.
    db_session.expire_all()
    org = db_session.get(Organization, org_id)
    if security:
        assert org.security_settings == {"idle_minutes": 120, "max_session_days": 3}
    else:
        assert org.ingestion_overrides == {"asset_existing_strategy": "skip", "import_partial_success": False}


def test_two_admins_create_one_consent_record(db_session, organization, monkeypatch):
    from app.services import knowledge_service
    org_id, actors = organization
    monkeypatch.setattr(knowledge_service, "report_target", lambda: "synthetic-provider/model")
    barrier = Barrier(2)
    engine = db_session.get_bind()
    def approve(actor):
        with Session(engine) as db:
            membership = db.get(OrgMembership, (actor, org_id))
            barrier.wait(timeout=10)
            return set_consent(org_id, ConsentChange(purpose="report", granted=True,
                target="synthetic-provider/model"), db, membership)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(approve, actors)) == [{"ok": True}, {"ok": True}]
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(KnowledgeConsent)) == 1
    assert db_session.get(KnowledgeConsent, (org_id, "report")).granted is True


def test_parallel_settings_patches_merge_different_fields(db_session, organization):
    org_id, actors = organization
    barrier = Barrier(2)
    engine = db_session.get_bind()
    patches = [IngestionSettingsUpdate(asset_existing_strategy="skip"),
               IngestionSettingsUpdate(import_partial_success=False)]
    def patch(index):
        with Session(engine) as db:
            cached = db.get(Organization, org_id)
            membership = db.get(OrgMembership, (actors[index], org_id))
            barrier.wait(timeout=10)
            result = update_ingestion_settings(org_id, patches[index], db, membership)
            assert cached.id == org_id
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(patch, range(2)))
    db_session.expire_all()
    assert db_session.get(Organization, org_id).ingestion_overrides == {
        "asset_existing_strategy": "skip", "import_partial_success": False}


def test_profile_partial_update_refreshes_cached_parts(db_session, organization):
    from uuid import UUID
    from app.api.routes.import_profiles import create_import_profile, update_import_profile
    from app.models.import_profile import ImportProfile
    from app.schemas.import_profile import ImportProfileCreate, ImportProfileUpdate
    org_id, actors = organization
    member = db_session.get(OrgMembership, (actors[0], org_id))
    created = create_import_profile(org_id, ImportProfileCreate(name="Synthetic EDR",
        copy_from="endpoint_agent"), db_session, member)
    profile_id = UUID(created.key)
    engine = db_session.get_bind()
    with Session(engine) as first, Session(engine) as stale:
        cached = stale.get(ImportProfile, profile_id)
        update_import_profile(org_id, created.key, ImportProfileUpdate(column_map={"hostname": "Host"}),
            first, first.get(OrgMembership, (actors[0], org_id)))
        result = update_import_profile(org_id, created.key, ImportProfileUpdate(params={"stale_after_days": 30}),
            stale, stale.get(OrgMembership, (actors[1], org_id)))
        assert result.column_map == {"hostname": "Host"}
        assert result.params["stale_after_days"] == 30
        assert cached.column_map == {"hostname": "Host"}


def test_concurrent_case_insensitive_profile_names_return_conflict(db_session, organization):
    from fastapi import HTTPException
    from app.api.routes.import_profiles import create_import_profile
    from app.models.import_profile import ImportProfile
    from app.schemas.import_profile import ImportProfileCreate
    org_id, actors = organization
    barrier = Barrier(2)
    engine = db_session.get_bind()
    def create(index):
        with Session(engine) as db:
            membership = db.get(OrgMembership, (actors[index], org_id))
            barrier.wait(timeout=10)
            try:
                create_import_profile(org_id, ImportProfileCreate(
                    name=["Synthetic EDR", "synthetic edr"][index], copy_from="endpoint_agent"), db, membership)
                return 201
            except HTTPException as error:
                db.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == [201, 409]
    assert db_session.scalar(select(func.count()).select_from(ImportProfile)) == 1


def test_distinct_admins_cannot_silently_overwrite_one_workflow(db_session, organization):
    from fastapi import HTTPException
    from app.models.finding import Finding
    from app.models.finding_history import FindingHistory
    from app.schemas.finding_workflow import WorkflowPatch, WorkflowTarget
    from app.services.finding_workflow import update_workflows
    org_id, actors = organization
    finding = Finding(org_id=org_id, domain="network_config", severity="high", source="manual")
    db_session.add(finding); db_session.commit()
    finding_id = finding.id
    barrier = Barrier(2)
    engine = db_session.get_bind()
    def edit(index):
        with Session(engine) as db:
            membership = db.get(OrgMembership, (actors[index], org_id))
            barrier.wait(timeout=10)
            try:
                update_workflows(db, org_id, membership,
                    [WorkflowTarget(finding_id=finding_id, expected_version=0)],
                    WorkflowPatch(rationale=f"Synthetic admin {index} edit"))
                return 200, actors[index]
            except HTTPException as error:
                db.rollback()
                return error.status_code, actors[index]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, range(2)))
    assert sorted(status for status, _ in results) == [200, 409]
    winner = next(actor for status, actor in results if status == 200)
    history = db_session.scalars(select(FindingHistory).where(FindingHistory.finding_id == finding_id)).all()
    assert len(history) == 1
    assert history[0].actor_id == winner
