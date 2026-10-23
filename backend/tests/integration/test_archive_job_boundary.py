"""Organization lifecycle admission, including Phase 3 jobs; no provider I/O."""
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ReportStatus
from app.models.knowledge import EmbeddingProfile, KnowledgeDocument, KnowledgeIndex, KnowledgeVersion
from app.models.organization import Organization
from app.models.report import Report
from app.models.user import User
from app.services import knowledge_service as knowledge, platform, report_service
from app.services.people import PeopleError
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def fixture(db_session):
    org = Organization(name='Lifecycle boundary')
    actor = User(email='boundary-root@example.com', is_sysadmin=True)
    db_session.add_all([org, actor])
    db_session.commit()
    return org, actor


def index_job(db, org_id, status):
    profile = db.scalar(select(EmbeddingProfile).where(EmbeddingProfile.model == 'synthetic'))
    if profile is None:
        profile = EmbeddingProfile(provider='local', model='synthetic', revision='fixture', dimensions=1024)
    doc = KnowledgeDocument(org_id=org_id, title='Synthetic')
    db.add_all([profile, doc]); db.flush()
    version = KnowledgeVersion(document_id=doc.id, number=1, edition='test', source='synthetic',
        content_kind='policy', rights='synthetic', content='Require MFA', content_hash='a' * 64)
    db.add(version); db.flush()
    job = KnowledgeIndex(version_id=version.id, profile_id=profile.id, status=status, publish_version=True)
    db.add(job); db.flush()
    return job


@pytest.mark.parametrize('kind', ['report', 'index'])
@pytest.mark.parametrize('state', ['pending', 'running'])
def test_active_phase3_jobs_prevent_archive(db_session, fixture, kind, state):
    org, actor = fixture
    if kind == 'report':
        db_session.add(Report(org_id=org.id, title='Synthetic', status=ReportStatus(state)))
    else:
        index_job(db_session, org.id, state)
    db_session.commit()
    with pytest.raises(PeopleError) as refused:
        platform.archive_org(db_session, org, actor)
    assert refused.value.code == 'jobs_running'
    assert org.archived_at is None


def test_terminal_other_org_and_shared_jobs_do_not_block(db_session, fixture):
    org, actor = fixture
    other = Organization(name='Other'); db_session.add(other); db_session.flush()
    db_session.add_all([Report(org_id=org.id, title='Done', status=ReportStatus.completed),
                        Report(org_id=other.id, title='Other', status=ReportStatus.pending)])
    index_job(db_session, org.id, 'ready')
    index_job(db_session, None, 'running')
    db_session.commit()
    platform.archive_org(db_session, org, actor)
    assert org.archived_at is not None


@pytest.mark.parametrize('purging', [False, True])
def test_report_worker_fails_closed_for_inactive_org(db_session, fixture, monkeypatch, purging):
    org, actor = fixture
    org.archived_at = platform._now()
    if purging:
        org.purge_requested_at = platform._now()
    report = Report(org_id=org.id, title='Legacy queued', status=ReportStatus.pending)
    db_session.add(report); db_session.commit()
    def forbidden(**kwargs):
        pytest.fail('Inactive org must not invoke report generation')
    monkeypatch.setattr(report_service, 'generate_ai_audit_snapshot', forbidden)
    with pytest.raises(knowledge.KnowledgeError, match='Organization'):
        report_service.process_report_job(db_session, report.id)
    db_session.refresh(report)
    assert report.status == ReportStatus.failed


def test_index_worker_and_new_admission_fail_closed(db_session, fixture, monkeypatch):
    org, actor = fixture
    job = index_job(db_session, org.id, 'running')
    org.archived_at = platform._now(); db_session.commit()
    monkeypatch.setattr(knowledge.embeddings, 'embed', lambda *a: pytest.fail('No embedding I/O'))
    with pytest.raises(knowledge.KnowledgeError, match='Organization'):
        knowledge.process_index(db_session, job.id)
    db_session.refresh(job)
    assert job.status == 'failed'
    with pytest.raises(knowledge.KnowledgeError, match='Organization'):
        report_service.queue_report_generation(db_session, org.id, 'Refused')
    with pytest.raises(knowledge.KnowledgeError, match='Organization'):
        knowledge.queue_version(db_session, org_id=org.id, actor_id=actor.id, title='Refused',
            framework=None, edition='fixture', source='synthetic', content_kind='policy',
            rights='synthetic', content='Require MFA')
    with pytest.raises(knowledge.KnowledgeError, match='Organization'):
        knowledge.queue_reindex(db_session, db_session.get(EmbeddingProfile, job.profile_id), org.id, actor.id)
    with pytest.raises(knowledge.KnowledgeError, match='Organization'):
        knowledge.queue_reactivation(db_session, db_session.get(KnowledgeVersion, job.version_id), actor.id)


def test_archive_wins_admission_rechecks_after_wait(db_session, fixture):
    org, actor = fixture
    org_id = org.id
    ready, attempt = threading.Event(), threading.Event()
    def admit():
        with Session(db_session.get_bind()) as db:
            cached = db.get(Organization, org_id)  # keep stale state in the identity map
            assert cached.archived_at is None
            ready.set(); assert attempt.wait(5)
            try:
                knowledge.require_active_org(db, org_id, lock=True)
                return 'admitted'
            except knowledge.KnowledgeError:
                return 'refused'
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(admit)
        assert ready.wait(5)
        platform.archive_org(db_session, org, actor)
        attempt.set()
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        db_session.commit()
        assert future.result(timeout=5) == 'refused'


def test_admission_wins_archive_sees_committed_job(db_session, fixture):
    org, actor = fixture
    org_id, actor_id = org.id, actor.id
    knowledge.require_active_org(db_session, org_id, lock=True)
    db_session.add(Report(org_id=org_id, title='Admitted', status=ReportStatus.pending))
    db_session.flush()
    started = threading.Event()
    def archive():
        with Session(db_session.get_bind()) as db:
            candidate, root = db.get(Organization, org_id), db.get(User, actor_id)
            started.set()
            try:
                platform.archive_org(db, candidate, root)
                db.commit()
                return 'archived'
            except PeopleError as exc:
                db.rollback()
                return exc.code
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(archive)
        assert started.wait(5)
        with pytest.raises(TimeoutError):
            future.result(timeout=0.2)
        db_session.commit()
        assert future.result(timeout=5) == 'jobs_running'
