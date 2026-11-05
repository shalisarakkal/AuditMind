import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import DateTime, String, and_, case, cast, func, literal_column, or_, select, union
from sqlalchemy.orm import Session, defer

from app.api.deps import require_org_member, require_org_role
from app.api.paging import (
    DateRange,
    PageParams,
    SortOrder,
    any_of,
    contains,
    contains_pattern,
    date_range,
    distinct_values,
    indexed_values,
    labelled,
    one_of,
    ordered,
    page_params,
)
from app.api.uploads import IMPORT_RESPONSES, confirm_form, start_import
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import Domain, Severity, UserRole
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.models.user import User
from app.schemas.finding import FindingAssigneeFacet, FindingCreate, FindingFacets, FindingListItem, FindingPage, FindingRead
from app.schemas.ingestion import ImportResponse
from app.services.archive_service import archiving_fields, unfinished_archives
from app.services.events import record_event
from app.schemas.finding_workflow import HistoryRead, WorkflowBulk, WorkflowRead, WorkflowStatus, WorkflowTarget, WorkflowUpdate
from app.models.finding_history import FindingHistory
from app.models.finding_observation import FindingObservation
from app.schemas.finding_observation import FindingObservationRead
from app.services.finding_workflow import get_finding, read_history, read_workflow, update_workflows
from app.services.workflow_deadlines import deadline_now
from app.services import list_pages
from app.db.list_sort import severity_rank, finding_text_size, TEXT_SORT_BYTES

router = APIRouter(prefix="/orgs/{org_id}", tags=["findings"])


@router.get("/findings/{finding_id}/observations", response_model=list[FindingObservationRead])
def finding_observations(org_id: uuid.UUID, finding_id: uuid.UUID,
        before: uuid.UUID | None = None, limit: int = Query(20, ge=1, le=100),
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    get_finding(db, org_id, finding_id)
    query = select(FindingObservation).where(FindingObservation.org_id == org_id,
        FindingObservation.finding_id == finding_id)
    if before is not None:
        cursor = db.scalar(query.where(FindingObservation.id == before))
        if cursor is None:
            raise HTTPException(404, "Observation cursor not found")
        query = query.where(or_(FindingObservation.recorded_at < cursor.recorded_at,
            and_(FindingObservation.recorded_at == cursor.recorded_at, FindingObservation.id < cursor.id)))
    return db.scalars(query.order_by(FindingObservation.recorded_at.desc(),
        FindingObservation.id.desc()).limit(limit)).all()


@router.get("/findings/{finding_id}/workflow", response_model=WorkflowRead)
def finding_workflow(org_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db),
        _: OrgMembership = Depends(require_org_member)):
    return read_workflow(db, get_finding(db, org_id, finding_id))


@router.get("/findings/{finding_id}/workflow/history", response_model=list[HistoryRead])
def finding_workflow_history(org_id: uuid.UUID, finding_id: uuid.UUID,
        offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)):
    get_finding(db, org_id, finding_id)
    rows = db.query(FindingHistory).filter(FindingHistory.org_id == org_id,
        FindingHistory.finding_id == finding_id).order_by(FindingHistory.version.desc()).offset(offset).limit(limit).all()
    return [read_history(db, row) for row in rows]


@router.patch("/findings/{finding_id}/workflow", response_model=WorkflowRead)
def patch_finding_workflow(org_id: uuid.UUID, finding_id: uuid.UUID, payload: WorkflowUpdate,
        db: Session = Depends(get_db), membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor))):
    return update_workflows(db, org_id, membership,
        [WorkflowTarget(finding_id=finding_id, expected_version=payload.expected_version)], payload)[0]


@router.post("/findings/workflow/bulk", response_model=list[WorkflowRead])
def bulk_finding_workflow(org_id: uuid.UUID, payload: WorkflowBulk,
        db: Session = Depends(get_db), membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor))):
    return update_workflows(db, org_id, membership, payload.targets, payload.patch)


# Most severe first (critical = 0).
_SEVERITY_RANK = severity_rank(Finding.severity)
_DOMAIN_RANK = case(*((Finding.domain == domain, rank) for rank, domain in enumerate(Domain)))
_MAX_SORT_GROUPS = 1024
_BROAD_SEARCH_ROWS = 10000
_SHORT_SEARCH_SAMPLE = 1000

# The domains' labels as the app shows them (frontend/src/lib/domain.ts), so
# the search box finds "Vulnerability Mgmt" by what's on screen.
_DOMAIN_LABELS = {
    Domain.identity_access: "Identity & Access",
    Domain.network_config: "Network & Config",
    Domain.vulnerability_management: "Vulnerability Mgmt",
    Domain.backup_recovery: "Backup & Recovery",
    Domain.monitoring_detection: "Monitoring & Detection",
    Domain.incident_response: "Incident Response",
    Domain.compliance_alignment: "Compliance Alignment",
}
_SEVERITY_LABELS = {severity: severity.value.capitalize() for severity in Severity}

# Sortable columns; "severity" (the default) puts the most severe first.
_WORKFLOW_LABELS = {"open": "Open", "accepted_risk": "Accepted risk", "mitigated": "Mitigated",
    "resolved": "Resolved", "false_positive": "False positive"}
_ASSIGNEE_LABEL = (select(func.coalesce(User.name, User.email)).join(OrgMembership, OrgMembership.user_id == User.id)
    .where(User.id == Finding.assignee_id, OrgMembership.org_id == Finding.org_id, User.is_active.is_(True))
    .correlate(Finding).scalar_subquery())
_DUE_EXPIRY = func.coalesce(Finding.due_expires_at, func.timezone("America/New_York", cast(Finding.due_date + 1, DateTime)))
_REVIEW_EXPIRY = func.coalesce(Finding.risk_review_expires_at, func.timezone("America/New_York", cast(Finding.risk_review_date + 1, DateTime)))
FindingSort = Literal["severity", "domain", "finding", "category", "asset", "source", "created", "workflow_status", "assignee", "due_date", "risk_review_date"]
_SORT_COLUMNS = {
    "severity": _SEVERITY_RANK,
    "domain": _DOMAIN_RANK,
    "finding": func.lower(func.coalesce(Finding.description, Finding.category)),
    "category": func.lower(Finding.category),
    "asset": func.lower(func.coalesce(Asset.hostname, Asset.ip, Asset.cloud_id)),
    "source": func.lower(Finding.source),
    "created": Finding.created_at,
    "workflow_status": func.lower(case(*((Finding.workflow_status == key, value) for key, value in _WORKFLOW_LABELS.items()))),
    "assignee": func.lower(_ASSIGNEE_LABEL),
    "due_date": _DUE_EXPIRY,
    "risk_review_date": _REVIEW_EXPIRY,
}


@router.get("/findings", response_model=FindingPage)
def list_findings(
    org_id: uuid.UUID,
    q: str | None = Query(
        None,
        description="Search every shown column: the finding (description or category), its asset's hostname, "
        "IP or cloud ID, source, severity or domain contains this",
    ),
    finding: str | None = Query(None, description="Description or category contains this"),
    finding_id: uuid.UUID | None = Query(None, description="Exact internal finding ID"),
    asset: str | None = Query(None, description="The asset's hostname, IP or cloud ID contains this"),
    domain: list[Domain] | None = Query(None, description="Domain is one of these"),
    severity: list[Severity] | None = Query(None, description="Severity is one of these"),
    source: list[str] | None = Query(None, description='Source is one of these ("" for none)'),
    workflow_status: list[WorkflowStatus] | None = Query(None),
    assignee: list[uuid.UUID | Literal["unassigned"]] | None = Query(None),
    overdue: Literal["due", "risk_review"] | None = Query(None),
    dates: DateRange = Depends(date_range),
    sort: FindingSort = Query("severity", description="Column to sort by"),
    order: SortOrder = Query("asc"),
    page: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> FindingPage:
    """The org's findings, a page at a time, each with its asset's hostname
    and IP: by default most severe first, newest first within a severity.
    Filters combine (all must match); text filters match partially.
    domain_counts counts each domain under every filter but the domain one."""
    # The asset must be the org's own too, so a finding pointing elsewhere
    # (create_finding rejects that now) can't show another org's host.
    asset_join = and_(Finding.asset_id == Asset.id, Asset.org_id == org_id)
    q = (q or "").strip() or None
    try:
        query_id = uuid.UUID(q.strip()) if q else None
    except ValueError:
        query_id = None
    # Search small/independent lookup sets once, rather than joining assets and
    # evaluating a correlated assignee lookup for each matching finding.
    search_asset_ids = select(Asset.id).where(
        Asset.org_id == org_id, contains(q, Asset.hostname, Asset.ip, Asset.cloud_id)
    )
    search_assignee_ids = select(User.id).join(OrgMembership, OrgMembership.user_id == User.id).where(
        OrgMembership.org_id == org_id, User.is_active.is_(True),
        contains(q, func.coalesce(User.name, User.email)),
    )
    search_condition = Finding.id == query_id if query_id else None
    candidate_predicates = None
    label_conditions = [labelled(q, column, labels) for column, labels in (
        (Finding.severity, _SEVERITY_LABELS), (Finding.domain, _DOMAIN_LABELS),
        (Finding.workflow_status, _WORKFLOW_LABELS))]
    if q and not query_id and (len(q) < 3 or any(value is not None for value in label_conditions)):
        # Short trigrams and broad display labels can match millions of rows.
        # Avoid constructing/deduplicating a huge candidate-ID set for these.
        search_condition = any_of(*label_conditions,
            contains(q, Finding.description, Finding.category, Finding.source),
            Finding.asset_id.in_(search_asset_ids), Finding.assignee_id.in_(search_assignee_ids),
            contains(q, cast(Finding.due_date, String), cast(Finding.risk_review_date, String)))
    elif q and not query_id:
        # Separate indexed branches: an OR containing asset/assignee subqueries
        # prevents PostgreSQL from using selective text indexes effectively.
        # Deduplicate candidates here. Keeping this bounded relation lets
        # PostgreSQL avoid repeated heap probes for overlapping branches.
        active = (Finding.org_id == org_id, Finding.archived_at.is_(None))
        candidate_predicates = [
            contains(q, Finding.description, Finding.category, Finding.source),
            Finding.asset_id.in_(search_asset_ids),
            Finding.assignee_id.in_(search_assignee_ids),
        ]
        for column in (Finding.due_date, Finding.risk_review_date):
            candidate_predicates.append(and_(column.is_not(None), contains(q, cast(column, String))))
        branches = [select(Finding.id).where(*active, predicate) for predicate in candidate_predicates]
        matches = union(*branches).subquery()
        search_condition = Finding.id.in_(select(matches.c.id))
    finding_condition = contains(finding, Finding.description, Finding.category)
    finding_needle = (finding or "").strip()
    if finding_needle and finding_needle.isascii() and not any(c.isalpha() for c in finding_needle):
        # ASCII punctuation/digits have no case variants. Avoid ILIKE's
        # per-character case folding without changing literal matching.
        pattern = contains_pattern(finding_needle)
        finding_condition = or_(Finding.description.like(pattern, escape="\\"),
                                Finding.category.like(pattern, escape="\\"))
    conditions = [
        search_condition,
        Finding.id == finding_id if finding_id else None,
        finding_condition,
        contains(asset, Asset.hostname, Asset.ip, Asset.cloud_id),
        one_of(Finding.severity, severity),
        one_of(Finding.source, source),
        one_of(Finding.workflow_status, workflow_status),
    ]
    if assignee:
        assigned_ids = [value for value in assignee if value != "unassigned"]
        conditions.append(or_(Finding.assignee_id.in_(assigned_ids),
            Finding.assignee_id.is_(None) if "unassigned" in assignee else False))
    now = deadline_now()
    # Unmigrated/direct legacy inserts have no author-zone metadata; retain their Eastern meaning.
    if overdue == "due":
        conditions.append(and_(_DUE_EXPIRY <= now, Finding.workflow_status.in_(["open", "accepted_risk", "mitigated"])))
    elif overdue == "risk_review":
        conditions.append(and_(_REVIEW_EXPIRY <= now, Finding.workflow_status == "accepted_risk"))
    # archived_at IS NULL also lets the paging below use the partial indexes.
    filters = [
        Finding.org_id == org_id,
        Finding.archived_at.is_(None),
        *(c for c in conditions if c is not None),
        *dates.conditions(Finding.created_at),
    ]
    # The asset is only needed to search or sort by it; joining it into a
    # query over every finding is costly.
    has_asset_filter = bool((asset or "").strip())
    needs_asset = has_asset_filter or sort == "asset"
    owners = (select(User.id.label("owner_id"), func.coalesce(User.name, User.email).label("owner_label"),
        func.dense_rank().over(order_by=func.lower(func.coalesce(User.name,User.email))).label("owner_rank"))
        .join(OrgMembership, OrgMembership.user_id == User.id).where(OrgMembership.org_id == org_id,
            User.is_active.is_(True)).subquery()) if sort == "assignee" else None
    sort_column = owners.c.owner_rank if owners is not None else _SORT_COLUMNS[sort]

    def matching(*columns, for_counts=False):
        query = db.query(*columns)
        # A sort-only join can prevent index-only counting even when the
        # planner later removes the unused join. Counts need filter joins only.
        if needs_asset and (not for_counts or has_asset_filter):
            query = query.outerjoin(Asset, asset_join)
        if owners is not None and not for_counts:
            query = query.outerjoin(owners, owners.c.owner_id == Finding.assignee_id)
        return query

    # Counts per domain and severity, under every filter but the domain one.
    def build_counts():
        if candidate_predicates:
            count_filters = [condition for condition in filters if condition is not search_condition]
            candidates = union(*(matching(Finding.id, Finding.domain, Finding.severity, for_counts=True)
                .filter(*count_filters, predicate).statement for predicate in candidate_predicates)).subquery()
            return db.query(candidates.c.domain, candidates.c.severity, func.count()).group_by(
                candidates.c.domain, candidates.c.severity).all()
        return matching(Finding.domain, Finding.severity, func.count(), for_counts=True).filter(*filters).group_by(
            Finding.domain, Finding.severity).all()

    def next_deadline():
        expiry = _DUE_EXPIRY if overdue == "due" else _REVIEW_EXPIRY
        states = ["open", "accepted_risk", "mitigated"] if overdue == "due" else ["accepted_risk"]
        return db.scalar(select(func.min(expiry)).where(Finding.org_id == org_id,
            Finding.archived_at.is_(None), Finding.workflow_status.in_(states), expiry > now))

    key = {"q": q, "finding_id": finding_id, "finding": (finding or "").strip(), "asset": (asset or "").strip(),
        "severity": list_pages.choices(severity), "source": list_pages.choices(source),
        "status": list_pages.choices(workflow_status), "assignee": list_pages.choices(assignee),
        "overdue": overdue, "since": dates.since, "until": dates.until, "timezone": dates.timezone_name}
    stamp = list_pages.revision_stamp(db, org_id, "findings")
    count_builder = build_counts
    short_ids = None
    if finding_condition is not None and len(finding.strip()) < 3 and not q:
        # One/two-character patterns cannot use trigrams. For rare matches,
        # scan once and reuse a bounded set of ID/count metadata for paging;
        # do not repeat the full scan for counts, page IDs and positions.
        sample = list_pages.exact_counts(db, stamp, "findings", {"short_candidates":key},
            lambda: matching(Finding.id, Finding.domain, Finding.severity, for_counts=True)
                .filter(*filters).limit(_SHORT_SEARCH_SAMPLE+1).all(),
            asof=now if overdue else None, boundary=next_deadline if overdue else None).value
        if len(sample) <= _SHORT_SEARCH_SAMPLE:
            grouped_counts = {}
            for identifier, d, s in sample:
                grouped_counts[(d,s)] = grouped_counts.get((d,s),0)+1
            short_ids = [row[0] for row in sample]
            count_builder = lambda: [(d,s,n) for (d,s),n in grouped_counts.items()]
    counted = list_pages.exact_counts(db, stamp, "findings", key, count_builder,
        asof=now if overdue else None, boundary=next_deadline if overdue else None)
    counts = counted.value
    domain_counts: dict[Domain, int] = {}
    for d, _severity, n in counts:
        domain_counts[d] = domain_counts.get(d, 0) + n
    if domain:
        filters.append(Finding.domain.in_(domain))
    severity_counts: dict[Severity, int] = {}
    for d, s, n in counts:
        if not domain or d in domain:
            severity_counts[s] = severity_counts.get(s, 0) + n
    total = sum(severity_counts.values())

    if short_ids is not None:
        filters = [Finding.id.in_(short_ids) if condition is finding_condition else condition
                   for condition in filters]

    # Broad matches should walk the ordered page index and stop at LIMIT,
    # rather than rebuild/deduplicate every candidate ID for each page probe.
    # Keep the indexed UNION for exact counts and selective/unknown matches.
    if candidate_predicates and total >= _BROAD_SEARCH_ROWS and sort in {"severity", "created"}:
        filters = [or_(*candidate_predicates) if condition is search_condition else condition
                   for condition in filters]

    # A bounded partial index accelerates ordinary finding text without
    # imposing B-tree entry-size limits on imported long descriptions.
    # If a matching long value exists, retain the full exact sort instead.
    short_text_sort = False
    if sort == "finding" and total:
        size = finding_text_size(Finding)
        bound = literal_column(str(TEXT_SORT_BYTES))
        # COUNT optimizes total work; LIMIT 1 can prefer a table scan on an
        # empty partial index because it assumes an early matching row.
        long_count = list_pages.exact_counts(db, stamp, "findings",
            {"long_finding_text":key,"domain":list_pages.choices(domain)},
            matching(Finding.id, for_counts=True).filter(*filters, size > bound).count,
            asof=now if overdue else None, boundary=(lambda: counted.valid_until) if overdue else None)
        short_text_sort = long_count.value == 0
        if short_text_sort:
            filters.append(size <= bound)

    if sort == "created":
        ascending = order == "asc"
        # Both keys are NOT NULL. Match a forward/backward walk of the same
        # physical index instead of requesting an unnecessary NULL re-sort.
        terms = [list_pages.Term(Finding.created_at, ascending, ascending),
                 list_pages.Term(Finding.id, ascending, ascending)]
    else:
        terms = [list_pages.Term(sort_column, order == "asc")]
        if sort != "severity": terms.append(list_pages.Term(_SEVERITY_RANK))
        terms += [list_pages.Term(Finding.created_at, False), list_pages.Term(Finding.id)]
    base_query = matching(Finding.id, *(term.column for term in terms)).filter(*filters)
    scope = list_pages.fingerprint({"kind": "findings-v2", "org": org_id, "filters": key,
        "domain": list_pages.choices(domain), "sort": sort, "order": order})
    anchor = list_pages.read_cursor(page.cursor, stamp, scope, page, terms, now if overdue else None)
    partitions = None
    if sort == "severity":
        partitions = [([rank], _SEVERITY_RANK == rank, severity_counts.get(severity, 0))
            for rank, severity in enumerate(Severity)]
    elif sort == "domain":
        selected_counts = {(d,s):n for d,s,n in counts if not domain or d in domain}
        partitions = [([d_rank,s_rank], and_(Finding.domain == d, _SEVERITY_RANK == s_rank), selected_counts[(d,s)])
            for d_rank,d in enumerate(Domain) for s_rank,s in enumerate(Severity)
            if selected_counts.get((d,s), 0)]
    groups = None
    if sort in {"workflow_status", "assignee", "due_date", "risk_review_date"} and page.offset < total:
        group_column = (Finding.workflow_status if sort == "workflow_status" else
            Finding.assignee_id if sort == "assignee" else sort_column)
        group_filters = list(filters)
        deadline_sort = sort in {"due_date", "risk_review_date"}
        if deadline_sort:
            date_field, expiry_field = ((Finding.due_date, Finding.due_expires_at) if sort == "due_date"
                else (Finding.risk_review_date, Finding.risk_review_expires_at))
            group_filters += [or_(date_field.is_not(None),expiry_field.is_not(None)), sort_column.is_not(None)]
        grouped = list_pages.exact_counts(db,stamp,"findings",
            {"sort_groups":key,"sort":sort,"domain":list_pages.choices(domain)},
            lambda: matching(group_column,Finding.severity,func.count(),for_counts=True).filter(*group_filters)
                .group_by(group_column,Finding.severity).limit(_MAX_SORT_GROUPS+1).all(),
            asof=now if overdue else None, boundary=(lambda:counted.valid_until) if overdue else None).value
        if len(grouped) <= _MAX_SORT_GROUPS:
            rank_map = dict(db.query(owners.c.owner_id,owners.c.owner_rank).all()) if owners is not None else {}
            label = ((lambda value: _WORKFLOW_LABELS[value].lower()) if sort == "workflow_status" else
                     rank_map.get if sort == "assignee" else None)
            groups = list_pages.ranked_groups(grouped, group_column, Finding.severity, _SEVERITY_RANK,
                Severity, label=label, totals=severity_counts if deadline_sort else None)
            if deadline_sort:
                # Make the sparse-index predicate explicit for dated groups;
                # PostgreSQL does not infer it from COALESCE(expiry,legacy)=x.
                presence = or_(date_field.is_not(None), expiry_field.is_not(None))
                groups = [(prefix,
                    and_(predicate,presence) if prefix[0] is not None else
                    and_(date_field.is_(None),expiry_field.is_(None),_SEVERITY_RANK == prefix[1],
                         Finding.severity == list(Severity)[prefix[1]]), count)
                    for prefix,predicate,count in groups]
            partitions = groups
    if page.offset >= total:
        positions, ids = [], []
    elif sort == "asset" and (anchor or page.offset == 0):
        positions = list_pages.split_nullable_rows(base_query, Asset.id.is_not(None), sort_column, terms, page, anchor, total)
        ids = [row[0] for row in positions]
    elif anchor:
        positions = list_pages.page_rows(base_query, terms, page, stamp, scope, now if overdue else None,
            indexed=sort in {"severity", "created", "category", "source"} or short_text_sort, partitions=partitions)
        ids = [row[0] for row in positions]
    elif groups is not None:
        positions = list_pages.grouped_rows(base_query,terms,groups,page)
        ids = [row[0] for row in positions]
    else:
        groups = {(d,s):n for d,s,n in counts if not domain or d in domain}
        ids = _page_ids(matching, filters, sort, order, page, severity_counts, sort_column, groups)
        positions = base_query.filter(Finding.id.in_(ids)).all() if ids else []
        position = {id_: i for i, id_ in enumerate(ids)}
        positions.sort(key=lambda row: position[row[0]])
    rows = (
        db.query(Finding, Asset.hostname, Asset.ip, Asset.cloud_id, _ASSIGNEE_LABEL)
        .options(defer(Finding.raw_data))
        .outerjoin(Asset, asset_join)
        .filter(Finding.id.in_(ids))
        .all()
        if ids
        else []
    )
    position = {id_: i for i, id_ in enumerate(ids)}
    rows.sort(key=lambda row: position[row[0].id])
    unfinished = unfinished_archives(db, org_id, [f.id for f, *_ in rows if f.scan_id is None])
    items = [
        FindingListItem(
            **FindingRead.model_validate(finding).model_dump(),
            asset_hostname=hostname,
            asset_ip=ip,
            asset_cloud_id=cloud_id,
            assignee_label=assignee_label,
            **archiving_fields(unfinished, finding.id),
        )
        for finding, hostname, ip, cloud_id, assignee_label in rows
    ]
    navigation = list_pages.navigation(positions, stamp, scope, page, total,
        valid_until=counted.valid_until, asof=now if overdue else None) if list_pages.revision_stamp(db, org_id, "findings") == stamp else {}
    return FindingPage(items=items, total=total, domain_counts=domain_counts, **navigation)


def _page_ids(
    matching,
    filters,
    sort: str,
    order: str,
    page: PageParams,
    severity_counts: dict,
    sort_column=None,
    domain_severity_counts=None,
) -> list[uuid.UUID]:
    """The ids of the findings on the requested page, in order, found without
    reading whole rows. The default order (severity, newest first within one)
    walks ix_findings_org_severity_created one severity at a time, skipping
    whole severities by their counts; date order walks ix_findings_org_created.
    Other orders sort the matching ids (which reads every matching finding)."""
    if sort == "domain" and domain_severity_counts is not None:
        ids, skip = [], page.offset
        for d in (list(Domain) if order == "asc" else list(reversed(Domain))):
            counts = {s:domain_severity_counts.get((d,s),0) for s in Severity}
            count = sum(counts.values())
            if skip >= count:
                skip -= count
                continue
            ids += _page_ids(matching, [*filters, Finding.domain == d], "severity", "asc",
                PageParams(page.limit-len(ids),skip), counts)
            skip = 0
            if len(ids) == page.limit:
                break
        return ids
    if sort == "severity":
        ids: list[uuid.UUID] = []
        skip, wanted = page.offset, page.limit
        for severity in (list(Severity) if order == "asc" else list(reversed(Severity))):
            count = severity_counts.get(severity, 0)
            if skip >= count:
                skip -= count
                continue
            ids += [
                id_
                for (id_,) in matching(Finding.id)
                .filter(*filters, _SEVERITY_RANK == list(Severity).index(severity))
                .order_by(Finding.created_at.desc().nulls_last(), Finding.id)
                .offset(skip)
                .limit(wanted - len(ids))
            ]
            skip = 0
            if len(ids) == wanted:
                break
        return ids
    if sort == "created":
        newest_first = order == "desc"
        by_date = (Finding.created_at.desc(), Finding.id.desc()) if newest_first else (Finding.created_at, Finding.id)
        query = matching(Finding.id).filter(*filters).order_by(*by_date)
    else:
        query = (
            matching(Finding.id)
            .filter(*filters)
            .order_by(ordered(sort_column if sort_column is not None else _SORT_COLUMNS[sort], order), _SEVERITY_RANK, Finding.created_at.desc().nulls_last(), Finding.id)
        )
    return [id_ for (id_,) in query.offset(page.offset).limit(page.limit)]


@router.get("/findings/facets", response_model=FindingFacets)
def finding_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> FindingFacets:
    """The values the source pick-list can offer ("" first when some
    findings have none). Severity and domain are fixed lists."""
    findings = db.query(Finding).filter(Finding.org_id == org_id, Finding.archived_at.is_(None))
    owners = indexed_values(findings, Finding.assignee_id)
    labels = dict(db.execute(select(User.id, func.coalesce(User.name, User.email))
        .join(OrgMembership, OrgMembership.user_id == User.id).where(OrgMembership.org_id == org_id,
            User.is_active.is_(True), User.id.in_([identifier for identifier in owners if identifier]))).all())
    return FindingFacets(has_manual_findings=findings.with_entities(Finding.id).filter(Finding.scan_id.is_(None)).first() is not None,
        source=distinct_values(findings, Finding.source, indexed=True),
        workflow_status=distinct_values(findings, Finding.workflow_status, indexed=True),
        assignee=sorted([FindingAssigneeFacet(value=str(identifier) if identifier else "unassigned",
            label=labels.get(identifier) or ("Assignee unavailable" if identifier else "Unassigned")) for identifier in owners],
            key=lambda item: (item.label.casefold(), item.value)))


@router.post("/findings", response_model=FindingRead, status_code=status.HTTP_201_CREATED)
def create_finding(
    org_id: uuid.UUID,
    payload: FindingCreate,
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Finding:
    """The asset and scan, if given, must belong to the org and not be archived."""
    from app.services.org_lock import lock_org
    lock_org(db, org_id)
    references = [value for value in (payload.asset_id, payload.scan_id) if value is not None]
    if unfinished_archives(db, org_id, references):
        raise HTTPException(409, "An affected asset or upload is being archived")
    for model, ref_id, name in ((Asset, payload.asset_id, "asset_id"), (Scan, payload.scan_id, "scan_id")):
        if ref_id is not None:
            ref = db.get(model, ref_id, populate_existing=True)
            if ref is None or ref.org_id != org_id or ref.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"{name} {ref_id} is not in this organization",
                )
    finding = Finding(org_id=org_id, **payload.model_dump())
    db.add(finding)
    record_event(
        db,
        "finding_added",
        org_id=org_id,
        actor=membership.user,
        item=finding.description or finding.category,
        details={"severity": finding.severity.value, "domain": finding.domain.value},
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.post(
    "/findings/import",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    responses=IMPORT_RESPONSES,
)
async def import_findings(
    org_id: uuid.UUID,
    response: Response,
    file: UploadFile = File(..., description="Findings: .csv, .json, or a native .nessus export"),
    confirm: bool = confirm_form(),
    db: Session = Depends(get_db),
    membership: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> ImportResponse:
    """Upload findings. CSV/JSON columns: hostname and/or ip (at least one),
    domain and severity (required), category, description, source (default
    "manual"). Hosts not yet in the inventory are added as assets. A finding
    already recorded for the same asset, source and category is skipped as a
    duplicate."""
    return await start_import(
        db=db,
        response=response,
        org_id=org_id,
        file=file,
        kind="findings",
        started_by=membership.user_id,
        confirm=confirm,
    )


@router.get("/assets/{asset_id}/findings", response_model=list[FindingRead])
def list_asset_findings(
    org_id: uuid.UUID,
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_member),
) -> list[Finding]:
    return (
        db.query(Finding)
        .filter(Finding.org_id == org_id, Finding.asset_id == asset_id, Finding.archived_at.is_(None))
        .order_by(Finding.created_at.desc())
        .all()
    )
