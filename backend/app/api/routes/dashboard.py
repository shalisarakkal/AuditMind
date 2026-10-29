import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
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
from app.services import evidence_jobs
from app.models.scoring_qualification import OrganizationScoringSettings
from app.services.evidence_policy import POLICY_VERSION
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
    org_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> DashboardSummary:
    response.headers["Cache-Control"] = "no-store"
    # Counts, mode, revision and cached qualification must describe one snapshot.
    # Do not retain the authorization connection throughout the dashboard read.
    engine = db.get_bind()
    db.rollback()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            return build_dashboard(org_id, snapshot)


def build_dashboard(org_id: uuid.UUID, db: Session) -> DashboardSummary:
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

    # Count rows without fetching UUIDs from the heap: existing active-asset
    # indexes can serve an index-only count. IDs are non-null, so semantics match.
    asset_count = db.query(func.count()).select_from(Asset).filter(Asset.org_id == org_id, Asset.archived_at.is_(None)).scalar()
    empty = asset_count == 0 and not any(by_severity.values())
    status = "not_assessed" if empty else "findings_based"

    settings_row = db.get(OrganizationScoringSettings, org_id)
    enabled = settings_row.evidence_qualified_enabled if settings_row else False
    current_revision = evidence_jobs.revision(db, org_id)
    evaluated = evidence_jobs.current_result(db, org_id) if enabled else None
    qualified = {d["domain"]: d for d in evaluated.result["domains"]} if evaluated else {}
    count = sum(d["eligible"] for d in qualified.values())
    qualified_status = evaluated.result["assessment_status"] if evaluated else "not_assessed"
    domains = []
    for domain, (score, tier, justification) in domain_scores.items():
        if not enabled:
            domains.append(DomainScore(domain=domain, score=None if empty else score, tier=None if empty else tier,
                assessment_status=status, justification="No active assets or findings recorded. Not assessed." if empty else justification))
            continue
        coverage = qualified.get(domain.value)
        eligible = bool(coverage and coverage["eligible"])
        domains.append(DomainScore(domain=domain, score=score if eligible else None, tier=tier if eligible else None,
            assessment_status="evidence_qualified" if eligible else "not_assessed", justification=justification if eligible else "Current operational evidence is required before assigning a score.",
            evidence_status=coverage["evidence_status"] if coverage else "limited",
            evidence_reason=coverage["reason_code"] if coverage else "evaluation_required",
            qualification_id=coverage.get("qualification_id") if coverage else None,
            qualification_version=coverage.get("version") if coverage else None,
            qualification_scope=coverage.get("scope") if coverage else None,
            reviewed_at=coverage.get("reviewed_at") if coverage else None,
            expires_at=coverage.get("expires_at") if coverage else None,
            observed_at=coverage.get("observed_at", []) if coverage else [],
            source_references=coverage.get("source_references", []) if coverage else []))

    return DashboardSummary(
        overall_score=overall if (qualified_status == "complete" if enabled else not empty) else None,
        overall_tier=overall_tier if (qualified_status == "complete" if enabled else not empty) else None,
        assessment_status=qualified_status if enabled else status,
        scoring_mode="evidence_qualified" if enabled else "findings_based",
        settings_version=settings_row.version if settings_row else 0,
        evidence_revision=current_revision, qualified_domain_count=count,
        evaluation_state=("current" if evaluated else "not_current") if enabled else "not_required",
        qualification_evaluated_at=evaluated.result["evaluated_at"] if evaluated else None,
        evaluation_id=evaluated.id if evaluated else None,
        policy_version=POLICY_VERSION if enabled else None,
        overall_reason=(evaluated.result.get("overall_reason") if evaluated else "evaluation_required") if enabled else None,
        domains=domains,
        top_findings=[FindingRead.model_validate(f) for f in top],
        recent_scans=[brief_scan(s) for s in recent_scans],
        asset_count=asset_count,
        findings_by_severity=by_severity,
    )

