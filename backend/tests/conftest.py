import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base

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
