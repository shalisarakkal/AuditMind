import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.report import Report
from app.schemas.report import ReportCreate, ReportRead

router = APIRouter(prefix="/orgs/{org_id}/reports", tags=["reports"])


@router.get("", response_model=list[ReportRead])
def list_reports(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> list[Report]:
    return db.query(Report).filter(Report.org_id == org_id).all()


@router.post(
    "/generate",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={501: {"description": "Not available yet: report generation arrives in Phase 3"}},
)
def generate_report(
    org_id: uuid.UUID,
    payload: ReportCreate,
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> None:
    """Report generation: not available yet (501). Phase 3 makes it a job
    for the background worker (PROMPTS_CLAUDE.md section 5); until then no
    report is recorded that would never be written."""
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Report generation isn't available yet")


@router.get("/{report_id}", response_model=ReportRead)
def get_report(
    org_id: uuid.UUID,
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Report:
    report = db.get(Report, report_id)
    if not report or report.org_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report
