import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, defer

from app.api.deps import require_org_member, require_org_role
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import Domain, Severity, UserRole
from app.models.organization import Organization
from app.models.finding import Finding
from app.models.event import Event
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.dashboard import (DashboardSummary, DashboardPending, DomainScore, SecuritySummary,
    OrganizationDashboardSettings, OrganizationDashboardSettingsUpdate)
from app.services.events import record_event
from app.schemas.finding import FindingRead
from app.schemas.scan import brief_scan
from app.services import evidence_jobs, dashboard_snapshots
from app.models.scoring_qualification import OrganizationScoringSettings
from app.services.evidence_policy import POLICY_VERSION
from app.services.scoring_service import count_org_findings, overall_score, score_all_from_counts

router = APIRouter(prefix="/orgs/{org_id}/dashboard", tags=["dashboard"])

TOP_FINDINGS = 5
RECENT_SCANS = 5


def organization_refresh_settings(db, org_id):
    org = db.get(Organization, org_id, populate_existing=True)
    config = dashboard_snapshots.configuration(db)
    return OrganizationDashboardSettings(enabled=config.enabled,
        platform_refresh_interval_seconds=config.refresh_interval_seconds,
        refresh_interval_seconds=dashboard_snapshots.effective_interval(org, config),
        refresh_interval_override_seconds=org.dashboard_refresh_interval_seconds,
        version=org.dashboard_refresh_settings_version)


@router.get("/settings", response_model=OrganizationDashboardSettings)
def get_refresh_settings(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                         _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    return organization_refresh_settings(db, org_id)


@router.patch("/settings", response_model=OrganizationDashboardSettings)
def update_refresh_settings(org_id: uuid.UUID, payload: OrganizationDashboardSettingsUpdate,
                            response: Response, db: Session = Depends(get_db),
                            member: OrgMembership = Depends(require_org_role(UserRole.admin))):
    org = db.get(Organization, org_id, populate_existing=True)
    if org.dashboard_refresh_settings_version != payload.expected_version:
        raise HTTPException(409, "Dashboard refresh settings changed; reload before retrying")
    before = org.dashboard_refresh_interval_seconds
    if before != payload.refresh_interval_override_seconds:
        org.dashboard_refresh_interval_seconds = payload.refresh_interval_override_seconds
        org.dashboard_refresh_settings_version += 1
        from app.models.user import User
        record_event(db, "settings_changed", org_id=org_id, actor=db.get(User, member.user_id),
            item="Dashboard refresh interval", details={"from": before, "to": org.dashboard_refresh_interval_seconds})
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return organization_refresh_settings(db, org_id)


@router.get("/security-summary", response_model=SecuritySummary)
def security_summary(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                     _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    if dashboard_snapshots.configuration(db).enabled:
        from app.models.dashboard_snapshot import DashboardSnapshot
        from sqlalchemy import select
        row = db.scalar(select(DashboardSnapshot).where(DashboardSnapshot.org_id == org_id))
        if row and row.payload:
            return SecuritySummary.model_validate(row.payload["security"]).model_copy(update={"snapshot_generated_at": row.generated_at})
    return build_security_summary(org_id, db)


def build_security_summary(org_id, db):
    """Completed organization actions started within the exact rolling seven days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    types = ("member_added", "role_changed", "purge")
    counts = dict(db.query(Event.type, func.count(Event.id)).filter(
        Event.org_id == org_id, Event.type.in_(types), Event.outcome == "completed",
        Event.started_at >= start, Event.started_at < end).group_by(Event.type).all())
    return SecuritySummary(window_start=start, window_end=end,
                           counts={kind: counts.get(kind, 0) for kind in types})


@router.get("", response_model=DashboardSummary | DashboardPending)
def get_dashboard(
    org_id: uuid.UUID, response: Response, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> DashboardSummary | DashboardPending:
    response.headers["Cache-Control"] = "no-store"
    if dashboard_snapshots.configuration(db).enabled:
        result = dashboard_snapshots.read(db, org_id)
        if isinstance(result, DashboardPending):
            response.status_code = 202
        return result
    # Counts, mode, revision and cached qualification must describe one snapshot.
    # Do not retain the authorization connection throughout the dashboard read.
    engine = db.get_bind()
    db.rollback()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as snapshot:
            return build_dashboard(org_id, snapshot)


@router.post("/refresh", response_model=DashboardSummary | DashboardPending)
def refresh_dashboard(org_id: uuid.UUID, response: Response, db: Session = Depends(get_db),
                      _: OrgMembership = Depends(require_org_member)):
    response.headers["Cache-Control"] = "no-store"
    if not dashboard_snapshots.configuration(db).enabled:
        raise HTTPException(409, "Stored Dashboard snapshots are disabled in Platform settings")
    if dashboard_snapshots.enqueue(db, org_id) is None:
        raise HTTPException(409, "Organization is archived or being deleted")
    response.status_code = 202
    return dashboard_snapshots.read(db, org_id)


def build_dashboard(org_id: uuid.UUID, db: Session, inventory: dict | None = None, captured_revision: int | None = None) -> DashboardSummary:
    """Assemble scores from fresh or saved inventory with live qualification.

    Only capture_inventory scans/counts source tables; saved reads reuse its
    timestamped output while checking current scoring mode and evidence.
    """
    inventory = inventory if inventory is not None else capture_inventory(org_id, db)
    counts = {Domain(d): {Severity(s): n for s, n in values.items()} for d, values in inventory["counts"].items()}
    domain_scores = score_all_from_counts(counts)
    overall, overall_tier = overall_score(domain_scores)
    top, recent_scans, asset_count = inventory["top_findings"], inventory["recent_scans"], inventory["asset_count"]
    by_severity = {severity: sum(values.get(severity, 0) for values in counts.values()) for severity in Severity}
    empty = asset_count == 0 and not any(by_severity.values())
    status = "not_assessed" if empty else "findings_based"

    settings_row = db.get(OrganizationScoringSettings, org_id)
    enabled = settings_row.evidence_qualified_enabled if settings_row else False
    current_revision = evidence_jobs.revision(db, org_id)
    live_evaluation = evidence_jobs.current_result(db, org_id) if enabled else None
    evaluated = live_evaluation if captured_revision is None or captured_revision == current_revision else None
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
        evaluation_id=live_evaluation.id if live_evaluation else None,
        policy_version=POLICY_VERSION if enabled else None,
        overall_reason=(evaluated.result.get("overall_reason") if evaluated else "evaluation_required") if enabled else None,
        domains=domains,
        top_findings=[FindingRead.model_validate(f) for f in top],
        recent_scans=recent_scans,
        asset_count=asset_count,
        findings_by_severity=by_severity,
    )


def capture_inventory(org_id: uuid.UUID, db: Session) -> dict:
    counts = count_org_findings(db, org_id)

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
    # Count rows without fetching UUIDs from the heap: existing active-asset
    # indexes can serve an index-only count. IDs are non-null, so semantics match.
    asset_count = db.query(func.count()).select_from(Asset).filter(Asset.org_id == org_id, Asset.archived_at.is_(None)).scalar()

    return {"counts": {d.value: {s.value: n for s, n in values.items()} for d, values in counts.items()},
            "asset_count": asset_count, "top_findings": [FindingRead.model_validate(f).model_dump(mode="json") for f in top],
            "recent_scans": [brief_scan(s).model_dump(mode="json") for s in recent_scans]}

