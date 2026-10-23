"""Persistent, explicitly simulated evidence-state examples. No inference or consent changes."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
import app.db.base  # noqa: F401: register relationship targets for standalone CLI

from app.models.enums import Domain, ReportStatus, UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.report import Report
from app.models.user import User
from app.schemas.evidence_assessment import EvidenceSnapshot
from app.services.scoring_service import tier_for_score

ORG_NAME = "Evidence examples - SYNTHETIC ONLY"
WARNING = "Synthetic mock: fixed example evidence and scores. No model was called. Not a real audit or operational evidence qualification."
STATES = ("sufficient", "limited", "insufficient", "conflicting")


def example_id(key):
    return uuid5(NAMESPACE_URL, "auditmind:synthetic-evidence-examples:v1:" + key)


def snapshot(state):
    if state not in STATES:
        raise ValueError("Unknown example state")
    domains = []
    for domain in Domain:
        references = [] if state == "insufficient" else ["SYNTHETIC-OBSERVATION-A"]
        if state == "conflicting":
            references.append("SYNTHETIC-OBSERVATION-B")
        domains.append(dict(domain=domain, evidence_status=state,
            evidence_reason=f"Simulated {state} evidence; no real control testing or qualification performed.",
            evidence_finding_ids=[], citation_ids=references,
            score=70 if state == "sufficient" else None,
            tier=tier_for_score(70) if state == "sufficient" else None,
            justification=WARNING, strengths=[], weaknesses=[]))
    citations = [dict(citation_id="SYNTHETIC-OBSERVATION-A", framework="SYNTHETIC",
        title="Invented example observation", content="Invented successful control test; not an actual test result.")]
    if state == "conflicting":
        citations.append(dict(citation_id="SYNTHETIC-OBSERVATION-B", framework="SYNTHETIC",
            title="Invented contradictory observation", content="Invented failed control test for the same scope and period."))
    return EvidenceSnapshot(title=f"SYNTHETIC - {state.title()} evidence example",
        executive_summary=WARNING, resilience_summary=WARNING, domains=domains,
        remediations=[], overall_score=70 if state == "sufficient" else None,
        overall_tier=tier_for_score(70) if state == "sufficient" else None,
        assessment_status="complete" if state == "sufficient" else "partial",
        compliance_citations=[] if state == "insufficient" else citations,
        frameworks_evaluated=["SYNTHETIC"], provenance=dict(schema_version=3,
            assessment_type="synthetic_mock", external_processing=False,
            model="None - fixed synthetic fixture", prompt_version="synthetic-examples-v1",
            captured_at=datetime.now(timezone.utc).isoformat(), sampled_findings=[],
            evidence_limitation=WARNING, evidence_qualification=dict(simulated=True,
                operational_approval=False))).model_dump(mode="json")


def seed_examples(db):
    schema, database = db.execute(text("SELECT current_schema(), current_database()")).one()
    if schema != "auditmind_demo" and not (schema == "public" and database == "auditmind_test"):
        raise ValueError("Evidence examples require the isolated demo schema or exact test database")
    admin = db.scalar(select(User).where(User.email == "demo.admin@example.com"))
    if admin is None:
        raise ValueError("Prepare the demo account first")
    org = db.get(Organization, example_id("organization"))
    if org is None:
        org = Organization(id=example_id("organization"), name=ORG_NAME, industry="Synthetic examples")
        db.add(org)
        db.flush()
        db.add(OrgMembership(user_id=admin.id, org_id=org.id, role=UserRole.admin))
    if org.archived_at or org.purge_requested_at:
        raise ValueError("Example organization is archived or pending purge")
    created = 0
    for state in STATES:
        report = db.get(Report, example_id(state))
        if report:
            if report.org_id != org.id or (report.data or {}).get("provenance", {}).get("assessment_type") != "synthetic_mock":
                raise ValueError("Example identifier belongs to an unrelated report")
            continue  # Preserve user edits and existing snapshots.
        data = snapshot(state)
        db.add(Report(id=example_id(state), org_id=org.id, title=data["title"],
            frameworks="SYNTHETIC", status=ReportStatus.completed, data=data,
            generated_at=datetime.now(timezone.utc), started_by=admin.id))
        created += 1
    db.commit()
    return created
