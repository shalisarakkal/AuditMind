import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.api.deps import require_org_member, require_org_role
from app.api.paging import (
    PageParams,
    SortOrder,
    any_of,
    contains,
    distinct_values,
    labelled,
    one_of,
    ordered,
    page_params,
)
from app.api.uploads import IMPORT_RESPONSES, start_import
from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import Domain, Severity, UserRole
from app.models.finding import Finding
from app.models.membership import OrgMembership
from app.models.scan import Scan
from app.schemas.finding import FindingCreate, FindingFacets, FindingListItem, FindingPage, FindingRead
from app.schemas.ingestion import ImportResponse

router = APIRouter(prefix="/orgs/{org_id}", tags=["findings"])


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
FindingSort = Literal["severity", "domain", "finding", "category", "asset", "source", "created"]
_SORT_COLUMNS = {
    "severity": _SEVERITY_RANK,
    "domain": _DOMAIN_RANK,
    "finding": func.lower(func.coalesce(Finding.description, Finding.category)),
    "category": func.lower(Finding.category),
    "asset": func.lower(func.coalesce(Asset.hostname, Asset.ip, Asset.cloud_id)),
    "source": func.lower(Finding.source),
    "created": Finding.created_at,
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
    asset: str | None = Query(None, description="The asset's hostname, IP or cloud ID contains this"),
    domain: list[Domain] | None = Query(None, description="Domain is one of these"),
    severity: list[Severity] | None = Query(None, description="Severity is one of these"),
    source: list[str] | None = Query(None, description='Source is one of these ("" for none)'),
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
    conditions = [
        any_of(
            contains(
                q, Finding.description, Finding.category, Asset.hostname, Asset.ip, Asset.cloud_id, Finding.source
            ),
            labelled(q, Finding.severity, _SEVERITY_LABELS),
            labelled(q, Finding.domain, _DOMAIN_LABELS),
        ),
        contains(finding, Finding.description, Finding.category),
        contains(asset, Asset.hostname, Asset.ip, Asset.cloud_id),
        one_of(Finding.severity, severity),
        one_of(Finding.source, source),
    ]
    filters = [Finding.org_id == org_id, *(c for c in conditions if c is not None)]
    # The asset is only needed to search or sort by it; joining it into a
    # query over every finding is costly.
    needs_asset = bool(q or asset) or sort == "asset"

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
        db.query(Finding, Asset.hostname, Asset.ip, Asset.cloud_id)
        .outerjoin(Asset, asset_join)
        .filter(Finding.id.in_(ids))
        .all()
        if ids
        else []
    )
    position = {id_: i for i, id_ in enumerate(ids)}
    rows.sort(key=lambda row: position[row[0].id])
    items = [
        FindingListItem(
            **FindingRead.model_validate(finding).model_dump(),
            asset_hostname=hostname,
            asset_ip=ip,
            asset_cloud_id=cloud_id,
        )
        for finding, hostname, ip, cloud_id in rows
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
    return FindingFacets(source=distinct_values(db.query(Finding).filter(Finding.org_id == org_id), Finding.source))


@router.post("/findings", response_model=FindingRead, status_code=status.HTTP_201_CREATED)
def create_finding(
    org_id: uuid.UUID,
    payload: FindingCreate,
    db: Session = Depends(get_db),
    _: OrgMembership = Depends(require_org_role(UserRole.admin, UserRole.auditor)),
) -> Finding:
    """The asset and scan, if given, must belong to the org."""
    for model, ref_id, name in ((Asset, payload.asset_id, "asset_id"), (Scan, payload.scan_id, "scan_id")):
        if ref_id is not None:
            ref = db.get(model, ref_id)
            if ref is None or ref.org_id != org_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"{name} {ref_id} is not in this organization",
                )
    finding = Finding(org_id=org_id, **payload.model_dump())
    db.add(finding)
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
    background_tasks: BackgroundTasks,
    response: Response,
    file: UploadFile = File(..., description="Findings: .csv, .json, or a native .nessus export"),
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
        background_tasks=background_tasks,
        response=response,
        org_id=org_id,
        file=file,
        kind="findings",
        started_by=membership.user_id,
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
        .filter(Finding.org_id == org_id, Finding.asset_id == asset_id)
        .order_by(Finding.created_at.desc())
        .all()
    )
