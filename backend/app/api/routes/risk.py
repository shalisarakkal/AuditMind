import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import authorize_org_write, require_org_role
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.risk_score import RiskScore
from app.schemas.risk_score import RiskAssessmentResult, RiskScoreRead
from app.services.scoring_service import count_org_findings, overall_score, score_all_from_counts
from app.services import status_scoring

router = APIRouter(prefix="/orgs/{org_id}/risk", tags=["risk"])


@router.post("/score", response_model=RiskAssessmentResult)
def run_risk_assessment(
    org_id: uuid.UUID,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> RiskAssessmentResult:
    """Rule-based v1 scoring (RISL_SCORING.md). Claude-driven qualitative scoring
    with RAG-backed standards citations lands in a later milestone (PROMPTS_CLAUDE.md)."""
    actor_id = membership.user_id
    engine = db.get_bind()
    db.rollback()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with Session(bind=connection) as capture:
            counts, policy = status_scoring.apply_policy(capture, org_id, count_org_findings(capture, org_id), capture_basis=True)
    if policy['not_assessed']:
        raise HTTPException(409, "Not assessed: verified exclusions leave no current-risk findings; evidence coverage is not established")
    domain_scores = score_all_from_counts(counts)
    overall, tier = overall_score(domain_scores)
    # Snapshot reads release the original authorization transaction. Recheck
    # and fence current permissions/lifecycle before publishing persisted scores.
    authorize_org_write(db, org_id, actor_id, (UserRole.admin, UserRole.auditor))

    saved: list[RiskScore] = []
    for domain, (score, domain_tier, justification) in domain_scores.items():
        risk_score = RiskScore(
            org_id=org_id,
            dimension=domain,
            score=score,
            tier=domain_tier,
            justification=justification,
            scoring_context=policy,
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
