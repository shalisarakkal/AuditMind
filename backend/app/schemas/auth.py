from datetime import datetime

from pydantic import BaseModel

from app.schemas.types import LowerEmail


class RegisterRequest(BaseModel):
    org_name: str
    email: LowerEmail
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: LowerEmail
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Seconds the access token lasts; the app renews it before then.
    expires_in: int
    # Every page but Change password is refused until it's changed (a
    # temporary password, or one past its expiry).
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class Me(BaseModel):
    id: str
    email: str
    name: str | None
    is_sysadmin: bool
    must_change_password: bool
    # When the password must be changed by (the rule's expiry), if ever.
    password_expires_at: datetime | None


class PasswordRulesRead(BaseModel):
    """The rule a new password must meet, for the Change password page."""

    rule: str
    min_length: int
    max_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_symbol: bool
    history_count: int
    expiry_days: int
    # Setting -> the org that asks for its stricter value.
    required_by: dict[str, str]
