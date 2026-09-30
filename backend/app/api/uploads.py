import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.middleware import upload_limit_message
from app.models.enums import ScanStatus
from app.models.scan import Scan
from app.models.user import User
from app.schemas.ingestion import ImportResponse
from app.services import ingestion_background
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


async def start_import(
    *,
    db: Session,
    background_tasks: BackgroundTasks,
    response: Response,
    org_id: uuid.UUID,
    file: UploadFile,
    kind: ImportKind,
    started_by: uuid.UUID,
    profile: ProfileConfig | None = None,
    confirm: bool = False,
) -> ImportResponse:
    """Record the upload as a scan, then import it now (201 + report) or, for
    files over IMPORT_SYNC_MAX_BYTES, in the background (202, report later on
    the scan). kind "profile" reads each row with `profile`. `started_by` (the
    uploader) is the one who sees the scan's report until they dismiss it.
    A byte-identical file already imported into the org (not failed or
    archived) is refused with 409 unless `confirm`: a warning, not a block."""
    try:
        fmt = detect_format(file.filename, kind)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    content = await _read_capped(file, settings.IMPORT_MAX_BYTES)
    content_hash = hashlib.sha256(content).hexdigest()
    if not confirm:
        _check_not_imported(db, org_id, content_hash)

    scan = Scan(
        org_id=org_id,
        scan_type=f"{profile.family.key}_import" if profile else scan_type_for(kind, fmt),
        profile=profile.key if profile else None,
        source="upload",
        filename=(file.filename or "")[:255] or None,
        status=ScanStatus.pending,
        started_at=datetime.now(timezone.utc),
        started_by=started_by,
        content_hash=content_hash,
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)

    if len(content) <= settings.IMPORT_SYNC_MAX_BYTES:
        report = process_import(db, scan, kind, fmt, content, profile)
        db.refresh(scan)
        response.status_code = status.HTTP_201_CREATED
        return ImportResponse(scan_id=scan.id, status=scan.status, report=report)

    background_tasks.add_task(ingestion_background.run_import_job, scan.id, kind, fmt, content, profile)
    response.status_code = status.HTTP_202_ACCEPTED
    return ImportResponse(scan_id=scan.id, status=scan.status)


def _check_not_imported(db: Session, org_id: uuid.UUID, content_hash: str) -> None:
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
        return
    started = previous.started_at.astimezone(timezone.utc) if previous.started_at else None
    who = previous.name or previous.email or "someone no longer in the app"
    when = f" on {started:%d %b %Y %H:%M} UTC" if started else ""
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": f"This exact file was already imported{when} by {who}.",
            "imported_at": started.isoformat() if started else None,
            "imported_by": who,
        },
    )


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK_BYTES):
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=upload_limit_message())
        chunks.append(chunk)
    return b"".join(chunks)
