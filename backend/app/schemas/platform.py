import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import UserRole
from app.schemas.types import LowerEmail, PersonName
from app.schemas.user import MemberStatus

OrgStatus = Literal["active", "archived", "purging"]


class PlatformOrgRead(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    size: str | None
    created_at: datetime
    status: OrgStatus
    archived_at: datetime | None
    members: int
    # Their emails: whom to ask about the org.
    admins: list[str]


class PlatformOrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    industry: str | None = Field(None, max_length=100)
    size: str | None = Field(None, max_length=50)
    # Its first admin: someone new gets a temporary password.
    admin_email: LowerEmail
    admin_name: PersonName | None = None


class PlatformOrgCreated(PlatformOrgRead):
    # Shown once, for a new account; null when the admin already had one.
    temporary_password: str | None
    temp_password_expires_at: datetime | None


class OrgPurge(BaseModel):
    # The org's name, typed again.
    name: str


class UserOrg(BaseModel):
    org_id: uuid.UUID
    name: str
    role: UserRole


class PlatformUserRead(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    created_at: datetime
    status: MemberStatus
    is_sysadmin: bool
    locked_until: datetime | None
    temp_password_expires_at: datetime | None
    orgs: list[UserOrg]


class PlatformUserUpdate(BaseModel):
    """Omitted fields are unchanged."""

    name: PersonName | None = None
    email: LowerEmail | None = None
    active: bool | None = None


class RoleUpdate(BaseModel):
    role: UserRole


class UserFacets(BaseModel):
    status: list[str]


class OrgFacets(BaseModel):
    status: list[str]
