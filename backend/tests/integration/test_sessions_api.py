"""Sign-in sessions, lockout and passwords (Phase 2e part 1)."""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.event import Event
from app.models.enums import UserRole
from app.models.membership import OrgMembership
from app.models.organization import Organization
from app.models.session import UserSession
from app.models.user import User
from app.services import accounts
from tests.conftest import requires_db
from tests.helpers import PASSWORD, first_org_id, register

pytestmark = requires_db

AUTH = "/api/v1/auth"
EMAIL = "ann@acme.io"
APP = {"X-Requested-With": "AuditMind"}
NEW_PASSWORD = "A-much-longer-passphrase-2026"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client, email=EMAIL, password=PASSWORD):
    return client.post(f"{AUTH}/login", json={"email": email, "password": password})


def user(db, email=EMAIL) -> User:
    db.expire_all()
    return db.scalar(select(User).where(User.email == email))


def sessions_of(db, email=EMAIL) -> list[UserSession]:
    db.expire_all()
    return db.scalars(select(UserSession).join(User).where(User.email == email).order_by(UserSession.created_at)).all()


def ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


@pytest.fixture
def ann(client):
    """Ann, admin of Acme; returns her auth headers."""
    return register(client, EMAIL)


def set_org_security(db, **changes):
    for org in db.scalars(select(Organization)).all():
        org.security_settings = changes
    db.commit()


# --- Sessions -----------------------------------------------------------------


def test_login_sets_an_httponly_strict_cookie_for_auth_only(client, ann):
    resp = login(client)
    assert resp.status_code == 200
    body = resp.json()
    assert (body["token_type"], body["expires_in"], body["must_change_password"]) == ("bearer", 900, False)
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith("auditmind_session=")
    for part in ("HttpOnly", "Path=/api/v1/auth", "SameSite=strict"):
        assert part in cookie
    assert "Secure" not in cookie  # tests run over http (COOKIE_SECURE off)


def test_the_cookie_renews_the_access_token(client, ann):
    login(client)
    resp = client.post(f"{AUTH}/refresh", headers=APP)
    assert resp.status_code == 200, resp.text
    assert client.get("/api/v1/orgs", headers=bearer(resp.json()["access_token"])).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Requested-With": "Other"}, {**APP, "Origin": "https://evil.example"}, {**APP, "Sec-Fetch-Site": "cross-site"}],
)
def test_refresh_refuses_requests_another_site_could_make(client, ann, headers):
    login(client)
    assert client.post(f"{AUTH}/refresh", headers=headers).status_code == 403


def test_refresh_from_our_own_frontend_is_allowed(client, ann):
    login(client)
    resp = client.post(f"{AUTH}/refresh", headers={**APP, "Origin": "http://localhost:3000"})
    assert resp.status_code == 200


def test_refresh_without_a_session_is_refused_and_clears_the_cookie(client):
    resp = client.post(f"{AUTH}/refresh", headers=APP)
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "session_ended"
    assert 'auditmind_session=""' in resp.headers["set-cookie"] or "Max-Age=0" in resp.headers["set-cookie"]


def test_signing_out_ends_the_session_at_once(client, ann):
    token = login(client).json()["access_token"]
    assert client.post(f"{AUTH}/logout", headers=bearer(token)).status_code == 204
    resp = client.get("/api/v1/orgs", headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "session_ended"
    # And the cookie can't renew it.
    assert client.post(f"{AUTH}/refresh", headers=APP).status_code == 401
    # Signing out again is fine.
    assert client.post(f"{AUTH}/logout", headers=bearer(token)).status_code == 204


def test_signing_out_with_only_the_cookie(client, ann):
    token = login(client).json()["access_token"]
    assert client.post(f"{AUTH}/logout", headers=APP).status_code == 204
    assert client.get("/api/v1/orgs", headers=bearer(token)).status_code == 401


def test_idle_too_long_ends_the_session(client, db_session, ann):
    token = login(client).json()["access_token"]
    session = sessions_of(db_session)[-1]
    session.last_seen_at = ago(minutes=481)
    db_session.commit()
    resp = client.get("/api/v1/orgs", headers=bearer(token))
    assert resp.status_code == 401
    assert "inactivity" in resp.json()["detail"]["message"]
    assert sessions_of(db_session)[-1].revoked_reason == "idle"


def test_the_longest_sign_in_ends_the_session(client, db_session, ann):
    token = login(client).json()["access_token"]
    session = sessions_of(db_session)[-1]
    session.expires_at = ago(seconds=1)
    db_session.commit()
    assert client.get("/api/v1/orgs", headers=bearer(token)).status_code == 401
    assert client.post(f"{AUTH}/refresh", headers=APP).status_code == 401


def test_the_apps_own_polling_doesnt_count_as_activity(client, db_session, ann):
    token = login(client).json()["access_token"]
    session = sessions_of(db_session)[-1]
    before = session.last_seen_at = ago(minutes=5)
    db_session.commit()
    client.get("/api/v1/orgs", headers={**bearer(token), "X-Activity": "background"})
    assert sessions_of(db_session)[-1].last_seen_at == before
    client.get("/api/v1/orgs", headers=bearer(token))
    assert sessions_of(db_session)[-1].last_seen_at > before


def test_the_org_settings_set_the_session_limits(client, db_session, ann):
    set_org_security(db_session, idle_minutes=10, max_session_days=2)
    login(client)
    session = sessions_of(db_session)[-1]
    assert session.idle_minutes == 10
    assert session.expires_at - session.created_at == timedelta(days=2)
    # A change applies from the next renewal.
    set_org_security(db_session, idle_minutes=60, max_session_days=2)
    client.post(f"{AUTH}/refresh", headers=APP)
    assert sessions_of(db_session)[-1].idle_minutes == 60


def test_a_token_without_a_session_is_refused(client, db_session, ann):
    old_style = create_access_token(subject=str(user(db_session).id))
    resp = client.get("/api/v1/orgs", headers=bearer(old_style))
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "token_invalid"


def test_a_deactivated_account_is_signed_out_and_told_only_with_its_password(client, db_session, ann):
    user(db_session).is_active = False
    db_session.commit()
    assert client.get("/api/v1/orgs", headers=ann).status_code == 401
    wrong = login(client, password="not-the-password")
    assert (wrong.status_code, wrong.json()["detail"]["code"]) == (401, "invalid")
    right = login(client)
    assert (right.status_code, right.json()["detail"]["code"]) == (403, "account_deactivated")


# --- Lockout ------------------------------------------------------------------


def test_five_failures_lock_the_account_and_only_the_password_reveals_it(client, db_session, ann):
    for _ in range(5):
        assert login(client, password="wrong-password").status_code == 401
    assert user(db_session).is_locked(datetime.now(timezone.utc))
    # A wrong password still just says invalid (and isn't counted again).
    wrong = login(client, password="wrong-password")
    assert (wrong.status_code, wrong.json()["detail"]["code"]) == (401, "invalid")
    right = login(client)
    assert right.status_code == 423
    assert "Try again in 15 minutes" in right.json()["detail"]["message"]

    [event] = db_session.scalars(select(Event).where(Event.type == "account_locked")).all()
    assert (event.item, event.criticality.value) == (EMAIL, "warning")


def test_a_timed_lock_runs_out(client, db_session, ann):
    for _ in range(5):
        login(client, password="wrong-password")
    account = user(db_session)
    account.locked_until = ago(seconds=1)
    db_session.commit()
    assert login(client).status_code == 200
    assert user(db_session).locked_at is None


def test_until_an_admin_unlocks(client, db_session, ann):
    set_org_security(db_session, lock_minutes=0)
    for _ in range(5):
        login(client, password="wrong-password")
    account = user(db_session)
    assert account.locked_until is None
    resp = login(client)
    assert (resp.status_code, resp.json()["detail"]["message"]) == (
        423,
        "Your account is locked. Ask your administrator to unlock it.",
    )
    accounts.unlock(account)
    db_session.commit()
    assert login(client).status_code == 200


def test_threshold_zero_never_locks(client, db_session, ann):
    set_org_security(db_session, lockout_threshold=0)
    for _ in range(8):
        login(client, password="wrong-password")
    assert login(client).status_code == 200


def test_failures_outside_the_window_start_a_new_count(client, db_session, ann):
    for _ in range(4):
        login(client, password="wrong-password")
    account = user(db_session)
    account.failed_window_started_at = ago(minutes=16)
    db_session.commit()
    login(client, password="wrong-password")
    assert (user(db_session).failed_login_count, user(db_session).locked_at) == (1, None)


def test_a_correct_password_clears_the_count(client, db_session, ann):
    for _ in range(4):
        login(client, password="wrong-password")
    assert login(client).status_code == 200
    assert user(db_session).failed_login_count == 0


def test_too_many_attempts_from_one_address(client, ann):
    for _ in range(20):
        login(client, email="nobody@nowhere.io", password="whatever")
    resp = login(client)
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1


# --- Passwords ----------------------------------------------------------------


def change(client, headers, current=PASSWORD, new=NEW_PASSWORD):
    return client.post(
        f"{AUTH}/change-password", json={"current_password": current, "new_password": new}, headers=headers
    )


def test_changing_the_password_ends_the_other_sessions_only(client, db_session, ann):
    other = bearer(login(client).json()["access_token"])
    assert change(client, ann).status_code == 204
    assert client.get("/api/v1/orgs", headers=ann).status_code == 200
    assert client.get("/api/v1/orgs", headers=other).status_code == 401
    assert login(client).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200
    assert db_session.scalars(select(Event.type).where(Event.type == "password_changed")).all() == ["password_changed"]


def test_a_new_password_must_meet_the_rule(client, ann):
    resp = change(client, ann, new="short")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "password_policy"
    assert [p["code"] for p in detail["problems"]] == ["too_short"]
    assert [p["code"] for p in change(client, ann, new=PASSWORD).json()["detail"]["problems"]] == ["is_current"]


def test_a_wrong_current_password_counts_towards_lockout(client, db_session, ann):
    for _ in range(4):
        resp = change(client, ann, current="wrong-password")
        assert (resp.status_code, resp.json()["detail"]["code"]) == (400, "wrong_current")
    change(client, ann, current="wrong-password")  # the fifth: locked, signed out
    assert user(db_session).locked_at is not None
    assert client.get("/api/v1/orgs", headers=ann).status_code == 401


def test_the_complex_rule_and_its_history(client, db_session, ann):
    set_org_security(db_session, password_rule="complex", min_length=16, history_count=2)
    rules = client.get(f"{AUTH}/password-rules", headers=ann).json()
    assert (rules["rule"], rules["min_length"], rules["require_symbol"]) == ("complex", 16, True)
    first, second = "First-password-2026!", "Second-password-2026!"
    assert change(client, ann, new=first).status_code == 204
    assert change(client, ann, current=first, new=second).status_code == 204
    resp = change(client, ann, current=second, new=first)
    assert [p["code"] for p in resp.json()["detail"]["problems"]] == ["reused"]


def test_rules_say_which_org_asks_for_them(client, db_session, ann):
    org_id = first_org_id(client, ann)
    # Ann is in a second org, with the default rule.
    zeta = Organization(name="Zeta")
    db_session.add(zeta)
    db_session.flush()
    db_session.add(OrgMembership(user_id=user(db_session).id, org_id=zeta.id, role=UserRole.admin))
    acme = db_session.get(Organization, uuid.UUID(org_id))
    acme.security_settings = {"password_rule": "complex", "min_length": 20}
    db_session.commit()
    rules = client.get(f"{AUTH}/password-rules", headers=ann).json()
    assert rules["min_length"] == 20
    assert rules["required_by"]["min_length"] == "Acme Corp"
    resp = change(client, ann, new="Short-but-Valid-1!")
    assert resp.json()["detail"]["problems"][0]["message"] == "Use at least 20 characters (required by Acme Corp)"


def test_a_password_change_is_required_before_anything_else(client, db_session, ann):
    user(db_session).must_change_password = True
    db_session.commit()
    resp = client.get("/api/v1/orgs", headers=ann)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (403, "password_change_required")
    me = client.get(f"{AUTH}/me", headers=ann).json()
    assert (me["email"], me["must_change_password"]) == (EMAIL, True)
    assert change(client, ann).status_code == 204
    assert client.get("/api/v1/orgs", headers=ann).status_code == 200


def test_a_temporary_password(client, db_session, ann):
    temporary = accounts.set_temporary_password(db_session, user(db_session))
    db_session.commit()
    assert len(temporary) >= 16
    assert client.get("/api/v1/orgs", headers=ann).status_code == 401  # sessions ended
    resp = login(client, password=temporary)
    assert (resp.status_code, resp.json()["must_change_password"]) == (200, True)
    headers = bearer(resp.json()["access_token"])
    assert client.get("/api/v1/orgs", headers=headers).status_code == 403
    assert change(client, headers, current=temporary).status_code == 204
    assert client.get("/api/v1/orgs", headers=headers).status_code == 200


def test_a_temporary_password_expires_after_seven_days(client, db_session, ann):
    account = user(db_session)
    temporary = accounts.set_temporary_password(db_session, account)
    account.temp_password_expires_at = ago(seconds=1)
    db_session.commit()
    resp = login(client, password=temporary)
    assert (resp.status_code, resp.json()["detail"]["code"]) == (401, "temp_password_expired")


def test_an_expired_password_must_be_changed(client, db_session, ann):
    set_org_security(db_session, password_rule="complex", expiry_days=30)
    user(db_session).password_changed_at = ago(days=31)
    db_session.commit()
    resp = login(client)
    assert resp.json()["must_change_password"] is True
    me = client.get(f"{AUTH}/me", headers=bearer(resp.json()["access_token"])).json()
    assert me["password_expires_at"] is not None


# --- Emails -------------------------------------------------------------------


def test_emails_are_one_account_whatever_their_case(client, db_session):
    register(client, "Ann.Lee@Acme.IO")
    assert user(db_session, "ann.lee@acme.io") is not None
    assert login(client, email="ANN.LEE@acme.io").status_code == 200
    dup = client.post(
        f"{AUTH}/register", json={"org_name": "Other", "email": "ann.lee@ACME.io", "password": PASSWORD}
    )
    assert dup.status_code == 400


def test_adding_a_member_finds_them_whatever_the_case(client):
    admin = register(client, "owner@acme.io")
    register(client, "bob@acme.io", org_name="Bob's")
    resp = client.post(
        f"/api/v1/orgs/{first_org_id(client, admin)}/members", json={"email": "BOB@Acme.io", "role": "viewer"}, headers=admin
    )
    assert resp.status_code == 201, resp.text


def test_the_upgrade_stops_on_emails_differing_only_in_case():
    path = Path(__file__).parents[2] / "alembic" / "versions" / "0015_sessions_and_accounts.py"
    spec = importlib.util.spec_from_file_location("migration_0015", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.email_clash_message([]) is None
    row = type("Row", (), {"email": "ann@acme.io", "accounts": "Ann@acme.io, ann@acme.io"})
    message = migration.email_clash_message([row])
    assert "ann@acme.io: Ann@acme.io, ann@acme.io" in message


# --- Headers ------------------------------------------------------------------


def test_security_headers(client, ann):
    resp = client.get("/api/v1/orgs", headers=ann)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "strict-transport-security" not in resp.headers  # COOKIE_SECURE off
    assert login(client).headers["cache-control"] == "no-store"
    docs = client.get("/docs")
    assert docs.status_code == 200 and "content-security-policy" not in docs.headers
