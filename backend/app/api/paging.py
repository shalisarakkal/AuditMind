"""Query parameters and filters shared by the paged list endpoints: paging,
one-column sorting, "contains" filters and pick-list filters."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import Query
from sqlalchemy import ColumnElement, false, or_
from sqlalchemy.orm import Query as OrmQuery

SortOrder = Literal["asc", "desc"]

# A pick-list value standing for "no value" (NULL, or an empty string).
BLANK = ""


@dataclass
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: int = Query(100, ge=1, le=500, description="Items per page"),
    offset: int = Query(0, ge=0, description="Items to skip"),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def contains_pattern(q: str | None) -> str | None:
    """An ILIKE pattern matching `q` anywhere (its own % and _ taken
    literally, with backslash as the escape character), or None for no search."""
    q = (q or "").strip()
    if not q:
        return None
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def contains(text: str | None, *columns) -> ColumnElement[bool] | None:
    """Any of `columns` contains `text` (case-insensitive), or None when
    there's nothing to search for."""
    pattern = contains_pattern(text)
    if pattern is None:
        return None
    return or_(*(column.ilike(pattern, escape="\\") for column in columns))


def one_of(column, values: list[str] | None) -> ColumnElement[bool] | None:
    """`column` is one of `values` (BLANK: no value), or None for no filter."""
    if not values:
        return None
    wanted = [v for v in values if v != BLANK]
    conditions = [column.in_(wanted)] if wanted else []
    if BLANK in values:
        conditions += [column.is_(None), column == ""]
    return or_(*conditions) if conditions else false()


def ordered(column, order: SortOrder):
    """ORDER BY `column` in `order`, rows without a value last either way."""
    return (column.desc() if order == "desc" else column.asc()).nulls_last()


def distinct_values(query: OrmQuery, column, limit: int = 500) -> list[str]:
    """A pick-list's values: the column's distinct values in `query`, sorted,
    with BLANK first if some rows have none."""
    values = {value for (value,) in query.with_entities(column).distinct().limit(limit + 1)}
    blank = None in values or "" in values
    listed = sorted(str(v.value if hasattr(v, "value") else v) for v in values if v not in (None, ""))
    return ([BLANK] if blank else []) + listed[:limit]


def labelled(text: str | None, column, labels: dict) -> ColumnElement[bool] | None:
    """`column` holds a value whose shown label (or the value itself) contains
    `text`, e.g. "network" -> network_device, "mgmt" -> vulnerability
    management. None when nothing matches, or there's nothing to search for."""
    needle = (text or "").strip().lower()
    if not needle:
        return None
    hits = [
        getattr(value, "value", value)
        for value, label in labels.items()
        if needle in label.lower() or needle in str(getattr(value, "value", value)).replace("_", " ")
    ]
    return column.in_(hits) if hits else None


def any_of(*conditions: ColumnElement[bool] | None) -> ColumnElement[bool] | None:
    """OR of the conditions given (None ones ignored); None if none are."""
    present = [c for c in conditions if c is not None]
    return or_(*present) if present else None


@dataclass
class DateRange:
    since: date | None
    until: date | None

    def conditions(self, column) -> list[ColumnElement[bool]]:
        """`column` (a timestamp) on or after `since` and on or before
        `until`, whole days in UTC."""
        found = []
        if self.since:
            found.append(column >= datetime.combine(self.since, time.min, timezone.utc))
        if self.until:
            found.append(column < datetime.combine(self.until + timedelta(days=1), time.min, timezone.utc))
        return found


def date_range(
    since: date | None = Query(None, description="On or after this day (UTC)"),
    until: date | None = Query(None, description="On or before this day (UTC)"),
) -> DateRange:
    """A list's From/To filter on its date column."""
    return DateRange(since=since, until=until)
