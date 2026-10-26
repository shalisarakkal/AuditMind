"""People: adding, changing and removing an org's members (Phase 2e part 2)."""

import pytest
from sqlalchemy import select

from app.models.event import Event
from app.models.organization import Organization
from app.models.user import User
from tests.conftest import requires_db
from tests.helpers import PASSWORD, first_org_id, register

pytestmark = requires_db

AUTH = "/api/v1/auth"
NEW_PASSWORD = "A-much-longer-passphrase-2026"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password=PASSWORD):
    return client.post(f"{AUTH}/login", json={"email": email, "password": password})


def account(db, email) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == email))


def events(db, type) -> list[Event]:
    db.expire_all()
    return db.scalars(select(Event).where(Event.type == type).order_by(Event.started_at)).all()


@pytest.fixture
def acme(client):
    """Ann, admin of Acme: (org id, her headers, the members URL)."""
    ann = register(client, "ann@acme.io", "Acme")
    org_id = first_org_id(client, ann)
    return org_id, ann, f"/api/v1/orgs/{org_id}/members"


def add(client, acme, email, role="viewer", name=None):
    _, ann, url = acme
    resp = client.post(url, json={"email": email, "role": role, **({"name": name} if name else {})}, headers=ann)
    assert resp.status_code == 201, resp.text
    return resp.json()


def signed_in(client, email, temporary):
    """Sign in with a temporary password and change it; returns headers."""
    token = login(client, email, temporary).json()["access_token"]
    resp = client.post(
        f"{AUTH}/change-password",
        json={"current_password": temporary, "new_password": NEW_PASSWORD},
        headers=bearer(token),
    )
    assert resp.status_code == 204, resp.text
    return bearer(token)


# --- Adding -------------------------------------------------------------------


def test_adding_a_new_person_gives_a_temporary_password_shown_once(client, db_session, acme):
    org_id, ann, url = acme
    resp = client.post(url, json={"email": "Bob@Acme.io", "name": " Bob ", "role": "auditor"}, headers=ann)
    assert resp.status_code == 201, resp.text
    assert resp.headers["cache-control"] == "no-store"
    bob = resp.json()
    assert (bob["email"], bob["name"], bob["role"], bob["status"]) == (
        "bob@acme.io",
        "Bob",
        "auditor",
        "must_change_password",
    )
    assert bob["temp_password_expires_at"] and bob["in_other_orgs"] is False
    temporary = bob["temporary_password"]
    assert len(temporary) >= 16

    resp = login(client, "bob@acme.io", temporary)
    assert (resp.status_code, resp.json()["must_change_password"]) == (200, True)
    headers = signed_in(client, "bob@acme.io", temporary)
    orgs = client.get("/api/v1/orgs", headers=headers).json()
    assert [(o["id"], o["role"]) for o in orgs] == [(org_id, "auditor")]

    [event] = events(db_session, "member_added")
    assert (event.item, event.actor_label, event.details) == (
        "bob@acme.io",
        "ann@acme.io",
        {"role": "auditor", "new_account": True},
    )


def test_adding_someone_with_an_account_keeps_their_password_and_name(client, db_session, acme):
    cara = register(client, "cara@globex.io", "Globex")
    client.patch(f"{AUTH}/me", json={"name": "Cara"}, headers=cara)
    resp = add(client, acme, "CARA@globex.io", "auditor", name="Someone else")
    assert (resp["name"], resp["temporary_password"], resp["status"], resp["in_other_orgs"]) == (
        "Cara",
        None,
        "active",
        True,
    )
    assert login(client, "cara@globex.io").status_code == 200
    assert events(db_session, "member_added")[-1].details == {"role": "auditor"}


def test_adding_is_refused_for_a_member_or_the_sysadmin(client, db_session, acme):
    _, ann, url = acme
    assert client.post(url, json={"email": "ann@acme.io"}, headers=ann).json()["detail"]["code"] == "already_member"
    db_session.add(User(email="root@platform.io", is_sysadmin=True))
    db_session.commit()
    resp = client.post(url, json={"email": "root@platform.io"}, headers=ann)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "sysadmin")


def test_a_new_persons_temporary_password_meets_the_orgs_rule(client, db_session, acme):
    org = db_session.scalar(select(Organization))
    org.security_settings = {"password_rule": "complex", "min_length": 30}
    db_session.commit()
    assert len(add(client, acme, "bob@acme.io")["temporary_password"]) == 30


def test_only_admins_manage_people_but_everyone_sees_them(client, acme):
    org_id, ann, url = acme
    viewer = signed_in(client, "vic@acme.io", add(client, acme, "vic@acme.io")["temporary_password"])
    bob_id = add(client, acme, "bob@acme.io", "auditor")["id"]

    listed = client.get(url, headers=viewer)
    assert listed.status_code == 200
    assert [m["email"] for m in listed.json()["items"]] == ["ann@acme.io", "bob@acme.io", "vic@acme.io"]
    for method, path, body in (
        ("post", "", {"email": "x@acme.io"}),
        ("patch", f"/{bob_id}", {"role": "admin"}),
        ("delete", f"/{bob_id}", None),
        ("post", f"/{bob_id}/reset-password", None),
        ("post", f"/{bob_id}/unlock", None),
    ):
        resp = client.request(method, url + path, json=body, headers=viewer)
        assert resp.status_code == 403, (method, path)


def test_admins_act_only_inside_their_own_org(client, acme):
    _, _, url = acme
    bob_id = add(client, acme, "bob@acme.io")["id"]
    zed = register(client, "zed@globex.io", "Globex")
    globex_url = f"/api/v1/orgs/{first_org_id(client, zed)}/members"
    # Zed is admin of Globex, but Bob isn't there: nothing to act on.
    for method, path, body in (
        ("patch", f"/{bob_id}", {"role": "admin"}),
        ("delete", f"/{bob_id}", None),
        ("post", f"/{bob_id}/reset-password", None),
        ("post", f"/{bob_id}/unlock", None),
    ):
        assert client.request(method, globex_url + path, json=body, headers=zed).status_code == 404
    # Nor through Acme's address, where Zed isn't a member.
    assert client.get(url, headers=zed).status_code == 403
    assert client.patch(f"{url}/{bob_id}", json={"role": "admin"}, headers=zed).status_code == 403


# --- Roles and removal --------------------------------------------------------


def test_changing_a_role_ends_their_sessions(client, db_session, acme):
    _, ann, url = acme
    bob = add(client, acme, "bob@acme.io", "viewer")
    headers = signed_in(client, "bob@acme.io", bob["temporary_password"])
    resp = client.patch(f"{url}/{bob['id']}", json={"role": "auditor"}, headers=ann)
    assert (resp.status_code, resp.json()["role"]) == (200, "auditor")
    ended = client.get("/api/v1/orgs", headers=headers)
    assert ended.status_code == 401
    assert ended.json()["detail"]["message"] == "An administrator changed your role. Please sign in again."
    assert events(db_session, "role_changed")[0].details == {"from": "viewer", "to": "auditor"}


def test_an_org_keeps_an_admin_and_admins_dont_change_themselves(client, acme):
    org_id, ann, url = acme
    ann_id = client.get(f"{AUTH}/me", headers=ann).json()["id"]
    for method, body in (("patch", {"role": "viewer"}), ("delete", None)):
        resp = client.request(method, f"{url}/{ann_id}", json=body, headers=ann)
        assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "yourself")

    bob = add(client, acme, "bob@acme.io", "admin")
    bob_headers = signed_in(client, "bob@acme.io", bob["temporary_password"])
    # Two admins: one may demote the other, but not the last one.
    assert client.patch(f"{url}/{ann_id}", json={"role": "viewer"}, headers=bob_headers).status_code == 200
    # Demoting Ann ended her sessions.
    assert client.patch(f"{url}/{bob['id']}", json={"role": "viewer"}, headers=ann).status_code == 401


def test_the_last_admin_cant_be_removed_or_demoted(client, db_session, acme):
    from app.models.enums import UserRole
    from app.models.membership import OrgMembership
    from app.services import people
    from app.services.people import PeopleError

    org_id, _, _ = acme
    ann = account(db_session, "ann@acme.io")
    someone = User(email="ops@acme.io")
    db_session.add(someone)
    db_session.flush()
    membership = db_session.get(OrgMembership, (ann.id, org_id))
    # An actor other than Ann (as the Sysadmin will be, in Part 3).
    for change in (lambda: people.change_role(db_session, membership, someone, UserRole.viewer),
                   lambda: people.remove_member(db_session, membership, someone)):
        with pytest.raises(PeopleError) as refused:
            change()
        assert refused.value.code == "last_admin"
    db_session.rollback()


def test_removing_someone_keeps_their_account(client, db_session, acme):
    _, ann, url = acme
    bob = add(client, acme, "bob@acme.io", "auditor")
    headers = signed_in(client, "bob@acme.io", bob["temporary_password"])
    assert client.delete(f"{url}/{bob['id']}", headers=ann).status_code == 204
    assert client.get("/api/v1/orgs", headers=headers).status_code == 401
    assert account(db_session, "bob@acme.io") is not None
    token = login(client, "bob@acme.io", NEW_PASSWORD).json()["access_token"]
    assert client.get("/api/v1/orgs", headers=bearer(token)).json() == []
    assert events(db_session, "member_removed")[0].details == {"role": "auditor"}
    # Added again: no temporary password, their own still works.
    assert add(client, acme, "bob@acme.io")["temporary_password"] is None


# --- Names and passwords ------------------------------------------------------


def test_everyone_renames_themselves(client, db_session, acme):
    _, ann, _ = acme
    zed = register(client, "zed@globex.io", "Globex")
    add(client, acme, "zed@globex.io")
    resp = client.patch(f"{AUTH}/me", json={"name": "  Zed Z.  "}, headers=zed)
    assert (resp.status_code, resp.json()["name"]) == (200, "Zed Z.")
    # Recorded in each of Zed's orgs.
    renamed = events(db_session, "name_changed")
    assert len(renamed) == 2 and renamed[0].details == {"from": None, "to": "Zed Z."}
    assert client.patch(f"{AUTH}/me", json={"name": "   "}, headers=zed).status_code == 422
    assert client.patch(f"{AUTH}/me", json={"name": "x" * 101}, headers=zed).status_code == 422


def test_an_admin_renames_and_resets_only_people_in_their_org_alone(client, db_session, acme):
    _, ann, url = acme
    bob = add(client, acme, "bob@acme.io", name="Bob")
    resp = client.patch(f"{url}/{bob['id']}", json={"name": "Robert"}, headers=ann)
    assert (resp.status_code, resp.json()["name"]) == (200, "Robert")
    assert events(db_session, "name_changed")[0].details == {"from": "Bob", "to": "Robert"}

    register(client, "zed@globex.io", "Globex")
    zed = add(client, acme, "zed@globex.io")
    for path, body in ((f"/{zed['id']}", {"name": "Zed"}), (f"/{zed['id']}/reset-password", None)):
        method = "patch" if body else "post"
        resp = client.request(method, url + path, json=body, headers=ann)
        assert (resp.status_code, resp.json()["detail"]["code"]) == (403, "other_orgs")
        assert "only the Sysadmin" in resp.json()["detail"]["message"]


def test_resetting_a_password(client, db_session, acme):
    _, ann, url = acme
    bob = add(client, acme, "bob@acme.io")
    headers = signed_in(client, "bob@acme.io", bob["temporary_password"])
    resp = client.post(f"{url}/{bob['id']}/reset-password", headers=ann)
    assert resp.status_code == 200, resp.text
    assert resp.headers["cache-control"] == "no-store"
    temporary = resp.json()["temporary_password"]
    ended = client.get("/api/v1/orgs", headers=headers)
    assert ended.json()["detail"]["message"].startswith("An administrator reset your password.")
    assert login(client, "bob@acme.io", NEW_PASSWORD).status_code == 401
    assert login(client, "bob@acme.io", temporary).json()["must_change_password"] is True
    [event] = events(db_session, "password_reset")
    assert (event.item, event.details) == ("bob@acme.io", None)  # never the password


def test_admins_dont_reset_their_own_password(client, acme):
    _, ann, url = acme
    ann_id = client.get(f"{AUTH}/me", headers=ann).json()["id"]
    assert client.post(f"{url}/{ann_id}/reset-password", headers=ann).json()["detail"]["code"] == "yourself"


def test_unlocking(client, db_session, acme):
    _, ann, url = acme
    zed = register(client, "zed@globex.io", "Globex")
    zed_id = client.get(f"{AUTH}/me", headers=zed).json()["id"]
    add(client, acme, "zed@globex.io")
    for org in db_session.scalars(select(Organization)).all():
        org.security_settings = {"lock_minutes": 0}
    db_session.commit()
    for _ in range(5):
        login(client, "zed@globex.io", "wrong-password")

    listed = client.get(url, params={"status": "locked"}, headers=ann).json()
    assert [(m["email"], m["locked_until"]) for m in listed["items"]] == [("zed@globex.io", None)]
    # An admin of any of Zed's orgs may unlock him.
    resp = client.post(f"{url}/{zed_id}/unlock", headers=ann)
    assert (resp.status_code, resp.json()["status"]) == (200, "active")
    assert login(client, "zed@globex.io").status_code == 200
    assert len(events(db_session, "account_unlocked")) == 2  # Acme and Globex
    assert client.post(f"{url}/{zed_id}/unlock", headers=ann).json()["detail"]["code"] == "not_locked"


# --- The list -----------------------------------------------------------------


def test_identity_search_matches_names_not_roles_and_remains_tenant_scoped(client, acme):
    _, ann, url = acme
    shali = add(client, acme, "shali@acme.io", "admin", name="Shali Arakkal")
    owner = add(client, acme, "owner@acme.io", "viewer", name="Active Admin")
    register(client, "admin@foreign.io", "Foreign")
    response = client.get(url, params={"q": "admin", "search_scope": "identity"}, headers=ann)
    assert response.status_code == 200
    assert [m["id"] for m in response.json()["items"]] == [owner["id"]]
    broad = client.get(url, params={"q": "admin"}, headers=ann).json()
    assert {m["id"] for m in broad["items"]} >= {shali["id"], owner["id"]}


def test_the_list_searches_filters_and_sorts(client, acme):
    _, ann, url = acme
    add(client, acme, "bob@acme.io", "auditor", name="Bob")
    add(client, acme, "cara@acme.io", "viewer", name="Cara")

    def emails(**params):
        resp = client.get(url, params=params, headers=ann)
        assert resp.status_code == 200, resp.text
        return [m["email"] for m in resp.json()["items"]]

    assert emails() == ["ann@acme.io", "bob@acme.io", "cara@acme.io"]
    assert emails(q="auditor") == ["bob@acme.io"]
    assert emails(q="must change") == ["bob@acme.io", "cara@acme.io"]
    assert emails(q="car") == ["cara@acme.io"]
    assert emails(q="auditor", search_scope="identity") == []
    assert emails(q="must change", search_scope="identity") == []
    assert emails(q="BOB", search_scope="identity") == ["bob@acme.io"]
    assert emails(q="cara@acme.io", search_scope="identity") == ["cara@acme.io"]
    assert emails(q="admin", search_scope="identity") == []
    assert emails(q="admin") == ["ann@acme.io"]
    assert client.get(url, params={"search_scope": "invalid"}, headers=ann).status_code == 422
    assert emails(role=["admin", "viewer"]) == ["ann@acme.io", "cara@acme.io"]
    assert emails(status="active") == ["ann@acme.io"]
    assert emails(name="b") == ["bob@acme.io"]
    assert emails(sort="role", order="desc") == ["cara@acme.io", "bob@acme.io", "ann@acme.io"]
    assert client.get(url, params={"limit": 1, "offset": 1}, headers=ann).json()["total"] == 3

    facets = client.get(f"{url}/facets", headers=ann).json()
    assert facets == {"role": ["admin", "auditor", "viewer"], "status": ["active", "must_change_password"]}
