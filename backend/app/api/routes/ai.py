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
        502: {"description": "Claude returned an error"},
        503: {"description": "Claude isn't configured, can't be reached, or is busy"},
        504: {"description": "Claude didn't answer in time (CLAUDE_TIMEOUT_SECONDS, after retries)"},
    },
)
def test_claude(payload: ClaudeTestRequest, _: User = Depends(_admin_somewhere)) -> ClaudeTestResponse:
    """Smoke test: confirms the Claude API key and SDK wiring work. Admins
    only; provider problems come back as 502/503/504 with a plain message."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Claude isn't configured (no API key)")
    try:
        response = ask_claude(payload.prompt, system=SYSTEM_PROMPT)
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Claude refused the API key")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Claude is busy: try again shortly")
    except anthropic.APITimeoutError:  # before APIConnectionError: it's a kind of it
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Claude didn't answer in time")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Couldn't reach Claude")
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Claude returned an error ({exc.status_code})")
    return ClaudeTestResponse(model=settings.CLAUDE_MODEL, response=response)
