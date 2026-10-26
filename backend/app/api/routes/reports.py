"""API routes for audit reports (list, generate, view, download HTML, cancel, delete)."""

import re
import uuid
import zipfile
from tempfile import SpooledTemporaryFile
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Integer, String, case, cast, func, select
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import DateRange, PageParams, SortOrder, any_of, contains, date_range, one_of, ordered, page_params
from app.core.config import settings
from app.db.session import get_db
from app.models.enums import ReportStatus, UserRole
from app.models.membership import OrgMembership
from app.models.report import Report
from app.models.user import User
from app.schemas.paging import Page
from app.schemas.report import ReportCreate, ReportDetail, ReportRead
from app.services import report_service
from app.services.events import record_event
from app.services.knowledge_service import KnowledgeError, require_report_consent

router = APIRouter(prefix="/orgs/{org_id}/reports", tags=["reports"])

ReportSort = Literal["title", "frameworks", "status", "score", "created"]
_RULE_BASED_TEST_LABEL = "Rule-based test · no framework assessment"
_REPORT_FRAMEWORKS_DISPLAY = func.coalesce(
    Report.frameworks,
    case(
        (Report.data["provenance"]["assessment_type"].astext == "rule_based_test", _RULE_BASED_TEST_LABEL),
        else_="",
    ),
)
_SORT_COLUMNS = {
    "title": func.lower(Report.title),
    "frameworks": func.lower(_REPORT_FRAMEWORKS_DISPLAY),
    "status": Report.status,
    "score": cast(Report.data["overall_score"].astext, Integer),
    "created": Report.created_at,
}
_REPORT_SCORE = cast(Report.data["overall_score"].astext, String)
_REPORT_STATUS = cast(Report.status, String)


class ReportFacets(BaseModel):
    status: list[ReportStatus]
    frameworks: list[str]


class ReportBulkDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ReportBulkDeleteResponse(BaseModel):
    deleted: int


class ReportBulkDownloadRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ReportCapabilities(BaseModel):
    rule_based_test_enabled: bool


@router.get("/capabilities", response_model=ReportCapabilities)
def report_capabilities(
    _: OrgMembership = Depends(require_org_member),
) -> ReportCapabilities:
    """Returns report workflows enabled by this API instance's configuration."""
    return ReportCapabilities(rule_based_test_enabled=settings.RULE_BASED_TEST_REPORTS_ENABLED)


@router.get("", response_model=Page[ReportRead])
def list_reports(
    org_id: uuid.UUID,
    q: str | None = Query(None, description="Search every shown report column"),
    title: str | None = Query(None, description="Report title contains this"),
    frameworks: str | None = Query(None, description="Displayed framework label contains this"),
    status: list[ReportStatus] | None = Query(None, description="Status is one of these"),
    score: str | None = Query(None, description="Score contains this"),
    assessment_status: Literal['complete', 'partial'] | None = Query(None),
    dates: DateRange = Depends(date_range),
    sort: ReportSort = Query("created", description="Column to sort by"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[ReportRead]:
    """List an organization's reports with shared paging, sorting and filters."""
    conditions = [
        Report.org_id == org_id,
        any_of(
            contains(q, Report.title, _REPORT_FRAMEWORKS_DISPLAY, _REPORT_STATUS, _REPORT_SCORE),
        ),
        contains(title, Report.title),
        contains(frameworks, _REPORT_FRAMEWORKS_DISPLAY),
        one_of(Report.status, [item.value for item in status] if status else None),
        contains(score, _REPORT_SCORE),
        Report.data['assessment_status'].astext == assessment_status if assessment_status else None,
    ]
    conditions = [condition for condition in conditions if condition is not None]
    conditions.extend(dates.conditions(Report.created_at))
    total = db.scalar(select(func.count()).select_from(Report).where(*conditions)) or 0
    rows = db.scalars(
        select(Report)
        .where(*conditions)
        .order_by(ordered(_SORT_COLUMNS[sort], order), Report.created_at.desc(), Report.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return Page(items=[ReportRead.model_validate(report, from_attributes=True) for report in rows], total=total)


@router.get("/facets", response_model=ReportFacets)
def report_facets(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> ReportFacets:
    """Organization-scoped values for status and framework filters."""
    statuses = db.scalars(
        select(Report.status).where(Report.org_id == org_id).distinct().order_by(Report.status)
    ).all()
    labels = db.scalars(
        select(_REPORT_FRAMEWORKS_DISPLAY).where(Report.org_id == org_id).distinct()
    ).all()
    frameworks = sorted({value.strip() for label in labels for value in label.split(",") if value.strip()})
    return ReportFacets(status=list(statuses), frameworks=frameworks)


@router.post("/bulk-download")
def bulk_download_reports(
    org_id: uuid.UUID,
    payload: ReportBulkDownloadRequest,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> StreamingResponse:
    """Downloads selected completed reports as PDFs in one ZIP archive."""
    if len(set(payload.ids)) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Report IDs must be unique.")
    reports = db.scalars(
        select(Report).where(Report.org_id == org_id, Report.id.in_(payload.ids))
    ).all()
    if len(reports) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more reports were not found.")
    unavailable = [
        report.title
        for report in reports
        if report.status not in (ReportStatus.completed, ReportStatus.generated)
    ]
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed reports can be downloaded: " + ", ".join(unavailable),
        )

    reports_by_id = {report.id: report for report in reports}
    archive = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for report_id in payload.ids:
            report = reports_by_id[report_id]
            safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", report.title).strip("._")[:100].lower() or "report"
            zip_file.writestr(
                f"audit_report_{safe_title}_{report.id}.pdf",
                report_service.render_report_pdf(report),
            )
    archive.seek(0)

    def stream_archive():
        try:
            while chunk := archive.read(64 * 1024):
                yield chunk
        finally:
            archive.close()

    return StreamingResponse(
        stream_archive(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="audit_reports.zip"'},
    )


@router.post("/bulk-delete", response_model=ReportBulkDeleteResponse)
def bulk_delete_reports(
    org_id: uuid.UUID,
    payload: ReportBulkDeleteRequest,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> ReportBulkDeleteResponse:
    """Delete selected, finished reports atomically and record each deletion."""
    if len(set(payload.ids)) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Report IDs must be unique.")
    reports = db.scalars(
        select(Report).where(Report.org_id == org_id, Report.id.in_(payload.ids))
    ).all()
    if len(reports) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more reports were not found.")
    active = [report.title for report in reports if report.status in (ReportStatus.pending, ReportStatus.running)]
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancel report generation before deleting selected reports: " + ", ".join(active),
        )

    actor = db.get(User, membership.user_id)
    for report in reports:
        record_event(
            db,
            "report_deleted",
            org_id=org_id,
            actor=actor,
            item=report.title,
            details={"report_id": str(report.id), "status": report.status.value},
        )
        db.delete(report)
    db.commit()
    return ReportBulkDeleteResponse(deleted=len(reports))


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReportRead,
    summary="Queue an AI audit report generation job",
)
def generate_report(
    org_id: uuid.UUID,
    payload: ReportCreate,
    idempotency_key: str | None = Header(None, min_length=1, max_length=128),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
    db: Session = Depends(get_db),
) -> Report:
    """Queues a new comprehensive cyber resilience audit report (processed asynchronously
    by the background worker with RAG and Claude reasoning).
    """
    try:
        require_report_consent(db, org_id)
    except KnowledgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        report = report_service.queue_report_generation(
            db=db,
            org_id=org_id,
            title=payload.title,
            user_id=membership.user_id,
            frameworks=payload.frameworks,
            period_start=payload.period_start,
            period_end=payload.period_end,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return report


@router.post("/rule-based-test", status_code=status.HTTP_201_CREATED, response_model=ReportRead)
def generate_rule_based_test_report(
    org_id: uuid.UUID,
    payload: ReportCreate,
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
    db: Session = Depends(get_db),
) -> Report:
    """Creates a no-provider test report when the test-only setting is enabled."""
    if not settings.RULE_BASED_TEST_REPORTS_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report workflow not found")
    if not payload.title.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Report title cannot be blank.")
    return report_service.create_rule_based_test_report(
        db=db,
        org_id=org_id,
        title=payload.title.strip(),
        user_id=membership.user_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
    )


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(
    org_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Report:
    """Fetches full details and snapshot data for an audit report."""
    report = db.get(Report, report_id)
    if not report or report.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.get("/{report_id}/download", response_class=Response)
def download_report(
    org_id: uuid.UUID,
    report_id: uuid.UUID,
    format: Literal["html", "json", "pdf"] = Query("html"),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Response:

    """Downloads the rendered audit report as HTML, PDF, or raw JSON snapshot."""
    report = db.get(Report, report_id)
    if not report or report.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    if report.status not in (ReportStatus.completed, ReportStatus.generated):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is not completed (current status: {report.status.value})",
        )

    if format == "pdf":
        safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", report.title).strip("._")[:100].lower()
        safe_filename = safe_filename or "report"
        return Response(
            content=report_service.render_report_pdf(report),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="audit_report_{safe_filename}_{report.id}.pdf"'
            },
        )

    if format == "html":
        safe_filename = re.sub(r"[^A-Za-z0-9._-]+", "_", report.title).strip("._")[:100].lower()
        safe_filename = safe_filename or "report"
        html_content = report_service.render_report_html(report)
        return Response(
            content=html_content,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="audit_report_{safe_filename}_{report.id}.html"'
            },
        )

    return JSONResponse(content=report.data or {})


@router.post("/{report_id}/cancel", response_model=ReportRead)
def cancel_report(
    org_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Report:
    """Cancels a pending or running report job."""
    try:
        return report_service.cancel_report_job(db, report_id, org_id, membership.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    org_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin)),
) -> None:
    """Deletes an audit report."""
    report = db.get(Report, report_id)
    if not report or report.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    if report.status in (ReportStatus.pending, ReportStatus.running):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancel report generation before deleting it.",
        )

    actor = db.get(User, membership.user_id)
    record_event(
        db,
        "report_deleted",
        org_id=org_id,
        actor=actor,
        item=report.title,
        details={"report_id": str(report.id), "status": report.status.value},
    )
    db.delete(report)
    db.commit()
