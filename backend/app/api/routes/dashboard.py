import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import Severity
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.dashboard import DashboardSummary, DomainScore
from app.schemas.finding import FindingRead
from app.schemas.scan import ScanRead
from app.services.scoring_service import overall_score, score_all_domains

router = APIRouter(prefix="/orgs/{org_id}/dashboard", tags=["dashboard"])

TOP_FINDINGS = 5
RECENT_SCANS = 5
_SEVERITY_RANK = {Severity.critical: 0, Severity.high: 1, Severity.medium: 2, Severity.low: 3}


@router.get("", response_model=DashboardSummary)
def get_dashboard(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> DashboardSummary:
    """Scores computed live from the org's current findings, the most severe
    findings (newest first within a severity), and the latest scans."""
    findings = db.query(Finding).filter(Finding.org_id == org_id).all()
    domain_scores = score_all_domains(findings)
    overall, overall_tier = overall_score(domain_scores)

    top = sorted(findings, key=lambda f: (_SEVERITY_RANK[f.severity], -f.created_at.timestamp()))[:TOP_FINDINGS]
    recent_scans = (
        db.query(Scan)
        .filter(Scan.org_id == org_id)
        .order_by(Scan.started_at.desc().nulls_last())
        .limit(RECENT_SCANS)
        .all()
    )
    by_severity = {severity: 0 for severity in Severity}
    for finding in findings:
        by_severity[finding.severity] += 1

    return DashboardSummary(
        overall_score=overall,
        overall_tier=overall_tier,
        domains=[
            DomainScore(domain=domain, score=score, tier=tier, justification=justification)
            for domain, (score, tier, justification) in domain_scores.items()
        ],
        top_findings=[FindingRead.model_validate(f) for f in top],
        recent_scans=[ScanRead.model_validate(s) for s in recent_scans],
        asset_count=db.query(func.count(Asset.id)).filter(Asset.org_id == org_id).scalar(),
        findings_by_severity=by_severity,
    )
