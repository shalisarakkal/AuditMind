import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.middleware import upload_limit_message
from app.models.enums import ScanStatus
from app.models.scan import Scan
from app.models.user import User
from app.schemas.ingestion import ImportResponse
from app.services.events import record_event
from app.services.import_profiles import ProfileConfig
from app.services.ingestion_service import (
    ImportKind,
    IngestionError,
    detect_format,
    process_import,
    scan_type_for,
)

_CHUNK_BYTES = 1024 * 1024

# OpenAPI docs for the two import endpoints' variable status code.
IMPORT_RESPONSES = {
    202: {"model": ImportResponse, "description": "Large file accepted; poll the scan for the report"},
    400: {"description": "Unsupported file type"},
    409: {"description": "The same file was already imported: send it again with confirm=true to import it anyway"},
    413: {"description": "File exceeds the upload size limit"},
}


def confirm_form() -> bool:
    return Form(
        False,
        description="Import even if this exact file was already imported into the org "
        "(otherwise that answers 409 with when and by whom)",
    )


def upload_path(scan_id: uuid.UUID) -> Path:
    """Where a large file waits for the background worker."""
    return settings.upload_dir / f"{scan_id}.upload"


async def start_import(
    *,
    db: Session,
    response: Response,
    org_id: uuid.UUID,
    file: UploadFile,
    kind: ImportKind,
    started_by: uuid.UUID,
    profile: ProfileConfig | None = None,
    confirm: bool = False,
) -> ImportResponse:
    """Record the upload as a scan, then import it now (201 + report) or, for
    files over IMPORT_SYNC_MAX_BYTES, leave it saved in UPLOAD_DIR for the
    background worker (202, report later on the scan). kind "profile" reads
    each row with `profile`. `started_by` (the uploader) is the one who sees
    the scan's report until they dismiss it. A byte-identical file already
    imported into the org (not failed or archived) is refused with 409
    unless `confirm`: a warning, not a block (and an Activity event)."""
    try:
        fmt = detect_format(file.filename, kind)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    received = await _receive(file, settings.IMPORT_MAX_BYTES, settings.IMPORT_SYNC_MAX_BYTES)
    try:
        from app.services.knowledge_service import KnowledgeError, require_active_org
        try:
            require_active_org(db, org_id, lock=True)
        except KnowledgeError as exc:
            raise HTTPException(409, str(exc)) from exc
        previous = _previous_import(db, org_id, received.sha256)
        if previous is not None and not confirm:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=previous)

        inline = received.content is not None
        filename = (file.filename or "")[:255] or None
        scan = Scan(
            org_id=org_id,
            scan_type=f"{profile.family.key}_import" if profile else scan_type_for(kind, fmt),
            profile=profile.key if profile else None,
            source="upload",
            filename=filename,
            # A file imported here is running already, so the worker never
            # picks it up; a large one waits for it.
            status=ScanStatus.running if inline else ScanStatus.pending,
            started_at=datetime.now(timezone.utc),
            started_by=started_by,
            content_hash=received.sha256,
        )
        db.add(scan)
        if previous is not None:
            record_event(
                db,
                "repeat_upload",
                org_id=org_id,
                actor=db.get(User, started_by),
                item=filename,
                details={"previously_imported_at": previous["imported_at"], "previously_by": previous["imported_by"]},
            )
        db.flush()
        if not inline:
            os.replace(received.path, upload_path(scan.id))
        db.commit()
        db.refresh(scan)
    finally:
        if received.path is not None and received.path.exists():
            received.path.unlink()  # not queued: refused, or the save failed

    if inline:
        report = process_import(db, scan, kind, fmt, received.content, profile)
        db.refresh(scan)
        response.status_code = status.HTTP_201_CREATED
        return ImportResponse(scan_id=scan.id, status=scan.status, report=report)
    response.status_code = status.HTTP_202_ACCEPTED
    return ImportResponse(scan_id=scan.id, status=scan.status)


def _previous_import(db: Session, org_id: uuid.UUID, content_hash: str) -> dict | None:
    """The same file already imported into the org (not failed or
    archived): when and by whom, as the 409 answers it."""
    previous = db.execute(
        select(Scan.started_at, User.name, User.email)
        .outerjoin(User, User.id == Scan.started_by)
        .where(
            Scan.org_id == org_id,
            Scan.content_hash == content_hash,
            Scan.status != ScanStatus.failed,
            Scan.archived_at.is_(None),
        )
        .order_by(Scan.started_at.desc())
        .limit(1)
    ).first()
    if previous is None:
        return None
    started = previous.started_at.astimezone(timezone.utc) if previous.started_at else None
    who = previous.name or previous.email or "someone no longer in the app"
    when = f" on {started:%d %b %Y %H:%M} UTC" if started else ""
    return {
        "message": f"This exact file was already uploaded{when} by {who}.",
        "imported_at": started.isoformat() if started else None,
        "imported_by": who,
    }


@dataclass
class _Received:
    sha256: str
    # The file in memory (up to the size imported during the request), or
    # the temporary file it was written to.
    content: bytes | None
    path: Path | None


async def _receive(file: UploadFile, max_bytes: int, keep_in_memory: int) -> _Received:
    """Read the upload, hashing it as it comes. A file larger than
    `keep_in_memory` goes to a temporary file in UPLOAD_DIR as it's read,
    so the web server never holds a large file in memory."""
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    path: Path | None = None
    out = None
    try:
        while chunk := await file.read(_CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=upload_limit_message())
            digest.update(chunk)
            if out is None and size > keep_in_memory:
                settings.upload_dir.mkdir(parents=True, exist_ok=True)
                path = settings.upload_dir / f"receiving-{uuid.uuid4()}.part"
                out = path.open("wb")
                out.writelines(chunks)
                chunks = []
            if out is not None:
                out.write(chunk)
            else:
                chunks.append(chunk)
    except BaseException:
        if out is not None:
            out.close()
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    if out is not None:
        out.close()
        return _Received(sha256=digest.hexdigest(), content=None, path=path)
    return _Received(sha256=digest.hexdigest(), content=b"".join(chunks), path=None)
