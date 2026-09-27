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


@router.post("/generate", response_model=ReportRead, status_code=status.HTTP_202_ACCEPTED)
def generate_report(
    org_id: uuid.UUID,
    payload: ReportCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Report:
    # Placeholder: full Claude-driven report generation (PROMPTS_CLAUDE.md section 5)
    # lands once risk scoring + RAG are wired up.
    report = Report(org_id=org_id, **payload.model_dump())
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


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
