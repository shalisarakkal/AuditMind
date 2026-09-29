import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import Domain, Severity
from app.schemas.paging import Page


class FindingCreate(BaseModel):
    asset_id: uuid.UUID | None = None
    scan_id: uuid.UUID | None = None
    category: str | None = None
    domain: Domain
    severity: Severity
    description: str | None = None
    raw_data: dict | None = None
    source: str | None = None


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    asset_id: uuid.UUID | None
    scan_id: uuid.UUID | None
    category: str | None
    domain: Domain
    severity: Severity
    description: str | None
    source: str | None
    created_at: datetime


class FindingListItem(FindingRead):
    """A finding in the org's list, with its asset's identifiers for display
    (a cloud resource may have only a cloud ID)."""

    asset_hostname: str | None = None
    asset_ip: str | None = None
    asset_cloud_id: str | None = None


class FindingPage(Page[FindingListItem]):
    # Findings per domain for the same search (whatever the domain filter),
    # for the list's domain filter.
    domain_counts: dict[Domain, int]


class FindingFacets(BaseModel):
    """The values the findings list's source pick-list can offer; "" stands
    for "no source"."""

    source: list[str]
