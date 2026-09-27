from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.ai import ClaudeTestRequest, ClaudeTestResponse
from app.services.claude_service import SYSTEM_PROMPT, ask_claude
from app.core.config import settings

router = APIRouter(prefix="/ai/claude", tags=["ai"])


@router.post("/test", response_model=ClaudeTestResponse)
def test_claude(payload: ClaudeTestRequest, _: User = Depends(get_current_user)) -> ClaudeTestResponse:
    """Week 1 smoke-test endpoint: confirms the Claude API key and SDK wiring work."""
    response = ask_claude(payload.prompt, system=SYSTEM_PROMPT)
    return ClaudeTestResponse(model=settings.CLAUDE_MODEL, response=response)
