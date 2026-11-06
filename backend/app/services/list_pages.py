"""Exact count reuse and signed, revision-bound seek navigation.

Only small count and bounded candidate-ID metadata is cached, never finding
payloads or authorization decisions.
Invalid/stale cursors fall back to the existing offset contract.
"""
import base64
import copy
import hashlib
import hmac
import json
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import cmp_to_key
from sqlalchemy import and_, false, func, or_, select, union_all
from app.core.config import settings
from app.models.list_revision import OrganizationListRevision, OrganizationWorkflowRevision


@dataclass(frozen=True)
class Stamp:
    engine: int
    database: str
    schema: str
    org: str
    epoch: str
    revision: int


def revision_stamp(db, org_id, kind):
    row = db.execute(select(OrganizationListRevision.epoch,
        OrganizationListRevision.asset_revision if kind == "assets" else
        OrganizationListRevision.finding_revision + func.coalesce(OrganizationWorkflowRevision.revision, 0),
        func.current_database(), func.current_schema(), func.pg_current_xact_id_if_assigned())
        .outerjoin(OrganizationWorkflowRevision, OrganizationWorkflowRevision.org_id == OrganizationListRevision.org_id)
        .where(OrganizationListRevision.org_id == org_id)).first()
    # Never publish counts from a writer's uncommitted transaction: rollback
    # could reuse its revision number for different future data.
    if row is None or row[4] is not None:
        return None
    bind = db.get_bind()
    return Stamp(id(getattr(bind, "engine", bind)), row[2], row[3], str(org_id), str(row[0]), row[1])


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def choices(value):
    return sorted({str(v.value if hasattr(v, "value") else v) for v in (value or [])})


@dataclass
class CountResult:
    value: object
    valid_until: datetime | None = None


_counts = OrderedDict()
_lock = threading.Lock()
COUNT_TTL = 60
MAX_COUNTS = 256


def exact_counts(db, stamp, kind, query_key, build, *, asof=None, boundary=None):
    key = (stamp, kind, fingerprint(query_key))
    instant = time.monotonic()
    if stamp is not None:
        with _lock:
            cached = _counts.get(key)
            if cached:
                inserted, captured, result = cached
                current = instant-inserted < COUNT_TTL
                if asof is not None:
                    current = current and asof >= captured and (result.valid_until is None or asof < result.valid_until)
                if current:
                    _counts.move_to_end(key)
                    return copy.deepcopy(result)
                _counts.pop(key, None)
    result = CountResult(build(), boundary() if boundary else None)
    if stamp is not None and revision_stamp(db, uuid.UUID(stamp.org), kind) == stamp:
        with _lock:
            _counts[key] = (instant, asof, copy.deepcopy(result))
            _counts.move_to_end(key)
            while len(_counts) > MAX_COUNTS:
                _counts.popitem(last=False)
    return result


@dataclass(frozen=True)
class Term:
    column: object
    asc: bool = True
    nulls_last: bool = True

    def ordering(self, reverse=False):
        ascending = self.asc != reverse
        expression = self.column.asc() if ascending else self.column.desc()
        return expression.nulls_last() if self.nulls_last != reverse else expression.nulls_first()


def _value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return {"uuid": str(value)}
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    raise ValueError("Unsupported cursor value")


def _restore(value):
    if isinstance(value, dict):
        if set(value) == {"uuid"}: return uuid.UUID(value["uuid"])
        if set(value) == {"datetime"}: return datetime.fromisoformat(value["datetime"])
        if set(value) == {"date"}: return date.fromisoformat(value["date"])
        raise ValueError("Unsupported cursor type")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("Unsupported cursor value")


def _b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(value):
    return _b64(hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).digest())


def cursor(stamp, scope, values, offset, limit, before=False, valid_until=None, asof=None):
    if stamp is None:
        return None
    payload = {"v": 1, "scope": scope, "epoch": stamp.epoch, "revision": stamp.revision,
        "offset": offset, "limit": limit, "before": before, "values": [_value(v) for v in values],
        "expires": valid_until.isoformat() if valid_until else None,
        "asof": asof.isoformat() if asof else None}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    token = body + "." + _sign(body)
    return token if len(token) <= 4096 else None


def read_cursor(token, stamp, scope, page, terms, asof=None):
    if not token or stamp is None:
        return None
    try:
        body, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(body)):
            return None
        data = json.loads(_decode(body))
        if (data["v"] != 1 or data["scope"] != scope or data["epoch"] != stamp.epoch
                or data["revision"] != stamp.revision or data["offset"] != page.offset or data["limit"] != page.limit
                or len(data["values"]) != len(terms)):
            return None
        clock = asof or datetime.now(timezone.utc)
        if data.get("expires") and clock >= datetime.fromisoformat(data["expires"]): return None
        if data.get("asof") and clock < datetime.fromisoformat(data["asof"]): return None
        return ([_restore(value) for value in data["values"]], bool(data["before"]))
    except (ValueError, TypeError, KeyError, UnicodeError):
        return None


def seek_condition(terms, values, before=False):
    equal, branches = [], []
    for term, value in zip(terms, values):
        col = term.column
        if value is None:
            comparison = col.is_not(None) if term.nulls_last == before else false()
            equality = col.is_(None)
        else:
            increasing = term.asc != before
            comparison = col > value if increasing else col < value
            if term.nulls_last != before:
                comparison = or_(comparison, col.is_(None))
            equality = col == value
        branches.append(and_(*equal, comparison))
        equal.append(equality)
    return or_(*branches)


def _indexed_branches(query, terms, values, reverse, limit):
    equal, branches = [], []
    for term, value in zip(terms, values):
        col = term.column
        predicates = []
        if value is None:
            if term.nulls_last == reverse:
                predicates.append(col.is_not(None))
            equality = col.is_(None)
        else:
            predicates.append(col > value if term.asc != reverse else col < value)
            if term.nulls_last != reverse:
                predicates.append(col.is_(None))
            equality = col == value
        for predicate in predicates:
            branch = query.filter(and_(*equal, predicate)).order_by(
                *(item.ordering(reverse) for item in terms)).limit(limit).subquery()
            branches.append(select(*branch.c))
        equal.append(equality)
    return branches


def prefix_relation(prefix, pivot, terms, reverse=False):
    for value, other, term in zip(prefix, pivot, terms):
        # PostgreSQL timestamptz compares instants. Python's equality at a
        # repeated local hour can differ between ZoneInfo and fixed offsets.
        if isinstance(value, datetime) and isinstance(other, datetime):
            value, other = value.astimezone(timezone.utc), other.astimezone(timezone.utc)
        if value == other:
            continue
        if value is None:
            return 1 if term.nulls_last != reverse else -1
        if other is None:
            return 1 if term.nulls_last == reverse else -1
        return 1 if (value > other) == (term.asc != reverse) else -1
    return 0


def grouped_rows(query, terms, groups, page):
    ordered_groups = sorted(groups, key=cmp_to_key(lambda a, b: prefix_relation(a[0], b[0], terms)))
    rows, skip = [], page.offset
    for prefix, predicate, count in ordered_groups:
        if skip >= count:
            skip -= count
            continue
        rows += (query.filter(predicate).order_by(*(term.ordering() for term in terms[len(prefix):]))
                 .offset(skip).limit(page.limit-len(rows)).all())
        skip = 0
        if len(rows) == page.limit:
            break
    return rows


def ranked_groups(rows, column, severity_column, rank_column, severities, *, label=None, totals=None):
    """Merge equal displayed labels while retaining exact source predicates.
    Sparse deadline totals derive the NULL bucket without scanning all rows.
    """
    severity_values = list(severities)
    combined = {}
    for value, severity, count in rows:
        primary = label(value) if label else value
        if isinstance(primary, datetime):
            primary = primary.astimezone(timezone.utc)
        prefix = (primary, severity_values.index(severity))
        bucket = combined.setdefault(prefix, [[], 0])
        bucket[0].append(value)
        bucket[1] += count
    groups = []
    for prefix, (values, count) in combined.items():
        predicate = or_(column.in_([value for value in values if value is not None]),
                        column.is_(None) if None in values else False)
        groups.append((prefix, and_(predicate, rank_column == prefix[1],
            severity_column == severity_values[prefix[1]]), count))
    for severity, total in (totals or {}).items():
        missing = total-sum(count for _value, group_severity, count in rows if group_severity == severity)
        if missing > 0:
            rank = severity_values.index(severity)
            groups.append(((None, rank), and_(column.is_(None), rank_column == rank,
                severity_column == severity), missing))
    return groups


def page_rows(query, terms, page, stamp, scope, asof=None, *, indexed=False, partitions=None):
    anchor = read_cursor(page.cursor, stamp, scope, page, terms, asof)
    reverse = anchor[1] if anchor else False
    if anchor and (indexed or partitions is not None):
        # Disjoint ranges let a compound index seek each range. A single OR
        # can otherwise filter all preceding entries in an ordered index scan.
        if partitions is None:
            branches = _indexed_branches(query, terms, anchor[0], reverse, page.limit)
        else:
            # Enumerated leading ranks can have mixed directions. Fixing
            # each prefix lets the same physical suffix index serve both.
            branches = []
            following = 0
            ordered_partitions = sorted(partitions, key=cmp_to_key(
                lambda a, b: prefix_relation(a[0], b[0], terms, reverse)))
            for prefix, predicate, count in ordered_partitions:
                if not count:
                    continue
                relation = prefix_relation(prefix, anchor[0], terms, reverse)
                if relation < 0:
                    continue
                segment = query.filter(predicate)
                suffix = terms[len(prefix):]
                if relation == 0:
                    branches += _indexed_branches(segment, suffix, anchor[0][len(prefix):], reverse, page.limit)
                else:
                    branch = segment.order_by(*(term.ordering(reverse) for term in suffix)).limit(page.limit).subquery()
                    branches.append(select(*branch.c))
                    following += count
                    if following >= page.limit:
                        break
        if not branches: return []
        combined = union_all(*branches).subquery()
        statement = select(*combined.c).order_by(*(Term(combined.c[i+1], term.asc, term.nulls_last).ordering(reverse)
            for i, term in enumerate(terms))).limit(page.limit)
        rows = list(query.session.execute(statement))
        return list(reversed(rows)) if reverse else rows
    if anchor:
        query = query.filter(seek_condition(terms, anchor[0], reverse))
    query = query.order_by(*(term.ordering(reverse) for term in terms))
    rows = query.offset(0 if anchor else page.offset).limit(page.limit).all()
    return list(reversed(rows)) if reverse else rows


def split_nullable_rows(query, nonnull, primary, terms, page, anchor, total):
    """Read a joined sort's non-NULL segment first; visit the NULL segment
    only if this page crosses it. Predicate reduction permits a driving inner
    join for populated labels without dropping unlinked rows from the list.
    Used only for page zero or a verified cursor; offsets retain their fallback.
    """
    reverse = anchor[1] if anchor else False
    values = anchor[0] if anchor else None
    def segment(is_null, wanted, use_anchor):
        selected = query.filter(primary.is_(None)) if is_null else query.filter(nonnull, primary.is_not(None))
        ordering = terms[1:] if is_null else terms
        if use_anchor:
            relevant = values[1:] if is_null else values
            selected = selected.filter(seek_condition(ordering, relevant, reverse))
            if not is_null:
                selected = selected.filter(primary >= values[0] if terms[0].asc != reverse else primary <= values[0])
        return selected.order_by(*(term.ordering(reverse) for term in ordering)).limit(wanted).all()
    if not anchor or (values[0] is not None and not reverse):
        rows = segment(False, page.limit, bool(anchor))
        if len(rows) < page.limit and page.offset+len(rows) < total:
            rows += segment(True, page.limit-len(rows), False)
    elif values[0] is not None:
        rows = segment(False, page.limit, True)
    else:
        rows = segment(True, page.limit, True)
        if reverse and len(rows) < page.limit:
            rows += segment(False, page.limit-len(rows), False)
    return list(reversed(rows)) if reverse else rows


def navigation(rows, stamp, scope, page, total, *, valid_until=None, asof=None):
    if not rows:
        return {}
    result = {}
    if page.offset + len(rows) < total:
        result["next_cursor"] = cursor(stamp, scope, rows[-1][1:], page.offset+len(rows), page.limit,
            valid_until=valid_until, asof=asof)
    if page.offset >= page.limit:
        result["previous_cursor"] = cursor(stamp, scope, rows[0][1:], page.offset-page.limit, page.limit,
            before=True, valid_until=valid_until, asof=asof)
    return result
