import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.user import User
from app.schemas.ai import ClaudeTestRequest, ClaudeTestResponse
from app.services.claude_service import SYSTEM_PROMPT, ask_claude
from app.services.claude_service import ClaudeOperationalError, provider_error_message, provider_error_status

router = APIRouter(prefix="/ai/claude", tags=["ai"])


def _admin_somewhere(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    """Admins only (of any org): every call costs money."""
    is_admin = (
        db.query(OrgMembership).filter(OrgMembership.user_id == user.id, OrgMembership.role == UserRole.admin).first()
    )
    if is_admin is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return user


@router.post(
    "/test",
    response_model=ClaudeTestResponse,
    responses={
        429: {"description": "Organization Claude quota exceeded"},
        502: {"description": "Claude returned an error"},
        503: {"description": "Claude isn't configured, can't be reached, or is busy"},
        504: {"description": "Claude didn't answer in time (CLAUDE_TIMEOUT_SECONDS, after retries)"},
    },
)
def test_claude(payload: ClaudeTestRequest, user: User = Depends(_admin_somewhere),
                db: Session = Depends(get_db)) -> ClaudeTestResponse:
    """Smoke test: confirms the Claude API key and SDK wiring work. Admins
    only; provider problems come back as 502/503/504 with a plain message."""
    if settings.REPORT_AI_PROVIDER != "anthropic":
        raise HTTPException(status_code=503, detail="Use the consent-controlled report workflow for OpenRouter")
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Claude isn't configured (no API key)")
    try:
        membership = db.query(OrgMembership).filter(
            OrgMembership.user_id == user.id, OrgMembership.role == UserRole.admin
        ).order_by(OrgMembership.org_id).first()
        response = ask_claude(payload.prompt, system=SYSTEM_PROMPT,
            org_id=membership.org_id, usage_bind=db.get_bind())
    except ClaudeOperationalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except anthropic.APIError as exc:
        raise HTTPException(status_code=provider_error_status(exc), detail=provider_error_message(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Claude returned an invalid response") from exc
    return ClaudeTestResponse(model=settings.CLAUDE_MODEL, response=response)
