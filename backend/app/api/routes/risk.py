import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_org_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.risk_score import RiskScore
from app.schemas.risk_score import RiskAssessmentResult, RiskScoreRead
from app.services.scoring_service import score_all_domains, overall_score

router = APIRouter(prefix="/orgs/{org_id}/risk", tags=["risk"])


@router.post("/score", response_model=RiskAssessmentResult)
def run_risk_assessment(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> RiskAssessmentResult:
    """Rule-based v1 scoring (RISL_SCORING.md). Claude-driven qualitative scoring
    with RAG-backed standards citations lands in a later milestone (PROMPTS_CLAUDE.md)."""
    findings = db.query(Finding).filter(Finding.org_id == org_id).all()
    domain_scores = score_all_domains(findings)
    overall, tier = overall_score(domain_scores)

    saved: list[RiskScore] = []
    for domain, (score, domain_tier, justification) in domain_scores.items():
        risk_score = RiskScore(
            org_id=org_id,
            dimension=domain,
            score=score,
            tier=domain_tier,
            justification=justification,
        )
        db.add(risk_score)
        saved.append(risk_score)
    db.commit()
    for risk_score in saved:
        db.refresh(risk_score)

    remediation = [
        f"Address {domain.value.replace('_', ' ')} gaps to move out of {domain_tier.value} tier."
        for domain, (score, domain_tier, _just) in domain_scores.items()
        if domain_tier.value in ("high", "critical")
    ]

    return RiskAssessmentResult(
        domains=[RiskScoreRead.model_validate(rs) for rs in saved],
        overall_score=overall,
        overall_tier=tier,
        remediation=remediation,
    )
