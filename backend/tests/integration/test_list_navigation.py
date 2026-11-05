"""Exact count reuse and seek pagination across every supported sort."""
from datetime import date, datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import event, func, select, text
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.enums import Domain, Severity, UserRole
from app.models.user import User
from app.models.membership import OrgMembership
from app.services import list_pages
from tests.conftest import requires_db
from tests.helpers import first_org_id, register

pytestmark = requires_db


@pytest.fixture
def inventory(client, db_session):
    headers = register(client, "navigation@example.com")
    org = uuid.UUID(first_org_id(client, headers))
    user = User(email="assignee@example.com", name="Zulu", hashed_password="unused", is_active=True)
    db_session.add(user); db_session.flush()
    db_session.add(OrgMembership(org_id=org, user_id=user.id, role=UserRole.auditor))
    created = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assets = [Asset(id=uuid.UUID(int=i+1), org_id=org, type="server" if i%2 else "network_device",
        hostname=None if i%7 == 0 else f"host-{i%5}", ip=None if i%4 == 0 else f"10.0.0.{i%4}",
        cloud_id=f"arn:{i%4}" if i%3 else None, subtype=f"sub-{i%3}" if i%4 else None,
        environment="Prod" if i%2 else None, criticality="low" if i%3 else "HIGH",
        created_at=created+timedelta(seconds=i%3), details={"payload": "x"*5000}) for i in range(37)]
    db_session.add_all(assets); db_session.flush()
    findings = [Finding(id=uuid.UUID(int=1000+i), org_id=org, asset_id=assets[i%len(assets)].id if i%9 else None,
        domain=list(Domain)[i%len(Domain)], severity=list(Severity)[i%4],
        description=f"Finding {i%6}" if i%7 else None, category=f"cat-{i%5}" if i%3 else None,
        source="Scanner" if i%4 else None, assignee_id=user.id if i%3 else None,
        workflow_status="accepted_risk" if i%2 else "open",
        due_date=date(2026,10,1+i%5) if i%4 else None,
        risk_review_date=date(2026,10,1+i%5) if i%3 else None,
        created_at=created+timedelta(seconds=i%3)) for i in range(45)]
    db_session.add_all(findings); db_session.commit()
    return headers, org, assets, findings, user


def get(client, inventory, kind, **params):
    headers, org, *_ = inventory
    response = client.get(f"/api/v1/orgs/{org}/{kind}", headers={**headers, "X-Activity": "background"}, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("kind,sorts", [
    ("assets", ["hostname","ip","cloud_id","type","subtype","environment","criticality","created"]),
    ("findings", ["severity","domain","finding","category","asset","source","created","workflow_status","assignee","due_date","risk_review_date"]),
])
def test_every_sort_seeks_forward_and_back_with_nulls_and_ties(client, inventory, kind, sorts):
    for sort in sorts:
        for order in ("asc", "desc"):
            params = {"sort": sort, "order": order}
            expected = get(client, inventory, kind, limit=500, **params)
            pages, ids, offset, cursor = [], [], 0, None
            while True:
                body = get(client, inventory, kind, limit=7, offset=offset, **params, **({"cursor": cursor} if cursor else {}))
                assert body["total"] == expected["total"]
                pages.append((offset, body))
                ids.extend(row["id"] for row in body["items"])
                cursor = body["next_cursor"]
                if not cursor: break
                offset += len(body["items"])
                assert len(pages) < 20
            assert ids == [row["id"] for row in expected["items"]], (kind, sort, order)
            for index in range(len(pages)-1, 0, -1):
                current = pages[index][1]
                previous = get(client, inventory, kind, limit=7, offset=pages[index-1][0],
                    cursor=current["previous_cursor"], **params)
                assert [row["id"] for row in previous["items"]] == [row["id"] for row in pages[index-1][1]["items"]], (kind,sort,order)


def test_counts_reuse_across_sort_and_page_and_invalidate_on_raw_writes(client, inventory, db_session):
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        if "count(" in statement.lower(): statements.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        first = get(client, inventory, "assets", type="server", limit=7)
        assert statements
        statements.clear()
        second = get(client, inventory, "assets", type="server", sort="hostname", limit=7)
        assert second["total"] == first["total"] and not statements
        asset = next(a for a in inventory[2] if a.type == "server")
        db_session.execute(text("UPDATE assets SET archived_at=now() WHERE id=:id"), {"id": asset.id}); db_session.commit()
        assert get(client, inventory, "assets", type="server")["total"] == first["total"]-1
        assert statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_stale_tampered_and_wrong_scope_cursors_fall_back_to_exact_offset(client, inventory, db_session):
    first = get(client, inventory, "assets", limit=7)
    cursor = first["next_cursor"]
    assert cursor
    for token in (cursor+"x", "malformed", get(client,inventory,"findings",limit=7)["next_cursor"]):
        actual = get(client,inventory,"assets",limit=7,offset=7,cursor=token)
        expected = get(client,inventory,"assets",limit=7,offset=7)
        assert actual["items"] == expected["items"]
    db_session.execute(text("UPDATE assets SET hostname='changed' WHERE id=:id"), {"id": inventory[2][0].id}); db_session.commit()
    assert get(client,inventory,"assets",limit=7,offset=7,cursor=cursor)["items"] == get(client,inventory,"assets",limit=7,offset=7)["items"]


def test_names_membership_and_workflow_invalidate_finding_counts(client, inventory, db_session):
    headers, org, assets, findings, user = inventory
    old = get(client,inventory,"findings",q="Zulu")["total"]
    assert old > 0
    db_session.execute(text("UPDATE users SET name='Renamed' WHERE id=:id"), {"id": user.id}); db_session.commit()
    assert get(client,inventory,"findings",q="Zulu")["total"] == 0
    assert get(client,inventory,"findings",q="Renamed")["total"] == old
    before = get(client,inventory,"findings",workflow_status="open")["total"]
    db_session.execute(text("UPDATE findings SET workflow_status='resolved' WHERE id=:id"), {"id": findings[0].id}); db_session.commit()
    assert get(client,inventory,"findings",workflow_status="open")["total"] == before-1
    db_session.execute(text("DELETE FROM org_memberships WHERE org_id=:org AND user_id=:id"), {"org":org,"id":user.id}); db_session.commit()
    assert get(client,inventory,"findings",q="Renamed")["total"] == 0


def test_uncommitted_changes_never_publish_reusable_counts(client, inventory, db_session):
    org = inventory[1]
    original = list_pages.revision_stamp(db_session, org, "assets")
    assert original is not None
    db_session.execute(text("UPDATE assets SET hostname='temporary' WHERE id=:id"), {"id": inventory[2][0].id})
    assert list_pages.revision_stamp(db_session, org, "assets") is None
    db_session.rollback()
    assert list_pages.revision_stamp(db_session, org, "assets") == original


@pytest.mark.parametrize("kind,sort", [("assets","created"),("findings","severity"),("findings","finding")])
def test_valid_cursor_does_not_execute_deep_offset(client, inventory, db_session, kind, sort):
    first = get(client, inventory, kind, limit=7, sort=sort)
    offsets = []
    def record(conn, cursor, statement, parameters, context, executemany):
        clause = getattr(getattr(context.compiled, "statement", None), "_offset_clause", None)
        if clause is not None:
            offsets.append(context.compiled_parameters[0][context.compiled.bind_names[clause]])
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        get(client, inventory, kind, limit=7, offset=7, sort=sort)
        assert 7 in offsets
        offsets.clear()
        get(client, inventory, kind, limit=7, offset=7, sort=sort, cursor=first["next_cursor"])
        assert not any(offset > 0 for offset in offsets)
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_count_deadline_clock_reversal_and_capacity(inventory, db_session, monkeypatch):
    stamp = list_pages.revision_stamp(db_session, inventory[1], "assets")
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    deadline = now + timedelta(seconds=10)
    calls = []
    def build():
        calls.append(1)
        return len(calls)
    monkeypatch.setattr(list_pages, "_counts", list_pages.OrderedDict())
    monkeypatch.setattr(list_pages, "MAX_COUNTS", 2)
    def count(clock, key="deadline"):
        return list_pages.exact_counts(db_session, stamp, "assets", key, build,
            asof=clock, boundary=lambda: deadline).value
    assert count(now) == count(now + timedelta(seconds=1)) == 1
    assert count(now-timedelta(seconds=1)) == 2
    assert count(deadline) == 3
    count(now, "other"); count(now, "third")
    assert len(list_pages._counts) == 2


def test_overdue_count_and_cursor_expire_when_deadline_passes(client, inventory, db_session, monkeypatch):
    from app.api.routes import findings as route
    clock = datetime(2026, 10, 30, tzinfo=timezone.utc)
    identifier = inventory[3][0].id
    db_session.execute(text("""UPDATE findings SET workflow_status='open',due_date='2026-10-30',
        due_expires_at=:expiry WHERE id=:id"""), {"expiry":clock+timedelta(seconds=1),"id":identifier})
    db_session.commit()
    monkeypatch.setattr(route, "deadline_now", lambda: clock)
    before = get(client, inventory, "findings", overdue="due", limit=7)
    clock += timedelta(seconds=2)
    after = get(client, inventory, "findings", overdue="due", limit=7)
    assert after["total"] == before["total"] + 1
    if before["next_cursor"]:
        stale = get(client, inventory, "findings", overdue="due", limit=7,offset=7,cursor=before["next_cursor"])
        assert stale["items"] == get(client, inventory, "findings", overdue="due",limit=7,offset=7)["items"]


@pytest.mark.parametrize("description", ["x" * 10000, "漢" * 400])
def test_long_and_multibyte_text_remain_importable_and_sort_exactly(client, inventory, db_session, description):
    identifier = inventory[3][0].id
    db_session.execute(text("UPDATE findings SET description=:value WHERE id=:id"),
        {"value":description,"id":identifier})
    db_session.commit()
    for order in ("asc", "desc"):
        expected = get(client, inventory, "findings", sort="finding", order=order, limit=500)
        assert str(identifier) in [item["id"] for item in expected["items"]]
        ids, offset, cursor = [], 0, None
        while True:
            page = get(client, inventory, "findings", sort="finding", order=order, limit=7,
                offset=offset, **({"cursor":cursor} if cursor else {}))
            ids.extend(item["id"] for item in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
            offset += len(page["items"])
        assert ids == [item["id"] for item in expected["items"]]
    filtered = get(client, inventory, "findings", finding="Finding", sort="finding", limit=500)
    assert str(identifier) not in [item["id"] for item in filtered["items"]]


def test_assignee_groups_preserve_database_collation_and_duplicate_labels(client, inventory, db_session):
    from app.api.routes import findings as route
    users = [User(email=f"collation-{i}@example.com",name=name) for i,name in enumerate(("Émile","Zebra","Zulu","zulu"))]
    db_session.add_all(users); db_session.flush()
    db_session.add_all(OrgMembership(org_id=inventory[1],user_id=u.id,role=UserRole.auditor) for u in users)
    for i,finding in enumerate(inventory[3][:20]):
        finding.assignee_id = users[i%len(users)].id
    db_session.commit()
    for direction in ("asc","desc"):
        label = func.lower(route._ASSIGNEE_LABEL)
        primary = label.asc().nulls_last() if direction == "asc" else label.desc().nulls_last()
        expected = list(db_session.scalars(select(Finding.id).where(Finding.org_id == inventory[1])
            .order_by(primary,route._SEVERITY_RANK,Finding.created_at.desc(),Finding.id)))
        actual = get(client,inventory,"findings",sort="assignee",order=direction,limit=500)
        assert [item["id"] for item in actual["items"]] == [str(identifier) for identifier in expected]
        first = get(client,inventory,"findings",sort="assignee",order=direction,limit=7)
        second = get(client,inventory,"findings",sort="assignee",order=direction,limit=7,offset=7,cursor=first["next_cursor"])
        assert [item["id"] for item in second["items"]] == [str(identifier) for identifier in expected[7:14]]


def test_high_cardinality_deadlines_keep_full_exact_sort(client, inventory, db_session):
    from app.api.routes import findings as route
    beginning = datetime(2027,1,1,tzinfo=timezone.utc)
    db_session.add_all(Finding(org_id=inventory[1],domain=Domain.identity_access,severity=Severity.high,
        description=f"dated-{i}",due_date=(beginning+timedelta(days=i)).date(),
        due_expires_at=beginning+timedelta(days=i)) for i in range(1100))
    db_session.commit()
    expected = list(db_session.scalars(select(Finding.id).where(Finding.org_id == inventory[1])
        .order_by(route._DUE_EXPIRY.asc().nulls_last(),route._SEVERITY_RANK,Finding.created_at.desc(),Finding.id).limit(200)))
    first = get(client,inventory,"findings",sort="due_date",limit=100)
    second = get(client,inventory,"findings",sort="due_date",limit=100,offset=100,cursor=first["next_cursor"])
    assert first["total"] == second["total"] == 1145
    assert [item["id"] for item in first["items"]+second["items"]] == [str(identifier) for identifier in expected]


@pytest.mark.parametrize("sort,asset_filter", [("asset",None),("assignee",None),("asset","host")])
def test_counts_keep_required_filter_joins_without_sort_only_joins(client, inventory, db_session, monkeypatch, sort, asset_filter):
    monkeypatch.setattr(list_pages,"_counts",list_pages.OrderedDict())
    statements = []
    def record(conn,cursor,statement,parameters,context,many):
        if "group by findings.domain" in statement.lower():
            statements.append(statement.lower())
    engine = db_session.get_bind()
    event.listen(engine,"before_cursor_execute",record)
    try:
        page = get(client,inventory,"findings",sort=sort,**({"asset":asset_filter} if asset_filter else {}))
        assert page["total"] > 0 and statements
        assert all(("join assets" in statement) == bool(asset_filter) for statement in statements)
        assert all("dense_rank" not in statement for statement in statements)
    finally:
        event.remove(engine,"before_cursor_execute",record)


def test_asset_sort_preserves_legacy_archived_asset_labels(client, inventory, db_session):
    asset = inventory[2][1]
    db_session.execute(text("UPDATE assets SET archived_at=now(),hostname='archived-label' WHERE id=:id"),{"id":asset.id})
    db_session.commit()
    result = get(client,inventory,"findings",sort="asset",limit=500)
    linked = [item for item in result["items"] if item["asset_id"] == str(asset.id)]
    assert linked and all(item["asset_hostname"] == "archived-label" for item in linked)
    assert result["total"] == len(result["items"]) == 45
