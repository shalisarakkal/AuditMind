"""MVCC concurrency regressions. All writers use independent test DB sessions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import Domain, ReportStatus, Severity
from app.models.finding import Finding
from app.models.organization import Organization
from app.models.report import Report
from app.models.knowledge import (EmbeddingProfile, KnowledgeConsent, KnowledgeDocument,
    KnowledgeVersion, KnowledgeIndex, KnowledgeChunk, ReportEvidenceUse)
from app.models.session import PlatformSetting
from app.schemas.report_ai import AuditReportSnapshot, DomainScoreAI
from app.services import knowledge_service as knowledge, report_ai_service as reports
from tests.conftest import requires_db

pytestmark = requires_db


@pytest.fixture
def evidence(db_session):
    org = Organization(name="Snapshot fixture")
    db_session.add(org)
    db_session.flush()
    asset = Asset(org_id=org.id, type="server", hostname="before")
    db_session.add(asset)
    db_session.flush()
    finding = Finding(org_id=org.id, asset_id=asset.id, domain=Domain.identity_access,
        severity=Severity.high, description="Before")
    report = Report(org_id=org.id, title="Snapshot", status=ReportStatus.running)
    profile = knowledge.local_profile(db_session)
    document = KnowledgeDocument(org_id=org.id, title="Before policy", framework="NIST")
    db_session.add_all([finding, report, document])
    db_session.flush()
    version = KnowledgeVersion(document_id=document.id, number=1, edition="1", source="Before source",
        content_kind="organization_policy", rights="Synthetic", content="Before policy",
        content_hash=knowledge.digest("Before policy"), current=True)
    db_session.add(version)
    db_session.flush()
    index = KnowledgeIndex(version_id=version.id, profile_id=profile.id, status="ready")
    db_session.add(index)
    db_session.flush()
    db_session.add(KnowledgeChunk(index_id=index.id, ordinal=0, start_offset=0, end_offset=13,
        content="Before policy", content_hash=knowledge.digest("Before policy"), embedding=[1.] + [0.] * 1023))
    ids = dict(org=org.id, asset=asset.id, finding=finding.id, report=report.id,
        profile=profile.id, document=document.id, version=version.id)
    db_session.commit()
    return ids


@pytest.mark.parametrize("operation", ["insert", "archive", "update", "delete"])
def test_counts_samples_inventory_and_rule_scores_share_one_view(db_session, evidence, monkeypatch, operation):
    engine = db_session.get_bind()
    read_counts, wrote = Event(), Event()
    monkeypatch.setattr(reports, "retrieve_standards_for_findings", lambda *a, **kw: [])
    def writer():
        assert read_counts.wait(15), "Reader did not reach severity counts"
        try:
            with Session(engine) as db, db.begin():
                if operation == "insert":
                    db.add(Asset(org_id=evidence["org"], type="database", hostname="after"))
                    db.add(Finding(org_id=evidence["org"], domain=Domain.identity_access,
                        severity=Severity.critical, description="After"))
                elif operation == "archive":
                    now = datetime.now(timezone.utc)
                    db.execute(update(Finding).where(Finding.id == evidence["finding"]).values(archived_at=now))
                    db.execute(update(Asset).where(Asset.id == evidence["asset"]).values(archived_at=now))
                elif operation == "update":
                    db.execute(update(Finding).where(Finding.id == evidence["finding"]).values(
                        severity=Severity.critical, description="After"))
                else:
                    db.execute(delete(Finding).where(Finding.id == evidence["finding"]))
        finally:
            wrote.set()
    def pause(connection, cursor, statement, parameters, context, executemany):
        if "GROUP BY findings.severity" in statement and not read_counts.is_set():
            assert connection.get_isolation_level() == "REPEATABLE READ"
            read_counts.set()
            assert wrote.wait(15), "Concurrent commit timed out"
    event.listen(engine, "after_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            context = reports._gather_org_audit_context(db_session, evidence["org"])
            future.result(timeout=15)
    finally:
        event.remove(engine, "after_cursor_execute", pause)
    assert context["total_assets"] == 1 and context["assets_by_category"] == {"server": 1}
    assert context["total_findings"] == 1 and context["findings_by_severity"] == {"high": 1}
    assert context["sample_findings"][0]["description"] == "Before"
    assert context["sample_findings"][0]["severity"] == "high"
    assert context["rule_based"]["domains"]["identity_access"]["score"] == 93
    assert context["captured_at"] == context["evidence_capture"]["started_at"]
    assert context["evidence_capture"]["isolation_level"] == "REPEATABLE READ"
    assert not db_session.in_transaction()
    with Session(engine) as db:
        assert db.connection().get_isolation_level() == "READ COMMITTED"
        live = db.get(Finding, evidence["finding"])
        if operation == "update":
            assert live.severity == Severity.critical
        elif operation == "delete":
            assert live is None
        elif operation == "archive":
            assert live.archived_at is not None
        else:
            assert db.scalar(select(func.count()).select_from(Finding)) == 2


def test_document_publication_conflict_retries_the_entire_capture(db_session, evidence, monkeypatch):
    engine = db_session.get_bind()
    monkeypatch.setattr(knowledge.embeddings, "embed", lambda *a, **kw: [[1.] + [0.] * 1023])
    changed = []
    reads = []
    original = reports._read_org_audit_context
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        reads.append(result)
        return result
    monkeypatch.setattr(reports, "_read_org_audit_context", read)
    def publish(connection, cursor, statement, parameters, context, executemany):
        if "<=>" not in statement or changed:
            return
        changed.append(True)
        with Session(engine) as db, db.begin():
            old = db.get(KnowledgeVersion, evidence["version"])
            old.current, old.retired_at = False, datetime.now(timezone.utc)
            db.get(KnowledgeDocument, evidence["document"]).title = "After policy"
            db.get(Finding, evidence["finding"]).severity = Severity.critical
            version = KnowledgeVersion(document_id=evidence["document"], number=2, edition="2",
                source="After source", content_kind="organization_policy", rights="Synthetic",
                content="After policy", content_hash=knowledge.digest("After policy"), current=True)
            db.add(version)
            db.flush()
            changed.append(version.id)
            index = KnowledgeIndex(version_id=version.id, profile_id=evidence["profile"], status="ready")
            db.add(index)
            db.flush()
            db.add(KnowledgeChunk(index_id=index.id, ordinal=0, start_offset=0, end_offset=12,
                content="After policy", content_hash=knowledge.digest("After policy"), embedding=[1.] + [0.] * 1023))
    event.listen(engine, "after_cursor_execute", publish)
    try:
        context = reports._gather_org_audit_context(db_session, evidence["org"], report_id=evidence["report"])
    finally:
        event.remove(engine, "after_cursor_execute", publish)
    assert len(reads) == 2
    assert context["evidence_capture"]["attempts"] == 2
    assert reads[0]["findings_by_severity"] == {"high": 1}
    assert {row["content"] for row in reads[0]["citations"]} == {"Before policy"}
    assert context["findings_by_severity"] == {"critical": 1}
    assert context["rule_based"]["domains"]["identity_access"]["score"] == 85
    assert {row["content"] for row in context["citations"]} == {"After policy"}
    assert {row["source"] for row in context["citations"]} == {"After source"}
    assert {row["title"] for row in context["citations"]} == {"After policy"}
    with Session(engine) as db:
        assert db.get(ReportEvidenceUse, (evidence["report"], evidence["version"])) is None
        assert db.get(ReportEvidenceUse, (evidence["report"], changed[1])) is not None


def test_source_pins_commit_and_locks_release_before_provider(db_session, evidence, monkeypatch):
    engine = db_session.get_bind()
    monkeypatch.setattr(reports.settings, "ANTHROPIC_API_KEY", "synthetic")
    monkeypatch.setattr(knowledge, "require_report_consent", lambda *a: None)
    monkeypatch.setattr(knowledge.embeddings, "embed", lambda *a, **kw: [[1.] + [0.] * 1023])
    def provider(*args, **kwargs):
        assert not db_session.in_transaction()
        with Session(engine) as db:
            assert db.get(ReportEvidenceUse, (evidence["report"], evidence["version"])) is not None
            version = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.id == evidence["version"])
                .with_for_update(nowait=True))
            knowledge.retire_version(db, version)
            with pytest.raises(knowledge.KnowledgeError, match="active report"):
                knowledge.purge_version(db, version)
            db.commit()
        return AuditReportSnapshot(title="Synthetic", executive_summary="Evidence", resilience_summary="Evidence",
            overall_score=80, overall_tier="low", domains=[DomainScoreAI(domain=d, score=80,
                tier="low", justification="Evidence") for d in Domain], remediations=[])
    monkeypatch.setattr(reports, "ask_claude_structured", provider)
    result = reports.generate_ai_audit_snapshot(db_session, evidence["org"], "Synthetic", report_id=evidence["report"])
    assert result.provenance["evidence_capture"]["isolation_level"] == "REPEATABLE READ"
    assert result.provenance["inventory"] == {"total_assets": 1, "assets_by_category": {"server": 1}}
    assert {row["content"] for row in result.compliance_citations} == {"Before policy"}


def test_failed_capture_rolls_back_all_source_pins(db_session, evidence, monkeypatch):
    first, second = UUID(int=1), UUID(int=2)
    for number, key in enumerate((first, second), start=2):
        db_session.add(KnowledgeVersion(id=key, document_id=evidence["document"], number=number,
            edition="Synthetic", source="Synthetic", rights="Synthetic", content_kind="organization_policy",
            content="Synthetic", content_hash="synthetic", current=key == first,
            retired_at=None if key == first else datetime.now(timezone.utc)))
    db_session.commit()
    monkeypatch.setattr(reports, "_read_org_audit_context", lambda *a: {
        "citations": [{"version_id": str(first)}, {"version_id": str(second)}]})
    with pytest.raises(ValueError, match="Retrieved evidence changed"):
        reports._gather_org_audit_context(db_session, evidence["org"], report_id=evidence["report"])
    assert db_session.scalar(select(func.count()).select_from(ReportEvidenceUse)) == 0


@pytest.mark.parametrize("state,attempts", [("40001",3),("40P01",3),("08006",1)])
def test_capture_conflicts_are_bounded_and_fail_closed(db_session, evidence, monkeypatch, state, attempts):
    calls = []
    def fail(*args):
        calls.append(True)
        error = Exception("Synthetic database failure")
        error.sqlstate = state
        raise DBAPIError("Synthetic", {}, error)
    monkeypatch.setattr(reports, "_read_org_audit_context", fail)
    with pytest.raises(ValueError, match="consistent report evidence"):
        reports._gather_org_audit_context(db_session, evidence["org"], report_id=evidence["report"])
    assert len(calls) == attempts
    assert db_session.scalar(select(func.count()).select_from(ReportEvidenceUse)) == 0


@pytest.mark.parametrize("change", ["revoke", "switch"])
def test_snapshot_does_not_freeze_external_embedding_authorization(db_session, evidence, change):
    engine = db_session.get_bind()
    profile = EmbeddingProfile(provider="openai", model="synthetic", revision="pinned", dimensions=2)
    db_session.add(profile)
    db_session.flush()
    profile_id = profile.id
    db_session.add_all([
        PlatformSetting(key="knowledge_embedding_profile", value={"id": str(profile_id)}),
        KnowledgeConsent(org_id=evidence["org"], purpose="embedding", target=knowledge.consent_target(profile), granted=True),
    ])
    db_session.commit()
    with Session(engine.execution_options(isolation_level="REPEATABLE READ")) as capture:
        capture.info["evidence_capture_live_bind"] = engine
        target = capture.get(EmbeddingProfile, profile_id)
        assert knowledge.consented(capture, evidence["org"], "embedding", knowledge.consent_target(target))
        with Session(engine) as writer, writer.begin():
            if change == "revoke":
                writer.get(KnowledgeConsent, (evidence["org"], "embedding")).granted = False
            else:
                writer.get(PlatformSetting, "knowledge_embedding_profile").value = {}
        # The historical evidence view still sees old approval, but the external
        # transmission guard must consult current authorization independently.
        assert knowledge.consented(capture, evidence["org"], "embedding", knowledge.consent_target(target))
        with pytest.raises(knowledge.KnowledgeError, match="revoked|changed"):
            knowledge.require_embedding_consent(capture, evidence["org"], target)


@pytest.mark.parametrize("pending", ["new", "dirty", "deleted"])
def test_capture_does_not_commit_or_discard_caller_changes(db_session, evidence, pending):
    if pending == "new":
        db_session.add(Asset(org_id=evidence["org"], type="server", hostname="Uncommitted"))
    elif pending == "dirty":
        db_session.get(Asset, evidence["asset"]).hostname = "Uncommitted"
    else:
        db_session.delete(db_session.get(Finding, evidence["finding"]))
    with pytest.raises(ValueError, match="Commit pending changes"):
        reports._gather_org_audit_context(db_session, evidence["org"])
    assert getattr(db_session, pending)
    with Session(db_session.get_bind()) as observer:
        assert observer.scalar(select(func.count()).select_from(Asset)) == 1
        assert observer.get(Asset, evidence["asset"]).hostname == "before"
        assert observer.get(Finding, evidence["finding"]) is not None


def test_report_source_registration_cannot_cross_organization(db_session, evidence):
    other = Organization(name="Other organization")
    db_session.add(other)
    db_session.flush()
    other_id = other.id
    db_session.commit()
    with pytest.raises(ValueError, match="evidence organization"):
        reports._gather_org_audit_context(db_session, other_id, report_id=evidence["report"])
    assert db_session.scalar(select(func.count()).select_from(ReportEvidenceUse)) == 0
