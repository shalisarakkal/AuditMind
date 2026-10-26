import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ArchiveProgress, Domain, Severity
from app.schemas.paging import Page
from app.schemas.finding_workflow import WorkflowStatus


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
    workflow_status: WorkflowStatus = "open"
    workflow_version: int = 0
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None
    risk_review_date: date | None = None
    due_timezone: str | None = None
    due_expires_at: datetime | None = None
    risk_review_timezone: str | None = None
    risk_review_expires_at: datetime | None = None
    created_at: datetime
    # An event log's finding: the events it sums up (else null).
    event_count: int | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    details: dict | None = None


class FindingListItem(FindingRead):
    """A finding in the org's list, with its asset's identifiers for display
    (a cloud resource may have only a cloud ID)."""

    asset_hostname: str | None = None
    assignee_label: str | None = None
    asset_ip: str | None = None
    asset_cloud_id: str | None = None
    # A manual finding whose archive hasn't finished: running now, or stopped
    # part-way; and that archive (restore it to undo what it archived).
    archiving: ArchiveProgress | None = None
    archiving_batch_id: uuid.UUID | None = None


class FindingPage(Page[FindingListItem]):
    # Findings per domain for the same search (whatever the domain filter),
    # for the list's domain filter.
    domain_counts: dict[Domain, int]


class FindingAssigneeFacet(BaseModel):
    value: str
    label: str


class FindingFacets(BaseModel):
    """The values the findings list's source pick-list can offer; "" stands
    for "no source"."""

    source: list[str]
    has_manual_findings: bool = False
    workflow_status: list[WorkflowStatus] = []
    assignee: list[FindingAssigneeFacet] = []
