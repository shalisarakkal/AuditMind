import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.middleware import upload_limit_message
from app.models.enums import ScanStatus
from app.models.scan import Scan
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
    413: {"description": "File exceeds the upload size limit"},
}


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
) -> ImportResponse:
    """Record the upload as a scan, then import it now (201 + report) or, for
    files over IMPORT_SYNC_MAX_BYTES, in the background (202, report later on
    the scan). kind "profile" reads each row with `profile`. `started_by` (the
    uploader) is the one who sees the scan's report until they dismiss it."""
    try:
        fmt = detect_format(file.filename, kind)
    except IngestionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    content = await _read_capped(file, settings.IMPORT_MAX_BYTES)

    scan = Scan(
        org_id=org_id,
        scan_type=f"{profile.family.key}_import" if profile else scan_type_for(kind, fmt),
        profile=profile.key if profile else None,
        source="upload",
        filename=(file.filename or "")[:255] or None,
        status=ScanStatus.pending,
        started_at=datetime.now(timezone.utc),
        started_by=started_by,
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


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK_BYTES):
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=upload_limit_message())
        chunks.append(chunk)
    return b"".join(chunks)
