"""Bounded page metadata and indexed category lookups; not a SaaS load test."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import event, insert, select, text
from app.models.control_catalog import FindingControlRule, FindingControlDecision, FindingControlTarget
from app.models.finding import Finding
from app.services import control_catalog as service, list_pages
from tests.conftest import requires_db
from tests.integration.test_control_catalog import catalog_setup, new_finding, proposal

pytestmark = requires_db


def test_page_summaries_and_history_use_bounded_queries_and_scoped_indexes(client, db_session, catalog_setup):
    n = catalog_setup
    first_finding = new_finding(client, n)
    now = datetime.now(timezone.utc)
    rules, decisions, targets = [], [], []
    for index in range(5000):
        rule_id, decision_id = uuid.uuid4(), uuid.uuid4()
        category = "Synthetic control category" if index == 0 else f"bulk-{index}"
        rules.append(dict(id=rule_id, org_id=n["org"], source="manual", domain="identity_access", category=category, version=1))
        decisions.append(dict(id=decision_id, org_id=n["org"], rule_id=rule_id, version=1, state="proposed", catalog_id=n["catalog"], rationale="Synthetic indexed review", actor_id=n["actor"], actor_label="Synthetic reviewer", created_at=now))
        targets.append(dict(decision_id=decision_id, catalog_id=n["catalog"], control_id=n["controls"][0]["control_id"]))
    db_session.execute(insert(FindingControlRule), rules)
    db_session.execute(insert(FindingControlDecision), decisions)
    db_session.execute(insert(FindingControlTarget), targets)
    db_session.execute(insert(Finding), [dict(id=uuid.uuid4(), org_id=n["org"], source="manual", domain="identity_access", severity="high", category=f"bulk-{i}", description="Synthetic page metadata probe", created_at=now) for i in range(1, 105)])
    db_session.commit()
    for table in ("finding_control_rules", "finding_control_decisions", "finding_control_targets"):
        db_session.execute(text(f"ANALYZE {table}"))
    db_session.commit()
    plan = db_session.scalar(text("EXPLAIN (FORMAT JSON) SELECT id FROM finding_control_rules WHERE org_id=:org AND source='manual' AND domain='identity_access' AND category='Synthetic control category'"), {"org": n["org"]})
    assert "uq_finding_control_rule_key" in str(plan), plan
    queries = []
    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get(f'/api/v1/orgs/{n["org"]}/findings?limit=100', headers=n["headers"])
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 105 and len(body["items"]) == 100
        assert all(item["control_mapping"]["status"] == "unmapped" and item["control_mapping"]["proposal_pending"] for item in body["items"])
        metadata_queries = [q for q in queries if "FROM finding_control_rules" in q or "FROM finding_control_decisions" in q]
        assert len(metadata_queries) <= 2, metadata_queries
        assert all("raw_data" not in q and "description" not in q for q in metadata_queries)
        rows = db_session.scalars(select(FindingControlDecision).limit(50)).all()
        queries.clear()
        assert len(service.decisions_data(db_session, rows)) == 50
        assert len(queries) <= 2, queries
    finally:
        event.remove(engine, "before_cursor_execute", record)
    path = f'/api/v1/orgs/{n["org"]}/findings/{first_finding}/control-mapping'
    lookup = f'/api/v1/orgs/{n["org"]}/findings?finding_id={first_finding}'
    assert client.get(lookup, headers=n["headers"]).json()["items"][0]["control_mapping"]["status"] == "unmapped"
    before = list_pages.revision_stamp(db_session, n["org"], "findings")
    db_session.commit()
    approval = {k: v for k, v in proposal(n, 1).items() if k not in ("catalog_id", "control_ids")}
    approval["proposal_version"] = 1
    response = client.post(path + "/approve", headers=n["headers"], json=approval)
    assert response.status_code == 200, response.text
    assert list_pages.revision_stamp(db_session, n["org"], "findings") == before
    assert client.get(lookup, headers=n["headers"]).json()["items"][0]["control_mapping"]["status"] == "mapped"
