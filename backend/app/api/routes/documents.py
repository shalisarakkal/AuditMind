"""Organization knowledge sources, explicit consent, and platform library management."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role, require_sysadmin
from app.api.paging import DateRange, PageParams, SortOrder, any_of, contains, date_range, one_of, ordered, page_params
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.knowledge import EmbeddingProfile, KnowledgeConsent, KnowledgeDocument, KnowledgeIndex, KnowledgeVersion, utcnow
from app.models.membership import OrgMembership
from app.models.session import PlatformSetting
from app.models.user import User
from app.services import knowledge_service as service
from app.services.events import record_event
from app.services.org_lock import lock_org_configuration

router = APIRouter(tags=["documents"])
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024


class ConsentChange(BaseModel):
    purpose: Literal["embedding", "report"]
    granted: bool
    target: str = Field(min_length=1, max_length=500)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1200)
    frameworks: list[Literal["CIS", "NIST", "ISO"]] | None = None


class ProfileRequest(BaseModel):
    provider: Literal["local", "openai", "voyage"]
    model: str = Field(min_length=1, max_length=255)
    revision: str = Field(min_length=1, max_length=100)
    dimensions: int = Field(ge=1, le=4096)
    approve_shared_external_processing: bool = False


class BulkVersionRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


DocumentSort = Literal["title", "framework", "version", "created"]
_LIFECYCLE_STATUS = case(
    (KnowledgeVersion.purged_at.is_not(None), "Removed"),
    (KnowledgeVersion.retired_at.is_not(None), "Retired"),
    (KnowledgeVersion.current.is_(True), "Current"),
    else_="Unpublished",
)
_SCOPE_LABEL = case((KnowledgeDocument.org_id.is_(None), "Shared"), else_="Organization")
_SORT_COLUMNS = {
    "title": func.lower(KnowledgeDocument.title),
    "framework": func.lower(func.coalesce(KnowledgeDocument.framework, "Policy")),
    "version": select(func.max(KnowledgeVersion.number))
    .where(KnowledgeVersion.document_id == KnowledgeDocument.id)
    .scalar_subquery(),
    "created": KnowledgeDocument.created_at,
}


def describe(db: Session, document: KnowledgeDocument) -> dict:
    versions = db.scalars(select(KnowledgeVersion).where(KnowledgeVersion.document_id == document.id)
                         .order_by(KnowledgeVersion.number.desc())).all()
    return {"id": document.id, "org_id": document.org_id, "title": document.title,
            "created_at": document.created_at,
            "framework": document.framework, "versions": [
        {"id": v.id, "number": v.number, "edition": v.edition, "source": v.source,
         "content_kind": v.content_kind, "rights": v.rights, "current": v.current,
         "retired_at": v.retired_at, "purged_at": v.purged_at, "content_hash": v.content_hash,
         "indexes": [{"id": i.id, "profile_id": i.profile_id, "status": i.status,
                      "publish_version": i.publish_version, "error_message": i.error_message}
                     for i in db.scalars(select(KnowledgeIndex).where(KnowledgeIndex.version_id == v.id))]}
        for v in versions]}


def list_sources(
    db: Session,
    scope,
    q: str | None,
    title: str | None,
    framework: list[str] | None,
    version: str | None,
    dates: DateRange,
    sort: DocumentSort,
    order: SortOrder,
    page: PageParams,
) -> dict:
    version_query = (
        select(KnowledgeVersion.id)
        .outerjoin(KnowledgeIndex, KnowledgeIndex.version_id == KnowledgeVersion.id)
        .where(KnowledgeVersion.document_id == KnowledgeDocument.id)
    )
    conditions = [
        scope,
        contains(title, KnowledgeDocument.title),
        one_of(KnowledgeDocument.framework, framework),
        any_of(
            contains(
                version,
                KnowledgeVersion.edition,
                KnowledgeVersion.content_kind,
                KnowledgeVersion.source,
                KnowledgeVersion.rights,
                KnowledgeVersion.content_hash,
                KnowledgeIndex.status,
                KnowledgeIndex.error_message,
                _LIFECYCLE_STATUS,
            )
        )
        if version
        else None,
    ]
    if q and q.strip():
        version_search = version_query.where(
            contains(
                q,
                KnowledgeVersion.edition,
                KnowledgeVersion.content_kind,
                KnowledgeVersion.source,
                KnowledgeVersion.rights,
                KnowledgeVersion.content_hash,
                KnowledgeIndex.status,
                KnowledgeIndex.error_message,
                _LIFECYCLE_STATUS,
            )
        ).exists()
        conditions.append(
            any_of(
                contains(
                    q,
                    KnowledgeDocument.title,
                    func.coalesce(KnowledgeDocument.framework, "Policy"),
                    _SCOPE_LABEL,
                    cast(KnowledgeDocument.created_at, String),
                ),
                version_search,
            )
        )
    conditions.extend(dates.conditions(KnowledgeDocument.created_at))
    conditions = [condition for condition in conditions if condition is not None]
    count = db.scalar(select(func.count()).select_from(KnowledgeDocument).where(*conditions)) or 0
    documents = db.scalars(
        select(KnowledgeDocument)
        .where(*conditions)
        .order_by(ordered(_SORT_COLUMNS[sort], order), KnowledgeDocument.created_at.desc(), KnowledgeDocument.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return {"items": [describe(db, d) for d in documents], "total": count}


@router.get("/orgs/{org_id}/documents")
def list_documents(
    org_id: uuid.UUID,
    q: str | None = Query(None),
    title: str | None = Query(None),
    framework: list[str] | None = Query(None),
    version: str | None = Query(None),
    dates: DateRange = Depends(date_range),
    sort: DocumentSort = Query("created"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
                   db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    return list_sources(
        db, or_(KnowledgeDocument.org_id == org_id, KnowledgeDocument.org_id.is_(None)),
        q, title, framework, version, dates, sort, order, page,
    )


@router.get("/platform/documents")
def list_shared(
    q: str | None = Query(None),
    title: str | None = Query(None),
    framework: list[str] | None = Query(None),
    version: str | None = Query(None),
    dates: DateRange = Depends(date_range),
    sort: DocumentSort = Query("created"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
                db: Session = Depends(get_db), _: User = Depends(require_sysadmin)):
    return list_sources(
        db, KnowledgeDocument.org_id.is_(None), q, title, framework, version,
        dates, sort, order, page,
    )


@router.get("/orgs/{org_id}/documents/facets")
def document_facets(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
):
    values = db.scalars(
        select(KnowledgeDocument.framework)
        .where(or_(KnowledgeDocument.org_id == org_id, KnowledgeDocument.org_id.is_(None)))
        .distinct()
        .order_by(KnowledgeDocument.framework)
    ).all()
    return {"framework": [value or "" for value in values]}


@router.get("/platform/documents/facets")
def shared_document_facets(db: Session = Depends(get_db), _: User = Depends(require_sysadmin)):
    values = db.scalars(
        select(KnowledgeDocument.framework)
        .where(KnowledgeDocument.org_id.is_(None))
        .distinct()
        .order_by(KnowledgeDocument.framework)
    ).all()
    return {"framework": [value or "" for value in values]}


async def accept_upload(db, org_id, actor_id, file, title, framework, edition, source, content_kind, rights, document_id):
    if not file.filename or not file.filename.lower().endswith((".txt", ".md", ".markdown")):
        raise HTTPException(422, "Upload UTF-8 text or Markdown")
    raw = await file.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise HTTPException(413, "Document exceeds the 10 MiB limit")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Document must be UTF-8") from None
    if "\x00" in content:
        raise HTTPException(422, "Document contains binary data")
    try:
        version = service.queue_version(db, org_id=org_id, actor_id=actor_id, title=title,
            framework=framework or None, edition=edition, source=source, content_kind=content_kind,
            rights=rights, content=content, document_id=document_id)
        document = db.get(KnowledgeDocument, version.document_id)
        record_event(
            db,
            "document_uploaded",
            org_id=org_id,
            actor=db.get(User, actor_id),
            item=document.title,
            details={
                "document_id": str(document.id),
                "version_id": str(version.id),
                "version": version.number,
                "content_kind": version.content_kind,
            },
        )
        db.commit()
        return describe(db, document)
    except service.KnowledgeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/orgs/{org_id}/documents", status_code=202)
async def upload_document(org_id: uuid.UUID, file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=255),
    framework: Literal["CIS", "NIST", "ISO", ""] = Form(""), edition: str = Form(..., min_length=1, max_length=100),
    source: str = Form(..., min_length=1, max_length=1000),
    content_kind: Literal["official", "original_summary", "organization_policy", "reference"] = Form(...),
    rights: str = Form(..., min_length=1, max_length=2000), document_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    return await accept_upload(db, org_id, member.user_id, file, title, framework, edition, source, content_kind, rights, document_id)


@router.post("/platform/documents", status_code=202)
async def upload_shared(file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=255),
    framework: Literal["CIS", "NIST", "ISO", ""] = Form(""), edition: str = Form(..., min_length=1, max_length=100),
    source: str = Form(..., min_length=1, max_length=1000),
    content_kind: Literal["official", "original_summary", "reference"] = Form(...),
    rights: str = Form(..., min_length=1, max_length=2000), document_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db), user: User = Depends(require_sysadmin)):
    return await accept_upload(db, None, user.id, file, title, framework, edition, source, content_kind, rights, document_id)


def scoped_version(db, version_id, org_id, shared_read=False):
    v = db.get(KnowledgeVersion, version_id)
    d = db.get(KnowledgeDocument, v.document_id) if v else None
    if d is None or (d.org_id != org_id and not (shared_read and d.org_id is None)):
        raise HTTPException(404, "Document version not found")
    return v


@router.get("/orgs/{org_id}/documents/versions/{version_id}")
def preview(org_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db),
            _: OrgMembership = Depends(require_org_member)):
    v = scoped_version(db, version_id, org_id, shared_read=True)
    return {"id": v.id, "content": v.content, "purged_at": v.purged_at}


@router.get("/platform/documents/versions/{version_id}")
def preview_shared(version_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_sysadmin)):
    v = scoped_version(db, version_id, None)
    return {"id": v.id, "content": v.content, "purged_at": v.purged_at}


def change_version(db, org_id, version_id, action, actor_id):
    try:
        service.require_active_org(db, org_id, lock=True)
    except service.KnowledgeError as exc:
        raise HTTPException(409, str(exc)) from exc
    version = scoped_version(db, version_id, org_id)
    document = db.get(KnowledgeDocument, version.document_id)
    try:
        if action == "retire":
            service.retire_version(db, version)
            event_type = "document_retired"
        elif action == "purge":
            service.purge_version(db, version)
            event_type = "document_removed"
        elif action == "reactivate":
            service.queue_reactivation(db, version, actor_id)
            event_type = "document_reactivation_queued"
        else:
            if version.retired_at or version.purged_at:
                raise service.KnowledgeError("Cannot index a retired or removed version")
            profile = service.requested_profile(db, org_id)
            index = db.scalar(select(KnowledgeIndex).where(KnowledgeIndex.version_id == version_id,
                                                          KnowledgeIndex.profile_id == profile.id).with_for_update())
            if index is None:
                db.add(KnowledgeIndex(version_id=version_id, profile_id=profile.id, publish_version=not version.current))
            elif index.status == "failed":
                index.status, index.retry_count, index.error_message = "pending", 0, None
            event_type = "document_index_queued"
        record_event(
            db,
            event_type,
            org_id=org_id,
            actor=db.get(User, actor_id),
            item=document.title,
            details={
                "document_id": str(document.id),
                "version_id": str(version.id),
                "version": version.number,
            },
        )
        db.commit()
    except service.KnowledgeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}


def bulk_change_versions(db, org_id, payload: BulkVersionRequest, action: Literal["retire", "purge"], actor_id):
    if len(set(payload.ids)) != len(payload.ids):
        raise HTTPException(422, "Version IDs must be unique")
    scope = KnowledgeDocument.org_id.is_(None) if org_id is None else KnowledgeDocument.org_id == org_id
    rows = db.execute(
        select(KnowledgeVersion, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
        .where(scope, KnowledgeVersion.id.in_(payload.ids))
        .with_for_update()
    ).all()
    if len(rows) != len(payload.ids):
        raise HTTPException(404, "One or more document versions were not found")
    by_id = {version.id: (version, document) for version, document in rows}
    ordered_rows = [by_id[version_id] for version_id in payload.ids]
    for version, document in ordered_rows:
        if action == "retire" and (version.retired_at or version.purged_at):
            raise HTTPException(409, f"{document.title} version {version.number} is not eligible for retirement")
        if action == "purge" and (version.current or not version.retired_at or version.purged_at):
            raise HTTPException(409, f"{document.title} version {version.number} is not eligible for removal")
    try:
        for version, document in ordered_rows:
            if action == "retire":
                service.retire_version(db, version)
                event_type = "document_retired"
            else:
                service.purge_version(db, version)
                event_type = "document_removed"
            record_event(
                db,
                event_type,
                org_id=org_id,
                actor=db.get(User, actor_id),
                item=document.title,
                details={
                    "document_id": str(document.id),
                    "version_id": str(version.id),
                    "version": version.number,
                },
            )
        db.commit()
    except service.KnowledgeError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    return {"changed": len(ordered_rows)}


@router.post("/orgs/{org_id}/documents/versions/{version_id}/{action}")
def version_action(org_id: uuid.UUID, version_id: uuid.UUID, action: Literal["retire", "purge", "reindex", "reactivate"],
    confirmed: bool = Query(False), db: Session = Depends(get_db), member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    if action == "purge" and not confirmed:
        raise HTTPException(422, "Confirm permanent removal; completed reports keep captured evidence")
    return change_version(db, org_id, version_id, action, member.user_id)


@router.post("/orgs/{org_id}/documents/bulk-retire")
def bulk_retire_documents(
    org_id: uuid.UUID,
    payload: BulkVersionRequest,
    db: Session = Depends(get_db),
    member: OrgMembership = Depends(require_org_role(UserRole.admin)),
):
    return bulk_change_versions(db, org_id, payload, "retire", member.user_id)


@router.post("/orgs/{org_id}/documents/bulk-remove")
def bulk_remove_documents(
    org_id: uuid.UUID,
    payload: BulkVersionRequest,
    confirmed: bool = Query(False),
    db: Session = Depends(get_db),
    member: OrgMembership = Depends(require_org_role(UserRole.admin)),
):
    if not confirmed:
        raise HTTPException(422, "Confirm permanent removal of the selected versions")
    return bulk_change_versions(db, org_id, payload, "purge", member.user_id)


@router.post("/platform/documents/versions/{version_id}/{action}")
def shared_action(version_id: uuid.UUID, action: Literal["retire", "purge", "reindex", "reactivate"],
    confirmed: bool = Query(False), db: Session = Depends(get_db), user: User = Depends(require_sysadmin)):
    if action == "purge" and not confirmed:
        raise HTTPException(422, "Confirm permanent removal; completed reports keep captured evidence")
    return change_version(db, None, version_id, action, user.id)


@router.post("/platform/documents/bulk-retire")
def bulk_retire_shared_documents(
    payload: BulkVersionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_sysadmin),
):
    return bulk_change_versions(db, None, payload, "retire", user.id)


@router.post("/platform/documents/bulk-remove")
def bulk_remove_shared_documents(
    payload: BulkVersionRequest,
    confirmed: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_sysadmin),
):
    if not confirmed:
        raise HTTPException(422, "Confirm permanent removal of the selected versions")
    return bulk_change_versions(db, None, payload, "purge", user.id)


@router.get("/orgs/{org_id}/documents/settings")
def get_settings(org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    platform = service.configured_profile(db)
    local = service.local_profile(db)
    result = {"embedding_target": service.consent_target(platform), "report_target": service.report_target(),
              "effective_embedding": service.consent_target(service.selected_profile(db, org_id)),
              "embedding_granted": service.consented(db, org_id, "embedding", service.consent_target(platform)),
              "report_granted": service.consented(db, org_id, "report", service.report_target()),
              "local_profile_id": str(local.id)}
    db.commit()
    return result


@router.put("/orgs/{org_id}/documents/settings/consent")
def set_consent(org_id: uuid.UUID, payload: ConsentChange, db: Session = Depends(get_db),
                member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    lock_org_configuration(db, org_id)
    expected = service.report_target() if payload.purpose == "report" else service.consent_target(service.configured_profile(db))
    if payload.target != expected:
        raise HTTPException(409, "Provider changed; reload the disclosure before approving")
    row = db.get(KnowledgeConsent, (org_id, payload.purpose), populate_existing=True)
    previous_grant = row.granted if row else False
    previous_target = row.target if row else None
    if row is None:
        row = KnowledgeConsent(org_id=org_id, purpose=payload.purpose, target=expected)
        db.add(row)
    row.target, row.granted, row.actor_id, row.updated_at = expected, payload.granted, member.user_id, utcnow()
    if payload.purpose == "embedding" and payload.granted:
        service.queue_reindex(db, service.configured_profile(db), org_id, member.user_id)
    if previous_grant != payload.granted or previous_target != expected:
        record_event(
            db,
            "knowledge_consent_changed",
            org_id=org_id,
            actor=db.get(User, member.user_id),
            item=f"{payload.purpose.title()} processing consent",
            details={"purpose": payload.purpose, "from": previous_grant, "to": payload.granted, "target": expected},
        )
    db.commit()
    return {"ok": True}


@router.post("/orgs/{org_id}/documents/search")
def search(org_id: uuid.UUID, payload: SearchRequest, db: Session = Depends(get_db),
           _: OrgMembership = Depends(require_org_member)):
    try:
        return {"items": service.retrieve(db, org_id, payload.query, payload.frameworks)}
    except service.KnowledgeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception:
        raise HTTPException(503, "Retrieval unavailable; check model setup and indexing status") from None


@router.post("/platform/documents/load-baseline", status_code=202)
def load_baseline(db: Session = Depends(get_db), user: User = Depends(require_sysadmin)):
    from app.services.knowledge_standards import queue_baseline
    version_ids = queue_baseline(db, user.id)
    record_event(
        db,
        "shared_standards_queued",
        org_id=None,
        actor=user,
        item="NIST, CIS, and ISO source references",
        counts={"documents": len(version_ids)},
        details={"version_ids": version_ids},
    )
    db.commit()
    return {"version_ids": version_ids}


@router.put("/platform/documents/embedding-profile")
def configure_profile(payload: ProfileRequest, db: Session = Depends(get_db), user: User = Depends(require_sysadmin)):
    previous_setting = db.get(PlatformSetting, "knowledge_embedding_profile")
    previous_id = previous_setting.value.get("id") if previous_setting else None
    previous_profile = db.get(EmbeddingProfile, uuid.UUID(previous_id)) if previous_id else None
    if payload.provider == "local":
        profile = service.local_profile(db)
    else:
        if not payload.approve_shared_external_processing:
            raise HTTPException(422, "Explicitly approve sending shared standards and retrieval queries to this provider")
        profile = db.scalar(select(EmbeddingProfile).where(EmbeddingProfile.provider == payload.provider,
            EmbeddingProfile.model == payload.model, EmbeddingProfile.revision == payload.revision,
            EmbeddingProfile.dimensions == payload.dimensions))
        if profile is None:
            profile = EmbeddingProfile(**payload.model_dump(exclude={"approve_shared_external_processing"}))
            db.add(profile)
            db.flush()
    setting = db.get(PlatformSetting, "knowledge_embedding_profile")
    if setting is None:
        setting = PlatformSetting(key="knowledge_embedding_profile")
        db.add(setting)
    setting.value = {"id": str(profile.id)}
    service.queue_reindex(db, profile, None, user.id)
    if previous_id != str(profile.id):
        record_event(
            db,
            "embedding_profile_changed",
            org_id=None,
            actor=user,
            item=service.consent_target(profile),
            details={
                "from": service.consent_target(previous_profile) if previous_profile else "default",
                "to": service.consent_target(profile),
            },
        )
    db.commit()
    return {"id": profile.id, "target": service.consent_target(profile)}
