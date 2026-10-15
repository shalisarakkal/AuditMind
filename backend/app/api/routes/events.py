"""Activity: the org's event log (read-only), and whether the background
worker is running."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_org_member, require_sysadmin
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
from app.models.organization import Organization
from app.models.user import User
from app.services.events import SHARED_SYSTEM_TYPES
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


def _in_org(org: Organization):
    # The org's own events, and the background worker's since the org was
    # created (it runs everyone's uploads); not the platform's.
    return or_(
        Event.org_id == org.id,
        and_(Event.org_id.is_(None), Event.type.in_(SHARED_SYSTEM_TYPES), Event.started_at >= org.created_at),
    )


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
    "org_created": "Organization created",
    "org_archived": "Organization archived",
    "org_restored": "Organization restored",
    "org_purged": "Organization purged",
    "user_deactivated": "Account deactivated",
    "user_reactivated": "Account reactivated",
    "email_changed": "Email changed",
    "sysadmin_created": "Sysadmin created",
    "registered": "Signed up",
    "login": "Signed in",
    "login_failed": "Failed sign-in",
    "logout": "Signed out",
    "password_changed": "Password changed",
    "account_locked": "Account locked",
    "document_uploaded": "Document uploaded",
    "document_index_queued": "Document indexing queued",
    "document_reactivation_queued": "Document version reactivation queued",
    "document_retired": "Document version retired",
    "document_removed": "Document version removed",
    "knowledge_consent_changed": "Document processing consent changed",
    "shared_standards_queued": "Shared standards queued",
    "embedding_profile_changed": "Embedding profile changed",
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


def _event_page(
    db: Session,
    scope,
    *,
    q: str | None,
    type: list[str] | None,
    item: str | None,
    who: str | None,
    result: list[str] | None,
    criticality: list[Criticality] | None,
    dates: DateRange,
    sort: str,
    order: SortOrder,
    page: PageParams,
) -> Page[EventRead]:
    conditions = [scope]
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


def _facets(db: Session, scope) -> EventFacets:
    types = db.scalars(select(Event.type).where(scope).distinct().order_by(Event.type)).all()
    results = db.scalars(select(Event.outcome).where(scope).distinct().order_by(Event.outcome)).all()
    return EventFacets(type=list(types), result=list(results))


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
    membership: OrgMembership = Depends(require_org_member),
) -> Page[EventRead]:
    """What happened in the org, newest first by default. Every member can
    read it; nothing can change it."""
    return _event_page(
        db, _in_org(membership.organization), q=q, type=type, item=item, who=who, result=result, criticality=criticality,
        dates=dates, sort=sort, order=order, page=page,
    )


@router.get("/orgs/{org_id}/events/facets", response_model=EventFacets)
def event_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), membership: OrgMembership = Depends(require_org_member)
) -> EventFacets:
    """The values the pick-lists can offer: event types and results seen."""
    return _facets(db, _in_org(membership.organization))


@router.get("/platform/events", response_model=Page[EventRead])
def list_platform_events(
    q: str | None = Query(None, description="Search the shown columns: event, item or who contains this"),
    type: list[str] | None = Query(None, description="Event type is one of these"),
    item: str | None = Query(None, description="The item (an org, an email) contains this"),
    who: str | None = Query(None, description="Who did it contains this"),
    result: list[str] | None = Query(None, description="Outcome is one of these"),
    criticality: list[Criticality] | None = Query(None, description="Criticality is one of these"),
    dates: DateRange = Depends(date_range),
    sort: EventSort = Query("when", description="Column to sort by"),
    order: SortOrder = Query("desc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: User = Depends(require_sysadmin),
) -> Page[EventRead]:
    """Platform activity: what the Sysadmin did (orgs created, archived and
    purged, accounts changed) and the background worker. Sysadmin only."""
    return _event_page(
        db, Event.org_id.is_(None), q=q, type=type, item=item, who=who, result=result, criticality=criticality,
        dates=dates, sort=sort, order=order, page=page,
    )


@router.get("/platform/events/facets", response_model=EventFacets)
def platform_event_facets(db: Session = Depends(get_db), _: User = Depends(require_sysadmin)) -> EventFacets:
    return _facets(db, Event.org_id.is_(None))


@router.get("/worker-status", response_model=WorkerStatusRead)
def worker_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> WorkerStatusRead:
    """Whether the background worker has checked in lately: while it
    hasn't, large imports and archive jobs wait."""
    status = db.get(WorkerStatus, 1)
    if status is None:
        return WorkerStatusRead(running=False, last_seen=None)
    fresh = datetime.now(timezone.utc) - status.heartbeat_at < timedelta(seconds=settings.WORKER_STALE_SECONDS // 2)
    return WorkerStatusRead(running=fresh, last_seen=status.heartbeat_at)
