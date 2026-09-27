from pydantic import BaseModel


class ClaudeTestRequest(BaseModel):
    prompt: str


class ClaudeTestResponse(BaseModel):
    model: str
    response: str
