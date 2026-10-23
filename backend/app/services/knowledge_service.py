"""Knowledge publication, consent, retrieval, and version lifecycle."""

import hashlib
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.assessment_contract import REPORT_PROMPT_VERSION
from app.models.enums import ReportStatus
from app.models.knowledge import (
    EmbeddingProfile, KnowledgeChunk, KnowledgeConsent, KnowledgeDocument,
    KnowledgeIndex, KnowledgeVersion, ReportEvidenceUse, utcnow,
)
from app.models.organization import Organization
from app.models.report import Report
from app.models.session import PlatformSetting
from app.services import knowledge_embeddings as embeddings


class KnowledgeError(ValueError):
    pass


def require_active_org(db: Session, org_id: uuid.UUID | None, *, lock: bool = False) -> None:
    """Job admission shares the org row lock; archive takes an exclusive lock.

    Re-read state after waiting: the caller's identity map may predate an archive.
    Shared standards have no organization lifecycle.
    """
    if org_id is None:
        return
    query = select(Organization.archived_at, Organization.purge_requested_at).where(Organization.id == org_id)
    if lock:
        query = query.with_for_update(read=True)
    state = db.execute(query).first()
    if state is None or state.archived_at or state.purge_requested_at:
        raise KnowledgeError("Organization is archived, being removed, or unavailable")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def local_profile(db: Session) -> EmbeddingProfile:
    profile = db.scalar(select(EmbeddingProfile).where(
        EmbeddingProfile.provider == "local", EmbeddingProfile.model == embeddings.LOCAL_MODEL,
        EmbeddingProfile.revision == embeddings.LOCAL_REVISION, EmbeddingProfile.dimensions == 1024,
    ))
    if profile is None:
        # Serialize first-time setup across web and worker processes.
        db.execute(select(func.pg_advisory_xact_lock(6, 1)))
        profile = db.scalar(select(EmbeddingProfile).where(EmbeddingProfile.provider == "local",
            EmbeddingProfile.model == embeddings.LOCAL_MODEL, EmbeddingProfile.revision == embeddings.LOCAL_REVISION))
        if profile is None:
            profile = EmbeddingProfile(provider="local", model=embeddings.LOCAL_MODEL,
                                       revision=embeddings.LOCAL_REVISION, dimensions=1024)
            db.add(profile)
            db.flush()
    return profile


def consent_target(profile: EmbeddingProfile) -> str:
    return f"{profile.provider}:{profile.model}:{profile.revision}:{profile.dimensions}"


def report_target() -> str:
    from app.services.report_provider import target
    from app.core.assessment_contract import active_prompt_version
    return target(active_prompt_version())


def consented(db: Session, org_id: uuid.UUID, purpose: str, target: str) -> bool:
    consent = db.get(KnowledgeConsent, (org_id, purpose), populate_existing=True)
    return bool(consent and consent.granted and consent.target == target)


def require_report_consent(db: Session, org_id: uuid.UUID) -> None:
    require_active_org(db, org_id)
    if not consented(db, org_id, "report", report_target()):
        raise KnowledgeError("An organization admin must approve external AI report processing in Documents settings")


def configured_profile(db: Session) -> EmbeddingProfile:
    setting = db.get(PlatformSetting, "knowledge_embedding_profile", populate_existing=True)
    profile = None
    if setting and setting.value.get("id"):
        profile = db.get(EmbeddingProfile, uuid.UUID(setting.value["id"]))
    return profile or local_profile(db)


def requested_profile(db: Session, org_id: uuid.UUID | None) -> EmbeddingProfile:
    profile = configured_profile(db)
    if profile.provider == "local" or org_id is None or consented(db, org_id, "embedding", consent_target(profile)):
        return profile
    return local_profile(db)


def selected_profile(db: Session, org_id: uuid.UUID | None) -> EmbeddingProfile:
    profile = requested_profile(db, org_id)
    if profile.provider == "local":
        return profile
    ready = select(KnowledgeIndex.id).where(KnowledgeIndex.version_id == KnowledgeVersion.id,
        KnowledgeIndex.profile_id == profile.id, KnowledgeIndex.status == "ready").exists()
    missing = db.scalar(select(KnowledgeVersion.id).join(KnowledgeDocument).where(
        KnowledgeVersion.current.is_(True), KnowledgeVersion.retired_at.is_(None),
        KnowledgeVersion.content_kind != "reference",
        or_(KnowledgeDocument.org_id.is_(None), KnowledgeDocument.org_id == org_id), ~ready).limit(1))
    # A staged profile is never used until every current permitted source is ready.
    return local_profile(db) if missing else profile


def queue_reindex(db: Session, profile: EmbeddingProfile, org_id: uuid.UUID | None, actor_id: uuid.UUID) -> None:
    require_active_org(db, org_id, lock=True)
    scope = KnowledgeDocument.org_id.is_(None) if org_id is None else KnowledgeDocument.org_id == org_id
    for version in db.scalars(select(KnowledgeVersion).join(KnowledgeDocument).where(
            scope, KnowledgeVersion.current.is_(True), KnowledgeVersion.retired_at.is_(None))):
        index = db.scalar(select(KnowledgeIndex).where(KnowledgeIndex.version_id == version.id,
                                                      KnowledgeIndex.profile_id == profile.id))
        if index is None:
            db.add(KnowledgeIndex(version_id=version.id, profile_id=profile.id, started_by=actor_id))
        elif index.status == "failed":
            index.status, index.retry_count, index.error_message = "pending", 0, None


def require_embedding_consent(db: Session, org_id: uuid.UUID | None, profile: EmbeddingProfile) -> None:
    if profile.provider == "local":
        return
    live_bind = db.info.get("evidence_capture_live_bind")
    if live_bind is not None:
        # Evidence is historical within its MVCC snapshot; authorization is not.
        with Session(live_bind.execution_options(isolation_level="READ COMMITTED")) as live:
            if configured_profile(live).id != profile.id:
                raise KnowledgeError("Embedding profile changed during evidence capture; retry generation")
            require_embedding_consent(live, org_id, profile)
        return
    if org_id is None:
        selected = configured_profile(db)
        if selected.id != profile.id:
            raise KnowledgeError("Shared external embedding profile is no longer enabled")
    elif not consented(db, org_id, "embedding", consent_target(profile)):
        raise KnowledgeError("External embedding consent is missing or revoked")


def queue_version(db: Session, *, org_id: uuid.UUID | None, actor_id: uuid.UUID,
                  title: str, framework: str | None, edition: str, source: str,
                  content_kind: str, rights: str, content: str,
                  document_id: uuid.UUID | None = None) -> KnowledgeVersion:
    require_active_org(db, org_id, lock=True)
    if not content.strip():
        raise KnowledgeError("Document contains no text")
    if document_id:
        document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id).with_for_update())
        if document is None or document.org_id != org_id:
            raise KnowledgeError("Document not found")
        document.title = title
        document.framework = framework
        existing = db.scalar(select(KnowledgeVersion).where(KnowledgeVersion.document_id == document_id,
            KnowledgeVersion.content_hash == digest(content), KnowledgeVersion.edition == edition,
            KnowledgeVersion.purged_at.is_(None)))
        if existing:
            return existing
    else:
        document = KnowledgeDocument(org_id=org_id, title=title, framework=framework)
        db.add(document)
        db.flush()
    number = (db.scalar(select(func.max(KnowledgeVersion.number)).where(KnowledgeVersion.document_id == document.id)) or 0) + 1
    version = KnowledgeVersion(document_id=document.id, number=number, edition=edition, source=source,
        content_kind=content_kind, rights=rights, content=content, content_hash=digest(content))
    db.add(version)
    db.flush()
    profile = requested_profile(db, org_id)
    # Publish locally first so revocation always retains a usable local index.
    local = local_profile(db)
    db.add(KnowledgeIndex(version_id=version.id, profile_id=local.id, publish_version=True, started_by=actor_id))
    if profile.id != local.id:
        db.add(KnowledgeIndex(version_id=version.id, profile_id=profile.id, started_by=actor_id))
    return version


def process_index(db: Session, index_id: uuid.UUID) -> None:
    job = db.get(KnowledgeIndex, index_id)
    if job is None or job.status != "running":
        return
    try:
        version = db.get(KnowledgeVersion, job.version_id)
        document = db.get(KnowledgeDocument, version.document_id)
        profile = db.get(EmbeddingProfile, job.profile_id)
        if version.purged_at or (version.retired_at and not job.publish_version) or not version.content:
            raise KnowledgeError("Document version is retired or removed")
        if document.org_id:
            org = db.get(Organization, document.org_id)
            if org.archived_at or org.purge_requested_at:
                raise KnowledgeError("Organization is archived or being removed")
        require_embedding_consent(db, document.org_id, profile)
        parts = [] if version.content_kind == "reference" else embeddings.chunk_text(version.content)
        version_id, document_id, org_id = version.id, document.id, document.org_id
        # No transaction is held while a model runs or a network request is issued.
        db.expunge(profile)
        db.commit()
        vectors = []
        for offset in range(0, len(parts), 8):
            require_active_org(db, org_id)
            require_embedding_consent(db, org_id, profile)
            db.commit()
            vectors.extend(embeddings.embed(profile, [part[2] for part in parts[offset:offset + 8]]))
        require_active_org(db, org_id, lock=True)
        document = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id).with_for_update())
        version = db.get(KnowledgeVersion, version_id, populate_existing=True, with_for_update=True)
        job = db.get(KnowledgeIndex, index_id, populate_existing=True, with_for_update=True)
        if not document or not version or (version.retired_at and not job.publish_version) or version.purged_at or job.status != "running":
            raise KnowledgeError("Document changed while indexing")
        require_embedding_consent(db, org_id, profile)
        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.index_id == index_id))
        for ordinal, ((start, end, content), vector) in enumerate(zip(parts, vectors)):
            db.add(KnowledgeChunk(index_id=index_id, ordinal=ordinal, start_offset=start, end_offset=end,
                content=content, content_hash=digest(content), embedding=vector))
        if job.publish_version:
            newer = db.scalar(select(KnowledgeVersion.id).where(KnowledgeVersion.document_id == document_id,
                KnowledgeVersion.current.is_(True), KnowledgeVersion.number > version.number))
            if newer:
                raise KnowledgeError("A newer version is already published")
            for old in db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.document_id == document_id,
                                                                 KnowledgeVersion.current.is_(True))):
                old.current = False
                old.retired_at = utcnow()
            version.current = True
            version.retired_at = None
        job.status = "ready"
        job.error_message = None
        db.commit()
    except Exception:
        db.rollback()
        job = db.get(KnowledgeIndex, index_id, populate_existing=True)
        if job:
            job.status = "failed"
            # Provider exception strings can contain request data; never expose them.
            job.error_message = "Indexing failed. Check model setup, consent, and source availability; retry after correcting the cause."
            db.commit()
        raise


def retire_version(db: Session, version: KnowledgeVersion) -> None:
    version = db.get(KnowledgeVersion, version.id, populate_existing=True, with_for_update=True)
    if version.purged_at:
        raise KnowledgeError("Version was removed")
    version.current = False
    version.retired_at = utcnow()
    for index in db.scalars(select(KnowledgeIndex).where(
            KnowledgeIndex.version_id == version.id,
            KnowledgeIndex.status.in_(["pending", "running"])).with_for_update()
            .execution_options(populate_existing=True)):
        # Running work must acknowledge retirement before purge can remove it.
        index.publish_version = False
        if index.status == "pending":
            index.status = "failed"
            index.error_message = "Indexing cancelled because the version was retired"


def queue_reactivation(db: Session, version: KnowledgeVersion, actor_id: uuid.UUID) -> None:
    document = db.get(KnowledgeDocument, version.document_id)
    require_active_org(db, document.org_id, lock=True)
    if not version.retired_at or version.purged_at or not version.content:
        raise KnowledgeError("Only retained, retired versions can be reactivated")
    newer_current = db.scalar(
        select(KnowledgeVersion.id).where(
            KnowledgeVersion.document_id == version.document_id,
            KnowledgeVersion.current.is_(True),
            KnowledgeVersion.number > version.number,
        )
    )
    if newer_current:
        raise KnowledgeError("Retire the newer current version before reactivating this version")
    profile = local_profile(db)
    index = db.scalar(
        select(KnowledgeIndex)
        .where(KnowledgeIndex.version_id == version.id, KnowledgeIndex.profile_id == profile.id)
        .with_for_update()
    )
    if index is not None and index.status in {"pending", "running"}:
        if index.publish_version:
            raise KnowledgeError("Reactivation is already queued for this version")
        if index.status == "running":
            raise KnowledgeError("This version is already being indexed")
    if index is None:
        db.add(KnowledgeIndex(
            version_id=version.id,
            profile_id=profile.id,
            publish_version=True,
            started_by=actor_id,
        ))
    else:
        index.status = "pending"
        index.publish_version = True
        index.error_message = None
        index.retry_count = 0


def purge_version(db: Session, version: KnowledgeVersion) -> None:
    version = db.get(KnowledgeVersion, version.id, populate_existing=True, with_for_update=True)
    if version.current or not version.retired_at:
        raise KnowledgeError("Only retired, non-current versions can be removed")
    used = db.scalar(select(ReportEvidenceUse.report_id).join(Report).where(
        ReportEvidenceUse.version_id == version.id, Report.status.in_([ReportStatus.pending, ReportStatus.running])))
    indexing = db.scalar(
        select(KnowledgeIndex.id).where(
            KnowledgeIndex.version_id == version.id,
            or_(
                KnowledgeIndex.status == "running",
                (KnowledgeIndex.publish_version.is_(True) & (KnowledgeIndex.status == "pending")),
            ),
        )
    )
    if used or indexing:
        raise KnowledgeError("Version is in use by an active report or indexing job")
    db.execute(delete(KnowledgeIndex).where(KnowledgeIndex.version_id == version.id))
    version.content = None
    version.purged_at = utcnow()


def retrieve(db: Session, org_id: uuid.UUID, query: str, frameworks: list[str] | None = None,
             limit: int = 8) -> list[dict]:
    if not query.strip():
        return []
    profile = selected_profile(db, org_id)
    require_embedding_consent(db, org_id, profile)
    available = db.scalar(select(KnowledgeIndex.id).join(KnowledgeVersion).join(KnowledgeDocument)
        .where(KnowledgeIndex.status == "ready", KnowledgeIndex.profile_id == profile.id,
               KnowledgeVersion.current.is_(True), KnowledgeVersion.retired_at.is_(None),
               or_(KnowledgeDocument.org_id.is_(None), KnowledgeDocument.org_id == org_id)).limit(1))
    if available is None:
        return []
    vector = embeddings.embed(profile, [query], query=True)[0]
    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    statement = (select(KnowledgeChunk, KnowledgeVersion, KnowledgeDocument, distance.label("distance"))
        .join(KnowledgeIndex, KnowledgeChunk.index_id == KnowledgeIndex.id)
        .join(KnowledgeVersion, KnowledgeIndex.version_id == KnowledgeVersion.id)
        .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
        .where(KnowledgeIndex.status == "ready", KnowledgeIndex.profile_id == profile.id,
               KnowledgeVersion.current.is_(True), KnowledgeVersion.retired_at.is_(None),
               KnowledgeVersion.purged_at.is_(None), KnowledgeVersion.content_kind != "reference",
               or_(KnowledgeDocument.org_id.is_(None), KnowledgeDocument.org_id == org_id)))
    if frameworks:
        statement = statement.where(or_(KnowledgeDocument.framework.in_(frameworks),
            (KnowledgeDocument.org_id == org_id) & KnowledgeDocument.framework.is_(None)))
    rows = db.execute(statement.order_by("distance", KnowledgeChunk.id).limit(limit)).all()
    return [{"citation_id": str(chunk.id), "document_id": str(document.id), "version_id": str(version.id),
             "chunk_id": str(chunk.id), "control_id": f"section-{chunk.ordinal + 1}",
             "framework": document.framework or "POLICY", "version": version.edition,
             "title": document.title, "content": chunk.content, "source": version.source,
             "content_ref": f"characters {chunk.start_offset}-{chunk.end_offset}",
             "content_hash": chunk.content_hash, "document_hash": version.content_hash,
             "content_kind": version.content_kind, "embedding_profile": consent_target(profile),
             "distance": float(score)} for chunk, version, document, score in rows]
