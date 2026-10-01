"""Activity: the org's event log (read-only), and whether the background
worker is running."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_org_member
from app.api.paging import (
    DateRange,
    PageParams,
    SortOrder,
    any_of,
    contains,
    date_range,
    labelled,
    one_of,
    ordered,
    page_params,
)
from app.core.config import settings
from app.db.session import get_db
from app.models.enums import Criticality
from app.models.event import Event, WorkerStatus
from app.models.membership import OrgMembership
from app.models.user import User
from app.schemas.paging import Page

router = APIRouter(tags=["activity"])


class EventRead(BaseModel):
    id: uuid.UUID
    type: str
    item: str | None
    actor_id: uuid.UUID | None
    actor_label: str
    started_at: datetime
    ended_at: datetime
    outcome: str
    criticality: Criticality
    counts: dict | None
    details: dict | None


class EventFacets(BaseModel):
    """What the Activity pick-lists can offer."""

    type: list[str]
    result: list[str]


class WorkerStatusRead(BaseModel):
    running: bool
    # Its last check-in; null if it has never run.
    last_seen: datetime | None


def _in_org(org_id: uuid.UUID):
    # The org's own events, and those of the whole system (the worker).
    return or_(Event.org_id == org_id, Event.org_id.is_(None))


# The event types' names as Activity shows them (frontend/src/lib/activity.ts),
# so the search box finds "Signed in" by what's on screen.
_TYPE_LABELS = {
    "import": "Import",
    "repeat_upload": "Same file imported again",
    "archive": "Archive",
    "restore": "Restore",
    "purge": "Purge",
    "asset_added": "Asset added",
    "finding_added": "Finding added",
    "settings_changed": "Settings changed",
    "profile_created": "Import profile created",
    "profile_updated": "Import profile changed",
    "profile_deleted": "Import profile deleted",
    "member_added": "Member added",
    "member_removed": "Member removed",
    "role_changed": "Role changed",
    "name_changed": "Name changed",
    "password_reset": "Password reset",
    "account_unlocked": "Account unlocked",
    "registered": "Signed up",
    "login": "Signed in",
    "login_failed": "Failed sign-in",
    "logout": "Signed out",
    "password_changed": "Password changed",
    "account_locked": "Account locked",
    "event_cleanup": "Old activity deleted",
    "worker_started": "Background worker started",
    "worker_stopped": "Background worker stopped",
}

EventSort = Literal["when", "event", "item", "who", "result", "criticality"]
_CRITICALITY_RANK = case(*((Event.criticality == c, rank) for rank, c in enumerate(Criticality)))
_SORT_COLUMNS = {
    "when": Event.started_at,
    "event": Event.type,
    "item": func.lower(Event.item),
    "who": func.lower(Event.actor_label),
    "result": Event.outcome,
    # Most critical first when descending.
    "criticality": _CRITICALITY_RANK,
}


@router.get("/orgs/{org_id}/events", response_model=Page[EventRead])
def list_events(
    org_id: uuid.UUID,
    q: str | None = Query(None, description="Search the shown columns: event, item or who contains this"),
    type: list[str] | None = Query(None, description="Event type is one of these"),
    item: str | None = Query(None, description="The item (file, asset...) contains this"),
    who: str | None = Query(None, description="Who did it (a name, System or Unknown) contains this"),
    result: list[str] | None = Query(None, description="Outcome is one of these: completed, failed, stopped"),
    criticality: list[Criticality] | None = Query(None, description="Criticality is one of these"),
    dates: DateRange = Depends(date_range),
    sort: EventSort = Query("when", description="Column to sort by"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> Page[EventRead]:
    """What happened in the org, newest first by default. Every member can
    read it; nothing can change it."""
    conditions = [_in_org(org_id)]
    for match in (
        any_of(contains(q, Event.item, Event.actor_label), labelled(q, Event.type, _TYPE_LABELS)),
        one_of(Event.type, type),
        contains(item, Event.item),
        contains(who, Event.actor_label),
        one_of(Event.outcome, result),
        one_of(Event.criticality, [c.value for c in criticality] if criticality else None),
    ):
        if match is not None:
            conditions.append(match)
    conditions += dates.conditions(Event.started_at)
    total = db.scalar(select(func.count()).select_from(Event).where(*conditions))
    rows = db.scalars(
        select(Event)
        .where(*conditions)
        .order_by(ordered(_SORT_COLUMNS[sort], order), Event.started_at.desc(), Event.id)
        .offset(page.offset)
        .limit(page.limit)
    ).all()
    return Page(items=[EventRead.model_validate(e, from_attributes=True) for e in rows], total=total)


@router.get("/orgs/{org_id}/events/facets", response_model=EventFacets)
def event_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> EventFacets:
    """The values the pick-lists can offer: event types and results seen."""
    types = db.scalars(select(Event.type).where(_in_org(org_id)).distinct().order_by(Event.type)).all()
    results = db.scalars(select(Event.outcome).where(_in_org(org_id)).distinct().order_by(Event.outcome)).all()
    return EventFacets(type=list(types), result=list(results))


@router.get("/worker-status", response_model=WorkerStatusRead)
def worker_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> WorkerStatusRead:
    """Whether the background worker has checked in lately: while it
    hasn't, large imports and archive jobs wait."""
    status = db.get(WorkerStatus, 1)
    if status is None:
        return WorkerStatusRead(running=False, last_seen=None)
    fresh = datetime.now(timezone.utc) - status.heartbeat_at < timedelta(seconds=settings.WORKER_STALE_SECONDS // 2)
    return WorkerStatusRead(running=fresh, last_seen=status.heartbeat_at)
