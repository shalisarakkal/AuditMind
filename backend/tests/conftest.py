import os
import secrets
from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

# The app refuses to start with the built-in signing key (check_secret_key);
# tests get a random one unless one's set already.
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(48))

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ingestion_background  # noqa: E402
from app.services.rate_limit import login_limiter  # noqa: E402

# The DB fixture creates and drops every table, so tests only ever use a
# database named *_test (TEST_DATABASE_URL), never the app's own: falling back
# to DATABASE_URL once wiped the dev database when .env wasn't found.
TEST_DB_URL = settings.TEST_DATABASE_URL


def _is_test_db(url: str | URL | None) -> bool:
    if not url:
        return False
    try:
        parsed = make_url(url)
    except (ArgumentError, ValueError):
        return False
    return parsed.get_backend_name() == "postgresql" and (parsed.database or "").endswith("_test")


def _db_available(url: str) -> bool:
    engine = None
    try:
        engine = create_engine(url)
        with engine.connect():
            pass
        return True
    except Exception:
        return False
    finally:
        if engine is not None:
            engine.dispose()


DB_AVAILABLE = _is_test_db(TEST_DB_URL) and _db_available(TEST_DB_URL)

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason=(
        f"Postgres test database {make_url(TEST_DB_URL).render_as_string(hide_password=True)} is not reachable"
        if _is_test_db(TEST_DB_URL)
        else "TEST_DATABASE_URL must name a PostgreSQL database ending in _test (see backend/.env.example)"
    )
    + "; skipping DB-backed test.",
)


@pytest.fixture(autouse=True)
def _sign_in_defaults(monkeypatch):
    """The test client talks plain http, so the session cookie mustn't be
    HTTPS-only; and each test starts with no sign-in attempts counted.
    Sign-up is open: most tests make their accounts that way (helpers.register)."""
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)
    monkeypatch.setattr(settings, "PUBLIC_SIGNUP", True)
    login_limiter.reset()


@pytest.fixture
def db_session():
    assert _is_test_db(TEST_DB_URL), "refusing to create and drop tables outside a *_test database"
    engine = create_engine(TEST_DB_URL)
    # `documents` needs the pgvector extension enabled in the test DB
    # (see scripts/create_databases.sql). Dropped first too: a run that was
    # cut off, or a copy of real data loaded for measuring, leaves tables
    # behind that create_all would keep.
    _drop_test_schema(engine)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        _drop_test_schema(engine)
        engine.dispose()


def _drop_test_schema(engine) -> None:
    assert _is_test_db(engine.url), "refusing schema cleanup outside a PostgreSQL *_test database"
    Base.metadata.drop_all(engine)
    # create_all/drop_all do not manage Alembic's table. A leftover revision
    # otherwise tells migrations that absent application tables already exist.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def client(db_session, monkeypatch, tmp_path):
    """API client whose requests, and the background worker (run it with
    tests.helpers.run_worker), all use the test session; uploads waiting for
    the worker go to a temporary folder."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(ingestion_background, "open_session", lambda: nullcontext(db_session))
    progress_sessions = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(ingestion_background, "open_progress_session", progress_sessions)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
