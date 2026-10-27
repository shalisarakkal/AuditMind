import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session, defer

from app.api.deps import require_org_member
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import Severity
from app.models.finding import Finding
from app.models.event import Event
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.dashboard import DashboardSummary, DomainScore, SecuritySummary
from app.schemas.finding import FindingRead
from app.schemas.scan import brief_scan
from app.services.scoring_service import count_org_findings, overall_score, score_all_from_counts

router = APIRouter(prefix="/orgs/{org_id}/dashboard", tags=["dashboard"])

TOP_FINDINGS = 5
RECENT_SCANS = 5


@router.get("/security-summary", response_model=SecuritySummary)
def security_summary(org_id: uuid.UUID, db: Session = Depends(get_db),
                     _: OrgMembership = Depends(require_org_member)):
    """Completed organization actions started within the exact rolling seven days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    types = ("member_added", "role_changed", "purge")
    counts = dict(db.query(Event.type, func.count(Event.id)).filter(
        Event.org_id == org_id, Event.type.in_(types), Event.outcome == "completed",
        Event.started_at >= start, Event.started_at < end).group_by(Event.type).all())
    return dict(window_start=start, window_end=end,
                counts={kind: counts.get(kind, 0) for kind in types})


@router.get("", response_model=DashboardSummary)
def get_dashboard(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> DashboardSummary:
    """Scores computed live from the org's current findings, the most severe
    findings (newest first within a severity), and the latest scans. The
    database does the counting: an org can have hundreds of thousands of
    findings."""
    counts = count_org_findings(db, org_id)
    domain_scores = score_all_from_counts(counts)
    overall, overall_tier = overall_score(domain_scores)

    # Most severe first, newest first within a severity: one small query per
    # severity (index ix_findings_org_severity_created) rather than sorting
    # every finding.
    top: list[Finding] = []
    for severity in Severity:
        if len(top) == TOP_FINDINGS:
            break
        top += (
            db.query(Finding)
            .options(defer(Finding.raw_data))
            .filter(Finding.org_id == org_id, Finding.archived_at.is_(None), Finding.severity == severity)
            .order_by(Finding.created_at.desc(), Finding.id)
            .limit(TOP_FINDINGS - len(top))
            .all()
        )
    recent_scans = (
        db.query(Scan)
        .filter(Scan.org_id == org_id, Scan.archived_at.is_(None))
        .order_by(Scan.started_at.desc().nulls_last())
        .limit(RECENT_SCANS)
        .all()
    )
    by_severity = {severity: 0 for severity in Severity}
    for by_domain in counts.values():
        for severity, count in by_domain.items():
            by_severity[severity] += count

    asset_count = db.query(func.count(Asset.id)).filter(Asset.org_id == org_id, Asset.archived_at.is_(None)).scalar()
    empty = asset_count == 0 and not any(by_severity.values())
    status = "not_assessed" if empty else "findings_based"

    return DashboardSummary(
        overall_score=None if empty else overall,
        overall_tier=None if empty else overall_tier,
        assessment_status=status,
        domains=[
            DomainScore(domain=domain, score=None if empty else score, tier=None if empty else tier,
                        assessment_status=status,
                        justification="No active assets or findings recorded. Not assessed." if empty else justification)
            for domain, (score, tier, justification) in domain_scores.items()
        ],
        top_findings=[FindingRead.model_validate(f) for f in top],
        recent_scans=[brief_scan(s) for s in recent_scans],
        asset_count=asset_count,
        findings_by_severity=by_severity,
    )

