import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import UserRole
from app.schemas.types import LowerEmail, PersonName


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    auth_provider: str
    created_at: datetime


# A person's state, as People shows it (services/people.py, status_of).
MemberStatus = Literal["active", "locked", "must_change_password", "deactivated"]


class MemberRead(UserRead):
    """A user as a member of one org: their role there, when they were added,
    and their account's state."""

    role: UserRole
    added_at: datetime
    status: MemberStatus
    # Locked until then; null while locked: until an admin unlocks it.
    locked_until: datetime | None
    # A temporary password can be used until then.
    temp_password_expires_at: datetime | None
    # Also in other orgs: their name and password are then the Sysadmin's to
    # change, not one org's admins'.
    in_other_orgs: bool


class MemberAdd(BaseModel):
    email: LowerEmail
    # For a new account; someone who already has one keeps their name.
    name: PersonName | None = None
    role: UserRole = UserRole.viewer


class MemberAdded(MemberRead):
    # Shown once to the admin, for a new account; null when the email
    # already had one (they sign in with their existing password).
    temporary_password: str | None


class MemberUpdate(BaseModel):
    """Omitted fields are unchanged."""

    name: PersonName | None = None
    role: UserRole | None = None


class PasswordReset(BaseModel):
    """Shown once to the admin."""

    temporary_password: str
    expires_at: datetime


class MemberFacets(BaseModel):
    role: list[str]
    status: list[str]


class NameUpdate(BaseModel):
    name: PersonName
