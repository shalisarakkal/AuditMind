import uuid
import pytest
from sqlalchemy import select, update, text, delete, func
from sqlalchemy.exc import IntegrityError
from app.models.control_catalog import CatalogControl, FindingControlRule, FindingControlDecision, FindingControlTarget
from app.models.membership import OrgMembership
from app.models.user import User
from app.services import control_catalog as service
from tests.conftest import requires_db
from tests.helpers import register, first_org_id, member

pytestmark = requires_db


@pytest.fixture
def catalog_setup(client, db_session):
    headers = register(client, "catalog-platform@example.io")
    org = uuid.UUID(first_org_id(client, headers))
    actor = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == org))
    db_session.execute(update(User).where(User.id == actor).values(is_sysadmin=True))
    db_session.commit()
    installed = service.install_baseline(db_session, actor)
    return dict(headers=headers, org=org, actor=actor, catalog=installed["catalog"]["id"], controls=installed["controls"])


def test_committed_catalog_cannot_gain_unreviewed_control_rows(db_session, catalog_setup):
    n = catalog_setup
    with pytest.raises(IntegrityError):
        db_session.add(CatalogControl(catalog_id=n["catalog"], control_id=uuid.uuid4(), reference="UNREVIEWED", title="Not in verified source", description="Injected after catalog commit"))
        db_session.commit()
    db_session.rollback()


def test_committed_mapping_decision_cannot_gain_extra_targets(db_session, catalog_setup):
    n = catalog_setup
    rule = FindingControlRule(org_id=n["org"], source="manual", domain="identity_access", category="Synthetic", version=1)
    db_session.add(rule)
    db_session.flush()
    decision = FindingControlDecision(org_id=n["org"], rule_id=rule.id, version=1, state="proposed", catalog_id=n["catalog"], rationale="Original scope", actor_id=n["actor"], actor_label="Synthetic reviewer")
    db_session.add(decision)
    db_session.flush()
    db_session.add(FindingControlTarget(decision_id=decision.id, catalog_id=n["catalog"], control_id=n["controls"][0]["control_id"]))
    db_session.commit()
    with pytest.raises(IntegrityError):
        db_session.add(FindingControlTarget(decision_id=decision.id, catalog_id=n["catalog"], control_id=n["controls"][1]["control_id"]))
        db_session.commit()
    db_session.rollback()


def test_install_noop_does_not_wait_for_import_actor_foreign_key_lock(db_session, catalog_setup):
    from sqlalchemy.orm import Session
    n = catalog_setup
    with Session(db_session.get_bind()) as importer:
        importer.execute(select(User.id).where(User.id == n["actor"]).with_for_update(read=True, key_share=True))
        db_session.execute(text("SET LOCAL lock_timeout='600ms'"))
        result = service.install_baseline(db_session, n["actor"])
        assert len(result["controls"]) == 106
        importer.rollback()


def new_finding(client, n, **fields):
    response = client.post(f'/api/v1/orgs/{n["org"]}/findings', headers=n["headers"], json={
        "domain": "identity_access", "source": "manual", "category": "Synthetic control category", "severity": "high", "description": "Synthetic mapping review", **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def proposal(n, version=0, **fields):
    return dict(source="manual", domain="identity_access", category="Synthetic control category", expected_version=version,
        catalog_id=str(n["catalog"]), control_ids=[str(n["controls"][0]["control_id"])], rationale="Reviewed synthetic relevance", **fields)


def test_proposal_approval_noop_stale_and_pending_effective_mapping(client, db_session, catalog_setup):
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    initial = client.get(path, headers=n["headers"])
    assert initial.status_code == 200, initial.text
    assert initial.json()["status"] == "unmapped" and initial.json()["version"] == 0
    proposed = client.post(path + "/proposals", headers=n["headers"], json=proposal(n))
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["version"] == 1 and proposed.json()["status"] == "unmapped"
    assert proposed.json()["proposal"]["catalog"]["content_hash"] == service.NIST_HASH
    again = client.post(path + "/proposals", headers=n["headers"], json=proposal(n, 1))
    assert again.status_code == 200 and again.json()["version"] == 1
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n)).status_code == 409
    approve = dict(source="manual", domain="identity_access", category="Synthetic control category", expected_version=1, proposal_version=1, rationale="Administrator confirms relevance only")
    approved = client.post(path + "/approve", headers=n["headers"], json=approve)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "mapped" and body["version"] == 2 and body["effective"]["proposal_version"] == 1
    other = new_finding(client, n)
    assert client.get(path.replace(finding, other), headers=n["headers"]).json()["effective"]["id"] == body["effective"]["id"]
    revision = proposal(n, 2)
    revision["control_ids"] = [str(n["controls"][1]["control_id"])]
    pending = client.post(path + "/proposals", headers=n["headers"], json=revision)
    assert pending.status_code == 200, pending.text
    assert pending.json()["version"] == 3 and pending.json()["effective"]["id"] == body["effective"]["id"]
    withdrawal = {k: v for k, v in proposal(n, 3).items() if k not in ("catalog_id", "control_ids")}
    withdrawn = client.post(path + "/withdraw", headers=n["headers"], json=withdrawal)
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "unmapped" and withdrawn.json()["version"] == 4
    rule_id = withdrawn.json()["rule_id"]
    history = client.get(f'/api/v1/orgs/{n["org"]}/control-rules/{rule_id}/history', headers=n["headers"])
    assert history.status_code == 200, history.text
    assert [row["state"] for row in history.json()] == ["withdrawn", "proposed", "approved", "proposed"]


@pytest.mark.parametrize("role", ["auditor", "viewer"])
def test_mapping_authorization_and_review_roles(client, catalog_setup, role):
    n = catalog_setup
    headers = member(client, n["headers"], str(n["org"]), role)
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    response = client.post(path + "/proposals", headers=headers, json=proposal(n))
    assert response.status_code == (200 if role == "auditor" else 403), response.text
    assert client.get(path, headers=headers).status_code == 200
    assert client.post('/api/v1/platform/control-catalogs/baseline', headers=headers).status_code == 403
    approve = dict(source="manual", domain="identity_access", category="Synthetic control category", expected_version=1, proposal_version=1, rationale="Unauthorized approval attempt")
    assert client.post(path + "/approve", headers=headers, json=approve).status_code == 403


def test_catalog_source_is_current_hashed_and_installation_is_noop(client, catalog_setup):
    n = catalog_setup
    release, controls = service.baseline()
    assert release["content_hash"] == service.NIST_HASH and len(controls) == 106
    assert "RC.CO-01" not in {c["reference"] for c in controls}
    response = client.post('/api/v1/platform/control-catalogs/baseline', headers=n["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["catalog"]["id"] == str(n["catalog"])


def test_foreign_org_and_platform_privilege_cannot_write_category_rules(client, db_session, catalog_setup):
    n = catalog_setup
    foreign = register(client, "catalog-foreign@example.io")
    other_org = uuid.UUID(first_org_id(client, foreign))
    outsider = db_session.scalar(select(OrgMembership.user_id).where(OrgMembership.org_id == other_org))
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    assert client.get(path, headers=foreign).status_code == 403
    assert client.post(path + "/proposals", headers=foreign, json=proposal(n)).status_code == 403
    db_session.execute(update(User).where(User.id == outsider).values(is_sysadmin=True))
    db_session.commit()
    assert client.get(path, headers=foreign).status_code == 200
    assert client.post(path + "/proposals", headers=foreign, json=proposal(n)).status_code == 403
    wrong_path = path.replace(str(n["org"]), str(other_org))
    assert client.get(wrong_path, headers=foreign).status_code == 404


@pytest.mark.parametrize("damage", ["trigger", "table", "wrong_function", "wrong_completion_function"])
def test_missing_guards_fail_closed(client, db_session, catalog_setup, damage):
    n = catalog_setup
    finding = new_finding(client, n)
    if damage == "trigger":
        db_session.execute(text("ALTER TABLE finding_control_targets DISABLE TRIGGER am_control_catalog_guard"))
    elif damage.startswith("wrong_"):
        db_session.execute(text("CREATE OR REPLACE FUNCTION am_catalog_wrong_hook_test() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END$$"))
        if damage == "wrong_function":
            db_session.execute(text("CREATE OR REPLACE TRIGGER am_control_catalog_guard BEFORE INSERT OR UPDATE OR DELETE ON finding_control_targets FOR EACH ROW EXECUTE FUNCTION am_catalog_wrong_hook_test()"))
        else:
            db_session.execute(text("DROP TRIGGER am_control_decision_complete ON finding_control_decisions"))
            db_session.execute(text("CREATE CONSTRAINT TRIGGER am_control_decision_complete AFTER INSERT ON finding_control_decisions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION am_catalog_wrong_hook_test()"))
    else:
        db_session.execute(text("DROP TABLE finding_control_targets"))
    db_session.commit()
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    response = client.get(path, headers=n["headers"])
    assert response.status_code == 200 and not response.json()["available"]
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n)).status_code == 409


def test_wrong_source_changed_category_and_uninstalled_targets_are_refused(client, db_session, catalog_setup):
    from app.models.finding import Finding
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    for payload in (dict(proposal(n), source="other-source"), dict(proposal(n), category="Other category")):
        assert client.post(path + "/proposals", headers=n["headers"], json=payload).status_code == 409
    for payload in (dict(proposal(n), catalog_id=str(uuid.uuid4())), dict(proposal(n), control_ids=[str(uuid.uuid4())])):
        assert client.post(path + "/proposals", headers=n["headers"], json=payload).status_code == 422
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n)).status_code == 200
    db_session.execute(update(Finding).where(Finding.id == uuid.UUID(finding)).values(category="Changed by source"))
    db_session.commit()
    assert client.get(path, headers=n["headers"]).json()["status"] == "unmapped"
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n, 1)).status_code == 409


def test_catalog_and_decision_rows_and_effective_pointer_are_protected(client, db_session, catalog_setup):
    from app.models.control_catalog import ControlCatalog
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    response = client.post(path + "/proposals", headers=n["headers"], json=proposal(n))
    assert response.status_code == 200, response.text
    rule = uuid.UUID(response.json()["rule_id"])
    decision = uuid.UUID(response.json()["proposal"]["id"])
    forbidden = [update(ControlCatalog).where(ControlCatalog.id == n["catalog"]).values(title="Rewritten release"),
        update(FindingControlDecision).where(FindingControlDecision.id == decision).values(rationale="Rewritten rationale"),
        delete(FindingControlDecision).where(FindingControlDecision.id == decision),
        update(FindingControlRule).where(FindingControlRule.id == rule).values(version=2, effective_version=1)]
    for statement in forbidden:
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.execute(statement)
    db_session.rollback()
    assert client.get(path, headers=n["headers"]).json()["status"] == "unmapped"


def test_atomic_rollback_and_report_snapshots_and_findings_are_unchanged(client, db_session, catalog_setup, monkeypatch):
    from app.models.report import Report
    from app.models.finding import Finding
    n = catalog_setup
    finding = new_finding(client, n)
    report = Report(org_id=n["org"], title="Synthetic saved snapshot", status="completed", data={"source": "Synthetic", "controls": ["original"], "score": 42})
    db_session.add(report)
    db_session.commit()
    original_report = db_session.scalar(text("SELECT data::text FROM reports WHERE id=:id"), {"id": report.id})
    original_finding = db_session.execute(select(Finding.workflow_status, Finding.workflow_version, Finding.severity).where(Finding.id == uuid.UUID(finding))).one()
    db_session.commit()
    original = service.record_event
    def fail(*args, **kwargs):
        db_session.flush()
        raise RuntimeError("Injected after decision and target flush")
    monkeypatch.setattr(service, "record_event", fail)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    with pytest.raises(RuntimeError):
        client.post(path + "/proposals", headers=n["headers"], json=proposal(n))
    assert db_session.scalar(select(func.count()).select_from(FindingControlRule)) == 0
    assert db_session.scalar(select(func.count()).select_from(FindingControlDecision)) == 0
    monkeypatch.setattr(service, "record_event", original)
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n)).status_code == 200
    assert db_session.scalar(text("SELECT data::text FROM reports WHERE id=:id"), {"id": report.id}) == original_report
    assert db_session.execute(select(Finding.workflow_status, Finding.workflow_version, Finding.severity).where(Finding.id == uuid.UUID(finding))).one() == original_finding


@pytest.mark.parametrize("damage", ["missing_decision", "empty_approval"])
def test_database_cannot_publish_incomplete_mapping_generations(client, db_session, catalog_setup, damage):
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    response = client.post(path + "/proposals", headers=n["headers"], json=proposal(n))
    assert response.status_code == 200, response.text
    rule = db_session.get(FindingControlRule, uuid.UUID(response.json()["rule_id"]))
    with pytest.raises(IntegrityError):
        if damage == "empty_approval":
            db_session.add(FindingControlDecision(org_id=n["org"], rule_id=rule.id, version=2, state="approved", catalog_id=n["catalog"], proposal_version=1, rationale="Must not publish missing targets", actor_id=n["actor"], actor_label="Synthetic reviewer"))
            db_session.flush()
            rule.effective_version = 2
        rule.version = 2
        db_session.commit()
    db_session.rollback()


def test_import_write_and_concurrent_reviewers_do_not_overwrite_rules(client, db_session, catalog_setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from fastapi import HTTPException
    from sqlalchemy.orm import Session
    from app.models.finding import Finding
    from app.schemas.control_catalog import MappingProposal
    n = catalog_setup
    finding = uuid.UUID(new_finding(client, n))
    # A scanner may own the non-key source row and list-revision lane. Mapping
    # metadata must not wait on either while preserving the reviewed tuple.
    with Session(db_session.get_bind()) as importer:
        importer.execute(update(Finding).where(Finding.id == finding).values(description="Uncommitted scanner description"))
        db_session.execute(text("SET LOCAL lock_timeout='700ms'"))
        result = service.change(db_session, n["org"], finding, n["actor"], MappingProposal(**proposal(n)), "propose")
        assert result["version"] == 1
        importer.rollback()
    held, release, attempted = Event(), Event(), Event()
    original = service.record_event
    def hold(*args, **kwargs):
        if kwargs["details"]["rationale"] == "First concurrent proposal":
            held.set()
            assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(service, "record_event", hold)
    engine = db_session.get_bind()
    def write(reason):
        if reason != "First concurrent proposal":
            attempted.set()
        with Session(engine) as session:
            payload = dict(proposal(n, 1), rationale=reason)
            try:
                result = service.change(session, n["org"], finding, n["actor"], MappingProposal(**payload), "propose")
                return 200, result["version"]
            except HTTPException as exc:
                return exc.status_code, None
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, "First concurrent proposal")
        try:
            assert held.wait(10)
            second = pool.submit(write, "Second concurrent proposal")
            assert attempted.wait(10)
        finally:
            release.set()
        assert first.result(timeout=10) == (200, 2)
        assert second.result(timeout=10) == (409, None)


def test_archive_restore_source_purge_and_tenant_purge_retention(client, db_session, catalog_setup):
    from app.models.finding import Finding
    from app.models.organization import Organization
    from app.models.control_catalog import ControlCatalog
    n = catalog_setup
    finding = new_finding(client, n)
    root = f'/api/v1/orgs/{n["org"]}'
    path = root + f'/findings/{finding}/control-mapping'
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n)).status_code == 200
    response = client.post(root + f'/findings/{finding}/archive', headers=n["headers"])
    assert response.status_code == 200, response.text
    assert client.get(path, headers=n["headers"]).json()["inactive"]
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n, 1)).status_code == 409
    archived = client.get(root + '/archive', headers=n["headers"]).json()["items"][0]
    response = client.post(root + '/archive/' + archived["id"] + '/restore', headers=n["headers"])
    assert response.status_code == 200, response.text
    restored = client.get(path, headers=n["headers"]).json()
    assert not restored["inactive"] and restored["version"] == 1
    rule_id = restored["rule_id"]
    db_session.execute(delete(Finding).where(Finding.id == uuid.UUID(finding)))
    db_session.commit()
    assert client.get(path, headers=n["headers"]).status_code == 404
    assert client.get(root + f'/control-rules/{rule_id}/history', headers=n["headers"]).status_code == 200
    db_session.execute(delete(Organization).where(Organization.id == n["org"]))
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(FindingControlDecision).where(FindingControlDecision.org_id == n["org"])) == 0
    assert db_session.get(ControlCatalog, n["catalog"]) is not None


def test_readiness_does_not_borrow_another_schema_catalog(db_session):
    schema = "catalog_legacy_" + uuid.uuid4().hex
    try:
        db_session.execute(text(f'CREATE SCHEMA "{schema}"'))
        db_session.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
        assert not service.available(db_session), "Legacy schema borrowed the public catalog activation"
    finally:
        db_session.rollback()


@pytest.mark.parametrize("damage", ["approval_not_applied", "withdrawal_not_cleared"])
def test_review_state_and_effective_projection_cannot_disagree(client, db_session, catalog_setup, damage):
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    response = client.post(path + "/proposals", headers=n["headers"], json=proposal(n))
    assert response.status_code == 200, response.text
    rule_id = uuid.UUID(response.json()["rule_id"])
    if damage == "withdrawal_not_cleared":
        approval = {k: v for k, v in proposal(n, 1).items() if k not in ("catalog_id", "control_ids")}
        approval["proposal_version"] = 1
        assert client.post(path + "/approve", headers=n["headers"], json=approval).status_code == 200
    rule = db_session.get(FindingControlRule, rule_id, populate_existing=True)
    with pytest.raises(IntegrityError):
        decision = FindingControlDecision(org_id=n["org"], rule_id=rule.id, version=rule.version + 1,
            state="approved" if damage == "approval_not_applied" else "withdrawn", catalog_id=n["catalog"],
            proposal_version=1 if damage == "approval_not_applied" else None, rationale="Synthetic inconsistent projection", actor_id=n["actor"], actor_label="Synthetic reviewer")
        db_session.add(decision)
        db_session.flush()
        if damage == "approval_not_applied":
            db_session.add(FindingControlTarget(decision_id=decision.id, catalog_id=n["catalog"], control_id=n["controls"][0]["control_id"]))
        rule.version = decision.version
        # Deliberately preserve the old effective pointer: neither should commit.
        db_session.commit()
    db_session.rollback()


def test_new_catalog_revision_preserves_old_mapping_and_saved_report(client, db_session, catalog_setup, monkeypatch):
    from app.models.report import Report
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    assert client.post(path + "/proposals", headers=n["headers"], json=proposal(n)).status_code == 200
    approval = {k: v for k, v in proposal(n, 1).items() if k not in ("catalog_id", "control_ids")}
    approval["proposal_version"] = 1
    original = client.post(path + "/approve", headers=n["headers"], json=approval)
    assert original.status_code == 200, original.text
    original = original.json()["effective"]
    report = Report(org_id=n["org"], title="Synthetic prior report", status="completed", data={"catalog_id": str(n["catalog"]), "mapping": original})
    db_session.add(report)
    db_session.commit()
    saved = db_session.scalar(text("SELECT data::text FROM reports WHERE id=:id"), {"id": report.id})
    db_session.commit()
    release, controls = service.baseline()
    # Simulate a later trusted producer revision; no external standard text or
    # licensing claim is introduced by this synthetic test source.
    newer = dict(release, id=uuid.uuid4(), framework="SYNTHETIC", edition="synthetic-revision-2", title="Synthetic later release", source="local:synthetic", rights="Synthetic fixture only", content_hash="b" * 64)
    revised = dict(n["controls"][0], title="Synthetic revised outcome", description="Synthetic later description")
    monkeypatch.setattr(service, "baseline", lambda: (newer, [revised]))
    assert client.post('/api/v1/platform/control-catalogs/baseline', headers=n["headers"]).status_code == 200
    assert client.get(path, headers=n["headers"]).json()["effective"] == original
    changed = dict(proposal(n, 2), catalog_id=str(newer["id"]), control_ids=[str(revised["control_id"])])
    proposed = client.post(path + "/proposals", headers=n["headers"], json=changed)
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["effective"] == original
    approval.update(expected_version=3, proposal_version=3)
    approved = client.post(path + "/approve", headers=n["headers"], json=approval)
    assert approved.status_code == 200, approved.text
    assert approved.json()["effective"]["catalog"]["id"] == str(newer["id"])
    assert approved.json()["effective"]["controls"][0]["description"] == revised["description"]
    assert db_session.scalar(text("SELECT data::text FROM reports WHERE id=:id"), {"id": report.id}) == saved
    history = client.get(f'/api/v1/orgs/{n["org"]}/control-rules/{approved.json()["rule_id"]}/history', headers=n["headers"]).json()
    assert next(row for row in history if row["version"] == 2) == original


def test_admin_can_retire_category_rule_after_originating_finding_is_purged(client, db_session, catalog_setup):
    from app.models.finding import Finding
    n = catalog_setup
    finding = new_finding(client, n)
    path = f'/api/v1/orgs/{n["org"]}/findings/{finding}/control-mapping'
    proposed = client.post(path + "/proposals", headers=n["headers"], json=proposal(n))
    assert proposed.status_code == 200, proposed.text
    rule_id = proposed.json()["rule_id"]
    approval = {k: v for k, v in proposal(n, 1).items() if k not in ("catalog_id", "control_ids")}
    approval["proposal_version"] = 1
    assert client.post(path + "/approve", headers=n["headers"], json=approval).status_code == 200
    db_session.execute(delete(Finding).where(Finding.id == uuid.UUID(finding)))
    db_session.commit()
    retained = f'/api/v1/orgs/{n["org"]}/control-rules/{rule_id}'
    response = client.get(retained, headers=n["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["context_kind"] == "rule" and response.json()["finding_id"] is None
    assert response.json()["status"] == "mapped"
    withdrawal = {k: v for k, v in proposal(n, 2).items() if k not in ("catalog_id", "control_ids")}
    response = client.post(retained + "/withdraw", headers=n["headers"], json=withdrawal)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "unmapped" and response.json()["version"] == 3
    reproposed = client.post(retained + "/proposals", headers=n["headers"], json=proposal(n, 3))
    assert reproposed.status_code == 200, reproposed.text
    assert reproposed.json()["context_kind"] == "rule" and reproposed.json()["version"] == 4
    approval.update(expected_version=4, proposal_version=4)
    approved = client.post(retained + "/approve", headers=n["headers"], json=approval)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "mapped" and approved.json()["version"] == 5
    assert client.post(retained + "/proposals", headers=n["headers"], json=proposal(n, 4)).status_code == 409
    assert client.post(retained + "/proposals", headers=n["headers"], json=dict(proposal(n, 5), category="Unreviewed different scope")).status_code == 409
    viewer = member(client, n["headers"], str(n["org"]), "viewer")
    assert client.get(retained, headers=viewer).status_code == 200
    assert client.post(retained + "/withdraw", headers=viewer, json=dict(withdrawal, expected_version=3)).status_code == 403
    other = register(client, "retained-rule-foreign@example.io")
    assert client.get(retained, headers=other).status_code == 403
