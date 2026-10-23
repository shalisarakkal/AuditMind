"""Report management service: handles queueing, background worker processing, HTML rendering, and lifecycle."""

import logging
import json
import hashlib
import math
import uuid
from io import BytesIO
from datetime import date, datetime, time, timedelta, timezone
from html import escape as escape_html
from typing import Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

import app.db.base  # noqa: F401
from app.models.asset import Asset
from app.models.enums import Criticality, Domain, ReportStatus, RiskTier, Severity
from app.models.finding import Finding
from app.models.report import Report
from app.models.user import User
from app.core.config import settings
from app.schemas.report_ai import AuditReportSnapshot, DomainScoreAI, RemediationActionAI
from app.services.events import record_event
from app.services.report_ai_service import generate_ai_audit_snapshot
from app.services.knowledge_service import require_report_consent
from app.services import scoring_service

logger = logging.getLogger("app.reports")


def _unsupported_snapshot(data: dict) -> bool:
    version = (data.get('provenance') or {}).get('schema_version')
    return version is not None and (type(version) is not int or version not in (1, 2, 3))


def _snapshot_tier(score: int) -> RiskTier:
    return scoring_service.tier_for_score(score)


def _remediation_evidence_lines(action: dict) -> list[str]:
    confidence = action.get("confidence")
    if (isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
            and math.isfinite(confidence) and 0 <= confidence <= 1):
        confidence_text = f"Model-estimated confidence: {confidence * 100:.0f}% (not calibrated)"
    else:
        confidence_text = "Confidence: not recorded"
    return [confidence_text,
        "Evidence references: " + (", ".join(map(str, action.get("citation_ids") or [])) or "Not recorded"),
        "Affected findings: " + (", ".join(map(str, action.get("affected_finding_ids") or [])) or "No specific finding references recorded"),
        "Affected assets: " + (", ".join(map(str, action.get("affected_asset_ids") or [])) or "No specific asset references recorded")]


def _assessment_display_lines(data: dict) -> list[str]:
    """Presentation only: never infer evidence sufficiency or rewrite saved scores."""
    provenance = data.get("provenance") or {}
    if provenance.get("assessment_type") == "rule_based_test":
        return ["Deterministic test score; no AI or framework control assessment.",
                "Higher scores mean greater resilience; this is not proof of compliance."]
    baseline = provenance.get("rule_based") or {}
    score = baseline.get("overall_score")
    lines = ["AI resilience score (advisory). Higher scores mean greater resilience.",
             "AI and deterministic scores are separate assessments. AI variation is not a measured change in security posture.",
             f"Captured deterministic baseline: {str(score) + '/100 (' + str(baseline.get('overall_tier', 'not recorded')) + ')' if score is not None else 'not recorded'}.",
             "Inventory totals are not proof of complete control assessment or compliance.",
             "Confidence is model-estimated evidential support, not a calibrated probability of compliance or remediation success, and not evidence completeness."]
    if data.get('assessment_status') == 'partial':
        lines.insert(0, 'Partial AI assessment — overall score unavailable; no overall risk tier assigned.')
    if provenance.get('schema_version') not in (3,):
        lines.append('Evidence status not recorded (legacy assessment).')
    sample = provenance.get("sampled_findings")
    if isinstance(sample, list):
        count, total = len(sample), data.get("total_findings")
        lines.append(f"Sampled findings: {count} of {total}. " + (
            "All counted findings were included; text may still be limited." if count == total else
            "The model did not receive every finding." if isinstance(total, int) and count < total else
            "Sampling counts cannot be reconciled; inspect captured evidence."))
    else:
        lines.append("Sampling coverage is not recorded.")
    if provenance.get("evidence_limitation"):
        lines.append(str(provenance["evidence_limitation"]))
    return lines


def _report_error_message(exc: Exception) -> str:
    """Turn Anthropic's exhausted-credit response into a clear, actionable failure."""
    message = str(exc)
    lowered = message.lower()
    if "credit balance is too low" in lowered or "insufficient credits" in lowered:
        return (
            "Anthropic rejected report generation because the API account has insufficient credits. "
            "Add credits or update the Anthropic billing plan, then generate a new report."
        )
    return message


def queue_report_generation(
    db: Session,
    org_id: uuid.UUID,
    title: str,
    user_id: uuid.UUID | None = None,
    frameworks: Sequence[str] | None = None,
    period_start=None,
    period_end=None,
    idempotency_key: str | None = None,
) -> Report:
    """Queues a new audit report generation job for the background worker."""
    from app.services.knowledge_service import require_active_org, report_target
    require_active_org(db, org_id, lock=True)
    require_report_consent(db, org_id)
    fw_str = ",".join(f.strip().upper() for f in (frameworks or ["CIS", "NIST", "ISO"]))
    fingerprint = hashlib.sha256(json.dumps([title, sorted(fw_str.split(",")),
        str(period_start), str(period_end), report_target()], separators=(",", ":")).encode()).hexdigest()
    if idempotency_key is not None:
        if not 1 <= len(idempotency_key) <= 128 or not idempotency_key.strip():
            raise ValueError("Idempotency-Key must contain 1 to 128 characters")
        lock = int.from_bytes(hashlib.sha256(f"report:{org_id}:{idempotency_key}".encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        existing = db.scalar(select(Report).where(Report.org_id == org_id, Report.idempotency_key == idempotency_key))
        if existing:
            if existing.request_hash != fingerprint:
                raise ValueError("Idempotency-Key was already used with different report parameters")
            db.commit()
            return existing
    report = Report(
        id=uuid.uuid4(),
        org_id=org_id,
        title=title,
        idempotency_key=idempotency_key,
        request_hash=fingerprint if idempotency_key is not None else None,
        data={"_processing_target": report_target()},
        frameworks=fw_str,
        status=ReportStatus.pending,
        started_by=user_id,
        period_start=period_start,
        period_end=period_end,
        format="json",
        created_at=datetime.now(timezone.utc),
    )
    db.add(report)
    actor = db.get(User, user_id) if user_id else None
    record_event(
        db,
        "report_queued",
        org_id=org_id,
        actor=actor,
        item=title,
        details={"frameworks": fw_str, "report_id": str(report.id)},
    )
    db.commit()
    db.refresh(report)

    logger.info("Queued audit report %r (%s) for org %s", title, report.id, org_id)
    return report


def purge_expired_reports(db: Session) -> int:
    """Delete terminal snapshots by completion time, never pending/running jobs.

    Existing evidence links cascade with the report. Idempotency keys expire
    with retention/deletion; clients must use a fresh key for each new intent.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.REPORT_RETENTION_DAYS)
    ids = db.scalars(select(Report.id).where(
        Report.status.notin_([ReportStatus.pending, ReportStatus.running]),
        func.coalesce(Report.generated_at, Report.cancel_requested_at, Report.heartbeat_at,
            Report.run_started_at, Report.created_at) < cutoff,
    ).with_for_update(skip_locked=True).limit(500)).all()
    if not ids:
        return 0
    db.execute(delete(Report).where(Report.id.in_(ids)))
    db.commit()
    return len(ids)


def create_rule_based_test_report(
    db: Session,
    org_id: uuid.UUID,
    title: str,
    user_id: uuid.UUID | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> Report:
    """Create a completed, explicitly non-AI report for configured UI testing."""
    if period_start and period_end and period_start > period_end:
        raise ValueError("period_start must not be after period_end")

    finding_filters = [Finding.org_id == org_id, Finding.archived_at.is_(None)]
    if period_start:
        finding_filters.append(Finding.created_at >= datetime.combine(period_start, time.min, timezone.utc))
    if period_end:
        finding_filters.append(Finding.created_at < datetime.combine(period_end + timedelta(days=1), time.min, timezone.utc))

    counts: scoring_service.SeverityCounts = {}
    severity_totals = {severity.value: 0 for severity in Severity}
    for domain, severity, count in db.query(Finding.domain, Finding.severity, func.count()).filter(
        *finding_filters
    ).group_by(Finding.domain, Finding.severity):
        counts.setdefault(domain, {})[severity] = count
        severity_totals[severity.value] += count

    domain_scores = scoring_service.score_all_from_counts(counts)
    overall, _overall_scoring_tier = scoring_service.overall_score(domain_scores)
    overall_score = round(overall)
    domains = [
        DomainScoreAI(
            domain=domain,
            score=round(score),
            tier=_snapshot_tier(round(score)),
            justification=f"Rule-based test score from active findings: {justification}",
            weaknesses=[justification] if counts.get(domain) else [],
        )
        for domain, (score, _tier, justification) in domain_scores.items()
    ]
    remediations = []
    for domain, by_severity in counts.items():
        severity = next((item for item in Severity if by_severity.get(item)), Severity.low)
        priority = {
            Severity.critical: "Critical",
            Severity.high: "High",
            Severity.medium: "Medium",
            Severity.low: "Low",
        }[severity]
        remediations.append(
            RemediationActionAI(
                title=f"Review {domain.value.replace('_', ' ')} findings",
                description=f"Review and address {sum(by_severity.values())} active finding(s) in this domain.",
                priority=priority,
                domain=domain,
                estimated_effort="Moderate",
                expected_impact="Reduce the active finding count and improve the rule-based score.",
                confidence=None, affected_finding_ids=[], affected_asset_ids=[],
            )
        )

    total_findings = sum(severity_totals.values())
    asset_count = db.scalar(
        select(func.count(Asset.id)).where(Asset.org_id == org_id, Asset.archived_at.is_(None))
    ) or 0
    generated_at = datetime.now(timezone.utc)
    period = (
        f"between {period_start.isoformat()} and {period_end.isoformat()}"
        if period_start and period_end
        else f"on or after {period_start.isoformat()}" if period_start
        else f"on or before {period_end.isoformat()}" if period_end
        else "in the selected period"
    )
    snapshot = AuditReportSnapshot(
        title=title,
        executive_summary=(
            "TEST-ONLY RULE-BASED REPORT. No AI model or external provider was used. "
            f"The deterministic scoring rules produced a resilience score of {overall_score}/100 "
            f"from {total_findings} active finding(s)."
        ),
        overall_score=overall_score,
        overall_tier=_snapshot_tier(overall_score),
        resilience_summary=(
            f"This test snapshot uses the configured deterministic risk scoring rules and the organization's "
            f"current inventory. It includes {asset_count} active asset(s) and findings {period}. "
            "No CIS, NIST, or ISO control evaluation was performed."
        ),
        domains=domains,
        remediations=remediations,
        total_assets=asset_count,
        total_findings=total_findings,
        findings_by_severity=severity_totals,
        frameworks_evaluated=[],
        provenance={
            "assessment_type": "rule_based_test",
            "method": "AuditMind deterministic finding severity scoring",
            "version": "rule-v1",
            "captured_at": generated_at.isoformat(),
            "external_processing": False,
            "framework_evaluation": "not performed",
            "period_semantics": "currently active findings created within inclusive UTC dates; current inventory",
            "period_start": period_start.isoformat() if period_start else None,
            "period_end": period_end.isoformat() if period_end else None,
        },
    )
    report = Report(
        id=uuid.uuid4(),
        org_id=org_id,
        title=title,
        period_start=period_start,
        period_end=period_end,
        frameworks=None,
        status=ReportStatus.completed,
        generated_at=generated_at,
        format="json",
        data=snapshot.model_dump(mode="json"),
        started_by=user_id,
        created_at=generated_at,
    )
    db.add(report)
    actor = db.get(User, user_id) if user_id else None
    record_event(
        db,
        "report_test_generated",
        org_id=org_id,
        actor=actor,
        item=title,
        details={"report_id": str(report.id), "overall_score": overall_score, "method": "rule-v1"},
    )
    db.commit()
    db.refresh(report)
    logger.info("Created rule-based test report %r (%s) for org %s", title, report.id, org_id)
    return report


def process_report_job(db: Session, report_id: uuid.UUID) -> Report:
    """Executes the AI audit report pipeline for a single report. Called by the worker."""
    report = db.get(Report, report_id)
    if not report:
        raise ValueError(f"Report {report_id} not found")

    if report.status in (ReportStatus.completed, ReportStatus.generated):
        return report

    if report.cancel_requested_at:
        report.status = ReportStatus.failed
        report.heartbeat_at = datetime.now(timezone.utc)
        report.error_message = "Generation cancelled by user"
        db.commit()
        return report

    report.status = ReportStatus.running
    report.run_started_at = datetime.now(timezone.utc)
    report.heartbeat_at = datetime.now(timezone.utc)
    db.commit()

    start_time = datetime.now(timezone.utc)

    try:
        from app.services.knowledge_service import report_target
        from app.services.report_provider import identity
        pinned = (report.data or {}).get("_processing_target")
        if pinned != report_target() and (pinned is not None or identity()["provider"] != "anthropic"):
            raise ValueError("Queued report processing target changed; queue a new report")
        processing_target = report_target()
        require_report_consent(db, report.org_id)
        fw_list = [f.strip() for f in (report.frameworks or "CIS,NIST,ISO").split(",") if f.strip()]
        snapshot = generate_ai_audit_snapshot(
            db=db,
            org_id=report.org_id,
            report_title=report.title,
            frameworks=fw_list,
            period_start=report.period_start,
            period_end=report.period_end,
            report_id=report.id,
        )

        db.refresh(report, with_for_update=True)
        if report_target() != processing_target:
            raise ValueError("Report processing target changed before publication")
        if report.cancel_requested_at or report.status != ReportStatus.running:
            db.commit()
            return report

        report.data = snapshot.model_dump(mode="json")
        report.status = ReportStatus.completed
        report.generated_at = datetime.now(timezone.utc)
        report.error_message = None

        # Record activity event
        duration_s = int((datetime.now(timezone.utc) - start_time).total_seconds())
        actor = db.get(User, report.started_by) if report.started_by else None
        record_event(
            db,
            "report_generated",
            org_id=report.org_id,
            actor=actor,
            item=report.title,
            criticality=Criticality.info,
            details={
                "overall_score": snapshot.overall_score,
                "tier": snapshot.overall_tier.value if snapshot.overall_tier is not None else None,
                "frameworks": fw_list,
                "duration_seconds": duration_s,
            },
        )
        db.commit()
        logger.info(f"Report {report.id} completed successfully ({duration_s}s).")
        return report

    except Exception as exc:
        logger.error("Report %s generation failed (%s)", report_id, type(exc).__name__)
        db.rollback()
        report = db.get(Report, report_id, populate_existing=True, with_for_update=True)
        if report is None:
            raise
        if report.cancel_requested_at or report.status != ReportStatus.running:
            db.commit()
            return report
        report.status = ReportStatus.failed
        report.heartbeat_at = datetime.now(timezone.utc)
        report.error_message = _report_error_message(exc)
        if report.data and "_processing_target" in report.data:
            report.data = None

        actor = db.get(User, report.started_by) if report.started_by else None
        record_event(
            db,
            "report_failed",
            org_id=report.org_id,
            actor=actor,
            item=report.title,
            criticality=Criticality.warning,
            details={"error": report.error_message},
        )
        db.commit()
        raise


def cancel_report_job(db: Session, report_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID | None = None) -> Report:
    """Cancels a pending or running report generation job."""
    report = db.get(Report, report_id, populate_existing=True, with_for_update=True)
    if not report or report.org_id != org_id:
        raise ValueError("Report not found")

    if report.status in (ReportStatus.completed, ReportStatus.failed):
        return report

    report.cancel_requested_at = datetime.now(timezone.utc)
    report.status = ReportStatus.failed
    report.error_message = "Generation cancelled by user"

    actor = db.get(User, user_id) if user_id else (db.get(User, report.started_by) if report.started_by else None)
    record_event(
        db,
        "report_cancelled",
        org_id=org_id,
        actor=actor,
        item=report.title,
        criticality=Criticality.info,
        details={"status": "cancelled"},
    )
    db.commit()
    return report



def render_report_html(report: Report) -> str:
    """Renders a self-contained, standalone, beautifully styled HTML document from the report snapshot."""
    if not report.data:
        return (
            f"<html><body><h1>{escape_html(report.title, quote=True)}</h1>"
            "<p>No snapshot data available.</p></body></html>"
        )

    data = report.data
    if _unsupported_snapshot(data):
        return '<html><body><p>Unsupported assessment schema. Update the application to view this report.</p></body></html>'
    domains = data.get("domains", [])
    remediations = data.get("remediations", [])
    citations = data.get("compliance_citations", [])
    overall_score = escape_html(str(data.get('overall_score') if data.get('overall_score') is not None else 'Not scored'), quote=True)
    overall_tier = str(data.get('overall_tier') or 'No tier assigned').title()
    overall_tier_label = escape_html(overall_tier, quote=True)
    exec_summary = data.get("executive_summary", "")
    resilience_summary = data.get("resilience_summary", "")

    test_report = (data.get("provenance") or {}).get("assessment_type") == "rule_based_test"
    report_kind = "Rule-based test report — no external AI" if test_report else "AI Audit"
    document_brand = "AuditMind Rule-Based Test Report" if test_report else "AuditMind AI"
    tier_colors = {
        "Optimal": "#22c55e",
        "Good": "#3b82f6",
        "Fair": "#eab308",
        "Poor": "#f97316",
        "Critical": "#ef4444",
    }
    tier_color = tier_colors.get(overall_tier, "#3b82f6")

    domains_html = ""
    for d in domains:
        d_name = escape_html(str(d.get("domain", "")).replace("_", " ").title(), quote=True)
        d_score = escape_html(str(d.get('score')) + '/100' if d.get('score') is not None else 'Not scored', quote=True)
        d_tier = escape_html(str(d.get('tier') or 'No tier assigned').title(), quote=True)
        d_just = escape_html(str(d.get("justification", "")), quote=True)
        strengths_li = "".join(
            f"<li>{escape_html(str(strength), quote=True)}</li>" for strength in d.get("strengths", [])
        )
        weaknesses_li = "".join(
            f"<li>{escape_html(str(weakness), quote=True)}</li>" for weakness in d.get("weaknesses", [])
        )
        domains_html += f"""
        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #334155; padding-bottom:8px; margin-bottom:12px;">
                <h3 style="margin:0; color:#f8fafc;">{d_name}</h3>
                <span class="badge" style="background-color:#1e293b; color:#38bdf8; font-weight:bold; font-size:16px;">{d_score} ({d_tier})</span>
            </div>
            <p style="color:#cbd5e1; font-size:14px; margin-bottom:12px;">{d_just}</p>
            <p>{escape_html(str(d.get('evidence_status') or 'Evidence status not recorded (legacy assessment)'), quote=True)}: {escape_html(str(d.get('evidence_reason') or ''), quote=True)}</p>
            <p>Evidence references: {escape_html(', '.join(map(str, d.get('citation_ids') or [])) or 'Not recorded', quote=True)}</p>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; font-size:13px;">
                <div>
                    <strong style="color:#4ade80;">Strengths:</strong>
                    <ul style="color:#94a3b8; padding-left:18px; margin-top:4px;">{strengths_li or ('<li>Not assessed by this test report</li>' if test_report else '<li>Baseline controls observed</li>')}</ul>
                </div>
                <div>
                    <strong style="color:#f87171;">Key Gaps:</strong>
                    <ul style="color:#94a3b8; padding-left:18px; margin-top:4px;">{weaknesses_li or '<li>None reported</li>'}</ul>
                </div>
            </div>
        </div>
        """

    remed_html = ""
    for r in remediations:
        evidence_html = "<br/>".join(escape_html(line, quote=True) for line in _remediation_evidence_lines(r))
        prio = r.get("priority", "Medium")
        prio_color = "#ef4444" if prio == "Critical" else "#f97316" if prio == "High" else "#38bdf8"
        ctrls = ", ".join(escape_html(str(control), quote=True) for control in r.get("related_controls", []))
        remed_html += f"""
        <div class="card" style="border-left:4px solid {prio_color};">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <div>
                    <h4 style="margin:0 0 4px 0; color:#f8fafc;">{escape_html(str(r.get('title', '')), quote=True)}</h4>
                    <span style="font-size:12px; color:#94a3b8;">Domain: <strong>{escape_html(str(r.get('domain', '')).replace('_', ' ').title(), quote=True)}</strong> | Effort: <strong>{escape_html(str(r.get('estimated_effort', '')), quote=True)}</strong></span>
                </div>
                <span class="badge" style="background-color:{prio_color}22; color:{prio_color}; border:1px solid {prio_color}44;">{escape_html(str(prio), quote=True)}</span>
            </div>
            <p style="color:#cbd5e1; font-size:14px; margin:8px 0;">{escape_html(str(r.get('description', '')), quote=True)}</p>
            <div style="font-size:12px; color:#64748b;">
                <strong>Expected Impact:</strong> {escape_html(str(r.get('expected_impact', '')), quote=True)}<br/>
                <strong>Related controls (descriptive):</strong> <span style="color:#38bdf8;">{ctrls or 'General'}</span><br/>
                {evidence_html}
            </div>
        </div>
        """

    citations_html = ""
    for c in citations:
        citations_html += f"""
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:6px; padding:12px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <strong style="color:#38bdf8;">{escape_html(str(c.get('control_id', '')), quote=True)} ({escape_html(str(c.get('framework', '')), quote=True)})</strong>
                <p>Evidence ID: {escape_html(str(c.get('citation_id', 'Not recorded')), quote=True)}</p>
                <span style="font-size:11px; color:#64748b;">{escape_html(str(c.get('content_ref', '')), quote=True)}</span>
            </div>
            <div style="font-size:13px; color:#e2e8f0; font-weight:600;">{escape_html(str(c.get('title', '')), quote=True)}</div>
            <div>{escape_html(str(c.get('source', '')), quote=True)} · {escape_html(str(c.get('version', '')), quote=True)} · {escape_html(str(c.get('citation_id', '')), quote=True)} · {escape_html(str(c.get('content_kind', '')), quote=True)}</div>
            <div style="font-size:12px; color:#94a3b8; margin-top:4px;">{escape_html(str(c.get('content', '')), quote=True)}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{escape_html(report.title, quote=True)} - {document_brand}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0b0f19; color: #f8fafc; margin: 0; padding: 40px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1e293b; padding-bottom: 24px; margin-bottom: 32px; }}
        .score-box {{ text-align: center; background: #1e293b; border-radius: 12px; padding: 20px 32px; border: 2px solid {tier_color}; }}
        .score-val {{ font-size: 48px; font-weight: 800; color: {tier_color}; line-height: 1; }}
        .score-lbl {{ font-size: 14px; text-transform: uppercase; letter-spacing: 1px; color: #94a3b8; margin-top: 6px; }}
        .card {{ background: #131d2f; border: 1px solid #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 16px; }}
        .badge {{ border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: 600; display: inline-block; }}
        h2 {{ color: #38bdf8; font-size: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 8px; margin-top: 32px; }}
        @media print {{
            body {{ background: #fff; color: #000; padding: 20px; }}
            .card {{ background: #f8fafc; border: 1px solid #e2e8f0; color: #000; break-inside: avoid; }}
            .score-box {{ background: #f1f5f9; }}
            h2 {{ color: #0284c7; }}
        }}
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <h1 style="margin:0 0 8px 0; font-size:28px;">{escape_html(report.title, quote=True)}</h1>
            <p style="margin:0; color:#94a3b8; font-size:14px;">
                {escape_html(report_kind, quote=True)} | {f"Frameworks: <strong>{escape_html(report.frameworks, quote=True)}</strong> | " if report.frameworks else ""}Generated: {report.generated_at.strftime('%B %d, %Y') if report.generated_at else 'In progress'}
            </p>
        </div>
        <div class="score-box">
            <div class="score-val">{overall_score}</div>
            <div class="score-lbl">{overall_tier_label} Resilience</div>
        </div>
    </div>

    <section aria-label="Assessment interpretation">
        {''.join('<p>' + escape_html(line, quote=True) + '</p>' for line in _assessment_display_lines(data))}
    </section>
    <h2>Executive Summary</h2>
    <div class="card">
        <p style="font-size:15px; line-height:1.6; color:#e2e8f0; margin-top:0;">{escape_html(str(exec_summary), quote=True)}</p>
        <p style="font-size:14px; line-height:1.5; color:#94a3b8; margin-bottom:0;">{escape_html(str(resilience_summary), quote=True)}</p>
    </div>

    <h2>Domain Breakdown</h2>
    <div style="display:grid; grid-template-columns:1fr; gap:12px;">
        {domains_html}
    </div>

    <h2>Prioritized Remediation Roadmap</h2>
    <div style="display:grid; grid-template-columns:1fr; gap:12px;">
        {remed_html}
    </div>

    <h2>{'Framework controls not assessed' if test_report else 'Compliance & Standards Citations (RAG)'}</h2>
    <div>
        {citations_html or ('<p style="color:#64748b;">This rule-based test report does not evaluate framework controls.</p>' if test_report else '<p style="color:#64748b;">No direct citations attached.</p>')}
        <h2>Evidence provenance</h2>
        <pre style="white-space:pre-wrap;">{escape_html(json.dumps(data.get('provenance') or {'status': 'Legacy report: full provenance was not captured'}, indent=2), quote=True)}</pre>
    </div>
</div>
</body>
</html>
"""
    return html


def render_report_pdf(report: Report) -> bytes:
    """Renders a report snapshot as a standalone PDF without browser-side printing."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=report.title,
    )
    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=base_styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#102a43"),
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "ReportSection",
        parent=base_styles["Heading2"],
        textColor=colors.HexColor("#075985"),
        spaceBefore=12,
        spaceAfter=5,
    )
    body_style = ParagraphStyle("ReportBody", parent=base_styles["BodyText"], leading=14, spaceAfter=5)
    small_style = ParagraphStyle("ReportSmall", parent=body_style, fontSize=8, textColor=colors.HexColor("#52606d"))

    def safe_text(value: object) -> str:
        text = str(value if value is not None else "")
        return escape_html(text.encode("cp1252", errors="replace").decode("cp1252")).replace("\n", "<br/>")

    def paragraph(value: object, style: ParagraphStyle = body_style) -> Paragraph:
        return Paragraph(safe_text(value), style)

    data = report.data or {}
    if _unsupported_snapshot(data):
        document.build([paragraph('Unsupported assessment schema. Update the application to view this report.')])
        return buffer.getvalue()
    provenance = data.get("provenance") or {}
    is_test_report = provenance.get("assessment_type") == "rule_based_test"
    story = [
        paragraph(report.title, title_style),
        paragraph(
            "Rule-based test report — no external AI"
            if is_test_report
            else "AI Audit Report",
            small_style,
        ),
        paragraph(
            f"Frameworks: {report.frameworks or 'Not specified'} · Generated: "
            f"{report.generated_at.strftime('%B %d, %Y') if report.generated_at else 'Not available'}",
            small_style,
        ),
        Spacer(1, 0.12 * inch),
        paragraph(
            (f"Overall resilience score: {data['overall_score']} / 100 ({str(data.get('overall_tier') or 'Unknown').title()} risk tier)"
             if data.get('overall_score') is not None else 'Overall resilience score unavailable; no overall risk tier assigned'),
            section_style,
        ),
        paragraph("Executive Summary", section_style),
        paragraph(data.get("executive_summary") or "No executive summary is available."),
        paragraph("Resilience Summary", section_style),
        paragraph(data.get("resilience_summary") or "No resilience summary is available."),
    ]

    domains = data.get("domains") or []
    if domains:
        story.append(paragraph("Domain Assessments", section_style))
        for domain in domains:
            story.append(
                paragraph(
                    f"{str(domain.get('domain', 'Domain')).replace('_', ' ').title()} — " +
                    (f"{domain['score']}/100 · {str(domain.get('tier') or 'Unknown').title()}" if domain.get('score') is not None else 'Not scored — no tier assigned'),
                    base_styles["Heading3"],
                )
            )
            story.append(paragraph(domain.get("justification") or "No justification provided."))
            story.append(paragraph(f"{domain.get('evidence_status') or 'Evidence status not recorded (legacy assessment)'}: {domain.get('evidence_reason') or ''}", small_style))
            story.append(paragraph("Evidence references: " + (", ".join(map(str, domain.get("citation_ids") or [])) or "Not recorded"), small_style))
            for label, items in (
                ("Strengths", domain.get("strengths") or []),
                ("Key gaps", domain.get("weaknesses") or []),
            ):
                if items:
                    story.append(paragraph(label, base_styles["Heading4"]))
                    story.extend(paragraph(f"• {item}") for item in items)

    story[2:2] = [paragraph(line, small_style) for line in _assessment_display_lines(data)]
    remediations = data.get("remediations") or []
    if remediations:
        story.append(paragraph("Recommended Remediations", section_style))
        for remediation in remediations:
            story.append(paragraph(remediation.get("title") or "Remediation", base_styles["Heading3"]))
            story.append(
                paragraph(
                    f"Priority: {remediation.get('priority', 'Not specified')} · "
                    f"Domain: {str(remediation.get('domain', 'Not specified')).replace('_', ' ').title()} · "
                    f"Effort: {remediation.get('estimated_effort', 'Not specified')}"
                )
            )
            story.append(paragraph(remediation.get("description") or "No description provided."))
            for line in _remediation_evidence_lines(remediation):
                story.append(paragraph(line, small_style))
            if remediation.get("expected_impact"):
                story.append(paragraph(f"Expected impact: {remediation['expected_impact']}"))
            if remediation.get("related_controls"):
                story.append(paragraph(f"Related controls (descriptive): {', '.join(map(str, remediation['related_controls']))}"))

    citations = data.get("compliance_citations") or []
    if citations:
        story.append(paragraph("Evidence and Citations", section_style))
        for citation in citations:
            heading = (
                f"{citation.get('control_id', 'Reference')} "
                f"({citation.get('framework', 'Standard')}) — {citation.get('title', '')}"
            )
            story.append(paragraph(heading, base_styles["Heading3"]))
            story.append(paragraph(f"Evidence ID: {citation.get('citation_id', 'Not recorded')}", small_style))
            for key in ("source", "version", "content_ref", "content"):
                if citation.get(key):
                    story.append(paragraph(f"{key.replace('_', ' ').title()}: {citation[key]}"))
    elif is_test_report:
        story.extend(
            [
                paragraph("Evidence and Citations", section_style),
                paragraph("This rule-based test report does not evaluate framework controls."),
            ]
        )

    if provenance:
        story.append(paragraph("Evidence Provenance", section_style))
        provenance_rows = [
            [paragraph(safe_text(key), small_style), paragraph(value, small_style)]
            for key, value in provenance.items()
        ]
        # A bounded evidence sample can still exceed one PDF page. Allow
        # Paragraph cells to split rather than rejecting a tall provenance row.
        table = Table(provenance_rows, colWidths=[1.65 * inch, 4.9 * inch], repeatRows=0, splitInRow=1)
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eaf2f8")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bcccdc")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
    elif not data:
        story.append(paragraph("No snapshot data is available for this report."))

    document.build(story)
    return buffer.getvalue()
