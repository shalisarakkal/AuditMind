import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import UserRole


class OrganizationCreate(BaseModel):
    name: str
    industry: str | None = None
    size: str | None = None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    size: str | None
    created_at: datetime


class MyOrganizationRead(OrganizationRead):
    """An org as seen by the current user: the org plus their role in it.
    Drives the org picker."""

    role: UserRole


class MemberAdd(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.viewer
