"""Combined search is a candidate accelerator, never the match authority."""
from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import select, text, func
from app.api.paging import contains, contains_pattern
from app.api.routes import assets as routes
from app.db.asset_search import INDEX, expression
from app.models.asset import Asset
from app.models.organization import Organization
from tests.conftest import requires_db
from tests.helpers import first_org_id, register

pytestmark = requires_db


@pytest.fixture
def inventory(client, db_session):
    headers = register(client, "search-index@example.com")
    org = uuid.UUID(first_org_id(client, headers))
    foreign = Organization(name="Other search tenant")
    db_session.add(foreign); db_session.flush()
    target = Asset(org_id=org, type="network_device", hostname="webneedle", ip="10.0.9.1", cloud_id="arn:search-target",
        subtype="router-needle", environment="production-east", criticality="priority-high",
        tags=["tagneedle", "tag%match", "under_score", r"back\slash", "München", "汉字测试", "zzshort", "needle' OR 1=1 --"])
    boundary = Asset(org_id=org, type="application", hostname="leftedge", ip="rightedge", tags=None)
    db_session.add_all([target, boundary,
        Asset(org_id=org, type="server", hostname="tagXmatch", tags=["underXscore"]),
        Asset(org_id=foreign.id, type="server", hostname="foreignneedle", tags=["foreignneedle"]),
        Asset(org_id=org, type="server", hostname="archivedneedle", tags=["archivedneedle"], archived_at=datetime.now(timezone.utc)),
    ])
    db_session.add_all(Asset(org_id=org, type="server", hostname=f"filler-{i}", tags=["shared-production-tag"]) for i in range(100))
    db_session.commit()
    db_session.execute(text("ANALYZE assets")); db_session.commit()
    return headers, org, target.id


def get(client, inventory, **filters):
    headers, org, _ = inventory
    response = client.get(f"/api/v1/orgs/{org}/assets", headers=headers, params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def test_index_candidates_preserve_literal_unicode_label_and_boundary_matching(client, inventory, monkeypatch):
    selected = []
    real = routes.selective_candidates
    def track(*args):
        result = real(*args)
        selected.append(bool(result))
        return result
    monkeypatch.setattr(routes, "selective_candidates", track)
    for value in ("WEBNEEDLE", "10.0.9", "arn:search", "router-needle", "production-east", "priority-high",
                  "tagneedle", "tag%match", "under_score", r"back\slash", "München", "汉字测试", "needle' OR 1=1 --",
                  "Network device", "work", "zz"):
        body = get(client, inventory, q=value)
        assert body["total"] == 1, value
        assert body["items"][0]["id"] == str(inventory[2]), value
    assert any(selected), "Exercise the indexed candidate strategy as well as its fallback"
    for value in ("leftedge\nrightedge", "foreignneedle", "archivedneedle", "missing-tag"):
        assert get(client, inventory, q=value)["total"] == 0
    assert get(client, inventory, tags="tagneedle")["total"] == 1
    assert get(client, inventory, q="tagneedle", environment="other")["total"] == 0
    assert get(client, inventory, q="tagneedle", limit=1, offset=1)["items"] == []


def test_common_type_and_short_search_use_original_path(client, inventory, db_session):
    _, org, _ = inventory
    common = contains("server", Asset.type)
    assert routes.selective_candidates(db_session, Asset, org, [(contains("server", expression(Asset)), common, contains_pattern("server"))]) == []
    assert routes.selective_candidates(db_session, Asset, org, [(contains("production", expression(Asset)),
        contains("production", func.array_to_string(Asset.tags, ' ')), contains_pattern("production"))]) == []
    assert get(client, inventory, q="production")["total"] == 101
    assert get(client, inventory, q="server")["total"] == 101
    assert get(client, inventory, q="%")["total"] == 1
    assert get(client, inventory, q="_")["total"] == 1


def test_null_tag_arrays_do_not_misclassify_a_selective_tag(client, inventory, db_session):
    _, org, _ = inventory
    db_session.execute(text("UPDATE assets SET tags=NULL WHERE hostname LIKE 'filler-%'"))
    db_session.commit()
    db_session.execute(text("ANALYZE assets")); db_session.commit()
    # Element frequencies are conditional on a non-null array. Account for
    # null_frac so a tag on one asset is not treated as common across the org.
    candidates = routes.selective_candidates(db_session, Asset, org, [(contains("tagneedle", expression(Asset)),
        contains("tagneedle", func.array_to_string(Asset.tags, ' ')), contains_pattern("tagneedle"))])
    assert len(candidates) == 1
    assert get(client, inventory, tags="tagneedle")["total"] == 1


def test_database_maintains_index_on_direct_update_archive_restore_and_delete(client, inventory, db_session):
    _, org, target = inventory
    # Isolate index maintenance from cost-based choices on this tiny fixture.
    # A valid organization-index bitmap scan is often cheaper on Linux. Remove
    # competing indexes only in the disposable test DB, retaining the PK/GIN.
    for index in Asset.__table__.indexes:
        if index.name != INDEX:
            index.drop(db_session.connection())

    def indexed_ids(value):
        db_session.execute(text("SET LOCAL enable_seqscan = off"))
        stmt = select(Asset.id).where(Asset.org_id == org, Asset.archived_at.is_(None),
            expression(Asset).ilike(contains_pattern(value), escape="\\"))
        compiled = stmt.compile(dialect=db_session.connection().dialect, compile_kwargs={"render_postcompile": True})
        plan = db_session.connection().exec_driver_sql("EXPLAIN (FORMAT JSON) " + str(compiled), compiled.params).scalar_one()
        assert INDEX in str(plan)
        return list(db_session.scalars(stmt))

    assert indexed_ids("tagneedle") == [target]
    db_session.execute(text("UPDATE assets SET tags=ARRAY['newtagneedle']::varchar[],hostname='renamed' WHERE id=:id"), {"id": target})
    db_session.commit()
    assert get(client, inventory, tags="newtagneedle")["total"] == 1
    assert get(client, inventory, q="webneedle")["total"] == 0
    assert indexed_ids("newtagneedle") == [target]
    assert indexed_ids("webneedle") == []
    db_session.execute(text("UPDATE assets SET archived_at=now() WHERE id=:id"), {"id": target}); db_session.commit()
    assert get(client, inventory, tags="newtagneedle")["total"] == 0
    assert indexed_ids("newtagneedle") == []
    db_session.execute(text("UPDATE assets SET archived_at=NULL WHERE id=:id"), {"id": target}); db_session.commit()
    assert get(client, inventory, tags="newtagneedle")["total"] == 1
    assert indexed_ids("newtagneedle") == [target]
    db_session.execute(text("DELETE FROM assets WHERE id=:id"), {"id": target}); db_session.commit()
    assert get(client, inventory, tags="newtagneedle")["total"] == 0
    assert indexed_ids("newtagneedle") == []


def test_import_pipeline_preserves_indexed_tags_and_records_paired_timings(client, db_session):
    import json
    import time
    from tests.helpers import upload
    index = next(i for i in Asset.__table__.indexes if i.name == INDEX)
    index.drop(db_session.connection()); db_session.commit()
    measurements = {}
    for phase in ("without_index", "with_index"):
        if phase == "with_index":
            index.create(db_session.connection()); db_session.commit()
        headers = register(client, f"write-{phase}@search-index.example")
        org = first_org_id(client, headers)
        for action in ("create", "update"):
            tag = "initial-tag" if action == "create" else "updated-tag"
            content = ("type,hostname,environment,tags\n" + "".join(
                f"server,import-{i},production,{tag};benchmark\n" for i in range(5000))).encode()
            started = time.perf_counter()
            response = upload(client, f"/api/v1/orgs/{org}/assets/import", headers, f"{phase}-{action}.csv", content)
            elapsed = round((time.perf_counter()-started)*1000, 2)
            assert response.status_code == 201, response.text
            report = response.json()["report"]
            assert report["created" if action == "create" else "updated"] == 5000
            measurements[f"{phase}_{action}_ms"] = elapsed
        response = client.get(f"/api/v1/orgs/{org}/assets", headers=headers, params={"tags": "updated-tag", "limit": 1})
        assert response.status_code == 200
        assert response.json()["total"] == 5000
    print("ASSET_IMPORT_TIMINGS " + json.dumps(measurements))
