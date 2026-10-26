import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import DateTime, String, and_, case, cast, func, or_, select, union
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import (
    DateRange,
    PageParams,
    SortOrder,
    any_of,
    contains,
    date_range,
    distinct_values,
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
from app.services.finding_workflow import get_finding, read_history, read_workflow, update_workflows
from app.services.workflow_deadlines import deadline_now

router = APIRouter(prefix="/orgs/{org_id}", tags=["findings"])


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
_SEVERITY_RANK = case(*((Finding.severity == severity, rank) for rank, severity in enumerate(Severity)))
_DOMAIN_RANK = case(*((Finding.domain == domain, rank) for rank, domain in enumerate(Domain)))

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
        # UNION removes duplicate IDs before counts, facets and pagination.
        active = (Finding.org_id == org_id, Finding.archived_at.is_(None))
        branches = [select(Finding.id).where(*active, predicate) for predicate in (
            contains(q, Finding.description, Finding.category, Finding.source),
            Finding.asset_id.in_(search_asset_ids),
            Finding.assignee_id.in_(search_assignee_ids),
        )]
        for column in (Finding.due_date, Finding.risk_review_date):
            branches.append(select(Finding.id).where(*active, column.is_not(None), contains(q, cast(column, String))))
        matches = union(*branches).subquery()
        search_condition = Finding.id.in_(select(matches.c.id))
    conditions = [
        search_condition,
        Finding.id == finding_id if finding_id else None,
        contains(finding, Finding.description, Finding.category),
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
    needs_asset = bool(asset) or sort == "asset"

    def matching(*columns):
        query = db.query(*columns)
        return query.outerjoin(Asset, asset_join) if needs_asset else query

    # Counts per domain and severity, under every filter but the domain one.
    counts = matching(Finding.domain, Finding.severity, func.count()).filter(*filters)
    counts = counts.group_by(Finding.domain, Finding.severity).all()
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

    ids = _page_ids(matching, filters, sort, order, page, severity_counts)
    rows = (
        db.query(Finding, Asset.hostname, Asset.ip, Asset.cloud_id, _ASSIGNEE_LABEL)
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
    return FindingPage(items=items, total=total, domain_counts=domain_counts)


def _page_ids(matching, filters, sort: str, order: str, page: PageParams, severity_counts: dict) -> list[uuid.UUID]:
    """The ids of the findings on the requested page, in order, found without
    reading whole rows. The default order (severity, newest first within one)
    walks ix_findings_org_severity_created one severity at a time, skipping
    whole severities by their counts; date order walks ix_findings_org_created.
    Other orders sort the matching ids (which reads every matching finding)."""
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
                .filter(*filters, Finding.severity == severity)
                .order_by(Finding.created_at.desc(), Finding.id)
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
            .order_by(ordered(_SORT_COLUMNS[sort], order), _SEVERITY_RANK, Finding.created_at.desc(), Finding.id)
        )
    return [id_ for (id_,) in query.offset(page.offset).limit(page.limit)]


@router.get("/findings/facets", response_model=FindingFacets)
def finding_facets(
    org_id: uuid.UUID, db: Session = Depends(get_db), _: OrgMembership = Depends(require_org_member)
) -> FindingFacets:
    """The values the source pick-list can offer ("" first when some
    findings have none). Severity and domain are fixed lists."""
    findings = db.query(Finding).filter(Finding.org_id == org_id, Finding.archived_at.is_(None))
    owners = db.scalars(select(Finding.assignee_id).where(
        Finding.org_id == org_id, Finding.archived_at.is_(None)).distinct()).all()
    labels = dict(db.execute(select(User.id, func.coalesce(User.name, User.email))
        .join(OrgMembership, OrgMembership.user_id == User.id).where(OrgMembership.org_id == org_id,
            User.is_active.is_(True), User.id.in_([identifier for identifier in owners if identifier]))).all())
    return FindingFacets(has_manual_findings=findings.with_entities(Finding.id).filter(Finding.scan_id.is_(None)).first() is not None,
        source=distinct_values(findings, Finding.source),
        workflow_status=distinct_values(findings, Finding.workflow_status),
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
