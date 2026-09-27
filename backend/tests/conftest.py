from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services import ingestion_background

TEST_DB_URL = settings.TEST_DATABASE_URL or settings.DATABASE_URL


def _db_available(url: str) -> bool:
    try:
        engine = create_engine(url)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available(TEST_DB_URL)

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason=f"Postgres is not reachable at {TEST_DB_URL!r}; skipping DB-backed test.",
)


@pytest.fixture
def db_session():
    engine = create_engine(TEST_DB_URL)
    # `documents` needs the pgvector extension enabled in the test DB
    # (see scripts/create_databases.sql).
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    """API client whose requests, and background imports, all use the test
    session. (TestClient runs background tasks before the request returns.)"""
    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(ingestion_background, "open_session", lambda: nullcontext(db_session))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
