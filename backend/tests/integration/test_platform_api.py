"""The Sysadmin, organizations' lifecycle and the security settings screens
(Phase 2e part 3)."""

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.asset import Asset
from app.models.enums import ScanStatus
from app.models.event import Event
from app.models.organization import Organization
from app.models.scan import Scan
from app.models.user import User
from app.services import platform
from app.services.people import PeopleError
from app.worker.runner import drain
from tests.conftest import requires_db
from tests.helpers import PASSWORD, first_org_id, register

pytestmark = requires_db

AUTH = "/api/v1/auth"
P = "/api/v1/platform"
NEW_PASSWORD = "A-much-longer-passphrase-2026"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password=PASSWORD):
    return client.post(f"{AUTH}/login", json={"email": email, "password": password})


def first_sign_in(client, email, temporary) -> dict[str, str]:
    headers = bearer(login(client, email, temporary).json()["access_token"])
    resp = client.post(
        f"{AUTH}/change-password", json={"current_password": temporary, "new_password": NEW_PASSWORD}, headers=headers
    )
    assert resp.status_code == 204, resp.text
    return headers


def events(db, type, org_id="any") -> list[Event]:
    db.expire_all()
    query = select(Event).where(Event.type == type)
    if org_id != "any":
        query = query.where(Event.org_id.is_(None) if org_id is None else Event.org_id == org_id)
    return db.scalars(query.order_by(Event.started_at)).all()


@pytest.fixture
def root(client, db_session):
    """The Sysadmin's headers (made as scripts/create_sysadmin.py does)."""
    temporary = platform.create_sysadmin(db_session, "root@platform.io", "Root")
    db_session.commit()
    return first_sign_in(client, "root@platform.io", temporary)


@pytest.fixture
def acme(client):
    ann = register(client, "ann@acme.io", "Acme")
    return first_org_id(client, ann), ann


# --- The Sysadmin ---------------------------------------------------------------


def test_the_sysadmin_belongs_to_no_org_and_reads_every_org(client, db_session, root, acme):
    org_id, _ = acme
    me = client.get(f"{AUTH}/me", headers=root).json()
    assert me["is_sysadmin"] is True
    [org] = client.get("/api/v1/orgs", headers=root).json()
    assert (org["id"], org["role"], org["access"]) == (org_id, "viewer", "sysadmin")
    assert client.get(f"/api/v1/orgs/{org_id}/assets", headers=root).status_code == 200
    # Read-only: no change to an org's data.
    resp = client.post(f"/api/v1/orgs/{org_id}/findings", json={"domain": "network_config", "severity": "low"}, headers=root)
    assert resp.status_code == 403
    assert client.post(f"/api/v1/orgs/{org_id}/members", json={"email": "x@acme.io"}, headers=root).status_code == 403
    [created] = events(db_session, "sysadmin_created", None)
    assert created.item == "root@platform.io"


def test_only_the_sysadmin_reaches_the_platform(client, acme):
    _, ann = acme
    for path in ("/orgs", "/users", "/events", "/security"):
        assert client.get(P + path, headers=ann).status_code == 403


def test_a_sysadmin_needs_an_account_of_its_own(client, db_session, acme):
    with pytest.raises(PeopleError) as refused:
        platform.create_sysadmin(db_session, "ann@acme.io", None)
    assert refused.value.code == "email_taken"


def test_the_script(db_session, monkeypatch, capsys):
    import scripts.create_sysadmin as script

    monkeypatch.setattr(script, "SessionLocal", lambda: _Same(db_session))
    assert script.main(["--email", "Root@Platform.io", "--name", "Root"]) == 0
    out = capsys.readouterr().out
    assert "Sysadmin root@platform.io created." in out and "Temporary password" in out
    assert script.main(["--email", "root@platform.io"]) == 1
    assert script.main(["--email", "not-an-email"]) == 2


class _Same:
    """The test's session as a context manager (the script closes its own)."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


# --- Sign-up ------------------------------------------------------------------


def test_sign_up_is_closed_unless_turned_on(client, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP", False)
    assert client.get(f"{AUTH}/options").json() == {"public_signup": False}
    resp = client.post(f"{AUTH}/register", json={"org_name": "Acme", "email": "a@acme.io", "password": PASSWORD})
    assert (resp.status_code, resp.json()["detail"]["code"]) == (403, "signup_closed")
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP", True)
    assert client.get(f"{AUTH}/options").json() == {"public_signup": True}


def test_members_no_longer_create_orgs(client, acme):
    _, ann = acme
    assert client.post("/api/v1/orgs", json={"name": "Side project"}, headers=ann).status_code == 405


# --- Organizations ---------------------------------------------------------------


def test_creating_an_org_with_its_first_admin(client, db_session, root):
    resp = client.post(
        f"{P}/orgs",
        json={"name": "Globex", "industry": "Energy", "admin_email": "Zed@Globex.io", "admin_name": "Zed"},
        headers=root,
    )
    assert resp.status_code == 201, resp.text
    assert resp.headers["cache-control"] == "no-store"
    org = resp.json()
    assert (org["name"], org["status"], org["members"], org["admins"]) == ("Globex", "active", 1, ["zed@globex.io"])
    zed = first_sign_in(client, "zed@globex.io", org["temporary_password"])
    assert [(o["name"], o["role"]) for o in client.get("/api/v1/orgs", headers=zed).json()] == [("Globex", "admin")]
    # In the org's Activity and in Platform activity.
    assert {e.org_id is None for e in events(db_session, "org_created")} == {True, False}

    # An existing account keeps its password.
    again = client.post(f"{P}/orgs", json={"name": "Initech", "admin_email": "zed@globex.io"}, headers=root).json()
    assert again["temporary_password"] is None


def test_archiving_makes_an_org_read_only_until_restored(client, db_session, root, acme):
    org_id, ann = acme
    resp = client.post(f"{P}/orgs/{org_id}/archive", headers=root)
    assert (resp.status_code, resp.json()["status"]) == (200, "archived")
    [org] = client.get("/api/v1/orgs", headers=ann).json()
    assert org["archived"] is True
    assert client.get(f"/api/v1/orgs/{org_id}/findings", headers=ann).status_code == 200
    refused = client.post(f"/api/v1/orgs/{org_id}/findings", json={"domain": "network_config", "severity": "low"}, headers=ann)
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "org_archived")
    assert client.patch(f"/api/v1/orgs/{org_id}/security", json={"idle_minutes": 30}, headers=ann).status_code == 409

    assert client.post(f"{P}/orgs/{org_id}/restore", headers=root).json()["status"] == "active"
    created = client.post(f"/api/v1/orgs/{org_id}/findings", json={"domain": "network_config", "severity": "low"}, headers=ann)
    assert created.status_code == 201
    assert [e.type for e in events(db_session, "org_archived", org_id)] == ["org_archived"]


def test_archiving_waits_for_running_jobs(client, db_session, root, acme):
    org_id, _ = acme
    db_session.add(Scan(org_id=org_id, scan_type="asset_import", status=ScanStatus.pending, source="upload"))
    db_session.commit()
    resp = client.post(f"{P}/orgs/{org_id}/archive", headers=root)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "jobs_running")


def test_evidence_job_blocks_archive_until_cancelled_and_is_purged(client, db_session, root, acme):
    from app.models.evidence_evaluation import EvidenceEvaluation
    org_id, ann = acme
    path = f"/api/v1/orgs/{org_id}/scoring/evaluations"
    job = client.post(path, headers=ann)
    assert job.status_code == 202
    refused = client.post(f"{P}/orgs/{org_id}/archive", headers=root)
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "jobs_running")
    assert client.post(path + f"/{job.json()['id']}/cancel", headers=ann).status_code == 200
    assert client.post(f"{P}/orgs/{org_id}/archive", headers=root).status_code == 200
    assert client.post(path, headers=ann).status_code == 409
    assert client.post(path, headers=root).status_code == 409
    assert client.post(f"{P}/orgs/{org_id}/purge", json={"name": "Acme"}, headers=root).status_code == 202
    assert drain(db_session) == 1
    db_session.expire_all()
    assert db_session.scalar(select(EvidenceEvaluation.id)) is None


def test_purging_an_org(client, db_session, root, acme):
    org_id, ann = acme
    db_session.add(Asset(org_id=org_id, hostname="web-1", type="server"))
    db_session.commit()
    url = f"{P}/orgs/{org_id}/purge"
    assert client.post(url, json={"name": "Acme"}, headers=root).json()["detail"]["code"] == "not_archived"
    client.post(f"{P}/orgs/{org_id}/archive", headers=root)
    assert client.post(url, json={"name": "acme"}, headers=root).json()["detail"]["code"] == "name_mismatch"
    resp = client.post(url, json={"name": "Acme"}, headers=root)
    assert (resp.status_code, resp.json()["status"]) == (202, "purging")
    # Gone at once for everyone.
    assert client.get("/api/v1/orgs", headers=ann).json() == []
    assert client.get(f"/api/v1/orgs/{org_id}/assets", headers=ann).status_code == 403

    assert drain(db_session) == 1
    db_session.expire_all()
    assert db_session.get(Organization, org_id) is None
    assert db_session.scalar(select(User).where(User.email == "ann@acme.io")) is not None  # accounts stay
    [purged] = events(db_session, "org_purged", None)
    assert (purged.item, purged.actor_label, purged.counts["assets"]) == ("Acme", "Root", 1)


def test_platform_events_stay_out_of_orgs_activity(client, db_session, root, acme):
    org_id, ann = acme
    client.post(f"{P}/orgs", json={"name": "Globex", "admin_email": "zed@globex.io"}, headers=root)
    acme_types = {e["type"] for e in client.get(f"/api/v1/orgs/{org_id}/events", headers=ann).json()["items"]}
    assert "org_created" not in acme_types and "sysadmin_created" not in acme_types
    platform_types = {e["type"] for e in client.get(f"{P}/events", headers=root).json()["items"]}
    assert {"org_created", "sysadmin_created"} <= platform_types


def test_the_org_list(client, root, acme):
    client.post(f"{P}/orgs", json={"name": "Globex", "admin_email": "zed@globex.io"}, headers=root)
    org_id, _ = acme
    client.post(f"{P}/orgs/{org_id}/archive", headers=root)

    def names(**params):
        return [o["name"] for o in client.get(f"{P}/orgs", params=params, headers=root).json()["items"]]

    assert names() == ["Acme", "Globex"]
    assert names(status="archived") == ["Acme"]
    assert names(q="glob") == ["Globex"]
    assert names(sort="name", order="desc") == ["Globex", "Acme"]
    assert client.get(f"{P}/orgs/facets", headers=root).json() == {"status": ["active", "archived"]}


# --- Accounts ---------------------------------------------------------------------


def account_id(client, headers) -> str:
    return client.get(f"{AUTH}/me", headers=headers).json()["id"]


def test_the_sysadmin_resets_and_renames_anyone(client, db_session, root, acme):
    org_id, ann = acme
    ann_id = account_id(client, ann)
    resp = client.patch(f"{P}/users/{ann_id}", json={"name": "Ann Lee", "email": "Ann.Lee@acme.io"}, headers=root)
    assert (resp.status_code, resp.json()["name"], resp.json()["email"]) == (200, "Ann Lee", "ann.lee@acme.io")
    assert resp.json()["orgs"] == [{"org_id": org_id, "name": "Acme", "role": "admin"}]
    [changed_here] = events(db_session, "email_changed", org_id)
    assert changed_here.details == {"from": "ann@acme.io", "to": "ann.lee@acme.io"}
    assert len(events(db_session, "name_changed")) == 2  # Acme and Platform

    reset = client.post(f"{P}/users/{ann_id}/reset-password", headers=root)
    assert reset.status_code == 200 and reset.headers["cache-control"] == "no-store"
    assert login(client, "ann.lee@acme.io", reset.json()["temporary_password"]).json()["must_change_password"] is True

    register(client, "bob@globex.io", "Globex")
    taken = client.patch(f"{P}/users/{ann_id}", json={"email": "bob@globex.io"}, headers=root)
    assert (taken.status_code, taken.json()["detail"]["code"]) == (409, "email_taken")


def test_deactivating_signs_out_and_keeps_an_admin(client, db_session, root, acme):
    org_id, ann = acme
    ann_id = account_id(client, ann)
    refused = client.patch(f"{P}/users/{ann_id}", json={"active": False}, headers=root)
    assert (refused.status_code, refused.json()["detail"]["code"]) == (409, "last_admin")
    assert "only admin of Acme" in refused.json()["detail"]["message"]

    bob = client.post(f"/api/v1/orgs/{org_id}/members", json={"email": "bob@acme.io", "role": "admin"}, headers=ann).json()
    resp = client.patch(f"{P}/users/{ann_id}", json={"active": False}, headers=root)
    assert (resp.status_code, resp.json()["status"]) == (200, "deactivated")
    assert client.get("/api/v1/orgs", headers=ann).status_code == 401
    assert login(client, "ann@acme.io").json()["detail"]["code"] == "account_deactivated"
    # Bob is the only admin who can sign in now: he can't be demoted.
    demote = client.patch(f"{P}/users/{bob['id']}/orgs/{org_id}", json={"role": "viewer"}, headers=root)
    assert demote.json()["detail"]["code"] == "last_admin"

    assert client.patch(f"{P}/users/{ann_id}", json={"active": True}, headers=root).json()["status"] == "active"
    assert login(client, "ann@acme.io").status_code == 200
    assert client.patch(f"{P}/users/{account_id(client, root)}", json={"active": False}, headers=root).status_code == 400


def test_the_sysadmin_changes_a_role_in_an_emergency(client, db_session, root, acme):
    org_id, ann = acme
    bob = client.post(f"/api/v1/orgs/{org_id}/members", json={"email": "bob@acme.io"}, headers=ann).json()
    resp = client.patch(f"{P}/users/{bob['id']}/orgs/{org_id}", json={"role": "admin"}, headers=root)
    assert resp.status_code == 200
    assert resp.json()["orgs"][0]["role"] == "admin"
    # In Acme's Activity and in Platform activity.
    assert sorted(str(e.org_id) for e in events(db_session, "role_changed")) == sorted([org_id, "None"])


def test_the_user_list(client, root, acme):
    _, ann = acme
    register(client, "bob@globex.io", "Globex")

    def emails(**params):
        return [u["email"] for u in client.get(f"{P}/users", params=params, headers=root).json()["items"]]

    assert emails() == ["ann@acme.io", "bob@globex.io", "root@platform.io"]
    assert emails(q="acme") == ["ann@acme.io"]  # by org
    assert emails(q="globex") == ["bob@globex.io"]
    assert emails(status="active") == ["ann@acme.io", "bob@globex.io", "root@platform.io"]


# --- Security settings ------------------------------------------------------------


def test_platform_defaults_and_an_orgs_changes(client, db_session, root, acme):
    org_id, ann = acme
    resp = client.patch(f"{P}/security", json={"idle_minutes": 60, "password_rule": "complex"}, headers=root)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["values"]["idle_minutes"], body["changed"], body["below"]["idle_minutes"]) == (
        60,
        ["idle_minutes", "password_rule"],
        480,
    )
    [platform_change] = events(db_session, "settings_changed", None)
    assert platform_change.details["idle_minutes"] == {"from": 480, "to": 60}

    org = client.get(f"/api/v1/orgs/{org_id}/security", headers=ann).json()
    assert (org["values"]["idle_minutes"], org["changed"], org["below"]["password_rule"]) == (60, [], "complex")

    changed = client.patch(f"/api/v1/orgs/{org_id}/security", json={"idle_minutes": 30, "min_length": 20}, headers=ann)
    assert changed.json()["changed"] == ["idle_minutes", "min_length"]
    # Back to the platform default.
    back = client.patch(f"/api/v1/orgs/{org_id}/security", json={"idle_minutes": None}, headers=ann).json()
    assert (back["values"]["idle_minutes"], back["changed"]) == (60, ["min_length"])
    rules = client.get(f"{AUTH}/password-rules", headers=ann).json()
    assert (rules["rule"], rules["min_length"]) == ("complex", 20)


@pytest.mark.parametrize(
    "changes",
    [{"idle_minutes": 5}, {"lockout_threshold": 2}, {"min_length": 8}, {"no_such_setting": 1}, {"password_rule": "x"}],
)
def test_settings_stay_within_their_ranges(client, root, acme, changes):
    org_id, ann = acme
    for url, headers in ((f"{P}/security", root), (f"/api/v1/orgs/{org_id}/security", ann)):
        resp = client.patch(url, json=changes, headers=headers)
        assert (resp.status_code, resp.json()["detail"]["code"]) == (422, "invalid_settings"), changes


def test_only_admins_change_an_orgs_security(client, acme):
    org_id, ann = acme
    bob = client.post(f"/api/v1/orgs/{org_id}/members", json={"email": "bob@acme.io"}, headers=ann).json()
    bob_headers = first_sign_in(client, "bob@acme.io", bob["temporary_password"])
    assert client.get(f"/api/v1/orgs/{org_id}/security", headers=bob_headers).status_code == 200
    assert client.patch(f"/api/v1/orgs/{org_id}/security", json={"idle_minutes": 30}, headers=bob_headers).status_code == 403


def test_refresh_renews_the_cookies_expiry(client, db_session, acme):
    login(client, "ann@acme.io")
    resp = client.post(f"{AUTH}/refresh", headers={"X-Requested-With": "AuditMind"})
    assert resp.status_code == 200
    assert "auditmind_session=" in resp.headers["set-cookie"] and "Max-Age" in resp.headers["set-cookie"]


def test_an_orgs_activity_shows_the_workers_events_only_since_the_org_was_created(client, db_session, acme):
    from datetime import timedelta

    from app.services.events import record_event

    org_id, ann = acme
    org = db_session.get(Organization, org_id)
    before = record_event(db_session, "worker_started", org_id=None)
    before.started_at = org.created_at - timedelta(days=1)
    record_event(db_session, "worker_stopped", org_id=None)
    db_session.commit()
    types = [e["type"] for e in client.get(f"/api/v1/orgs/{org_id}/events", headers=ann).json()["items"]]
    assert "worker_stopped" in types and "worker_started" not in types
    facets = client.get(f"/api/v1/orgs/{org_id}/events/facets", headers=ann).json()
    assert "worker_started" not in facets["type"]
