import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool
from app.models.enums import UserRole

LogoSize = Literal["small", "medium", "large"]


class OrganizationBrandingRead(BaseModel):
    show_name_in_header: bool
    header_logo_size: LogoSize
    header_name_size: LogoSize


class OrganizationBrandingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    show_name_in_header: StrictBool
    expected_show_name_in_header: StrictBool
    header_logo_size: LogoSize | None = None
    expected_header_logo_size: LogoSize | None = None
    header_name_size: LogoSize | None = None
    expected_header_name_size: LogoSize | None = None


class OrganizationCreate(BaseModel):
    name: str
    industry: str | None = None
    size: str | None = None


class OrganizationLogoRead(BaseModel):
    version: str | None
    image_data_url: str | None


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
    # "member", or "sysadmin": the Sysadmin reading an org it doesn't belong
    # to (as a viewer).
    access: Literal["member", "sysadmin"] = "member"
    # Archived: read-only for everyone until the Sysadmin restores it.
    archived: bool = False

