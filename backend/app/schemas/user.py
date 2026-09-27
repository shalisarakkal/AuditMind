import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    auth_provider: str
    created_at: datetime


class MemberRead(UserRead):
    """A user as a member of one org, with their role there."""

    role: UserRole
