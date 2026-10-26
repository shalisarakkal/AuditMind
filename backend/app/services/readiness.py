"""Bounded, redacted dependency probe. Never creates storage or starts work."""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.event import WorkerStatus


def inspect_readiness(engine, directory):
    checks = {"database": False, "uploads": False, "worker": False}
    try:
        checks["uploads"] = directory.is_dir() and os.access(directory, os.R_OK | os.W_OK | os.X_OK)
    except OSError:
        pass
    try:
        with Session(engine) as db:
            db.execute(text("SET LOCAL statement_timeout = '1000ms'"))
            db.execute(text("SELECT 1"))
            checks["database"] = True
            heartbeat = db.scalar(select(WorkerStatus.heartbeat_at).where(WorkerStatus.id == 1))
            if heartbeat is not None:
                age = datetime.now(timezone.utc) - heartbeat
                checks["worker"] = timedelta(0) <= age < timedelta(seconds=settings.WORKER_STALE_SECONDS // 2)
    except Exception:
        # No exception strings, paths, connection URLs or credentials in the response.
        pass
    return checks


def readiness_checks():
    # Separate non-pooled probe cannot wait behind the application's connection pool.
    engine = create_engine(settings.DATABASE_URL, poolclass=NullPool,
                           connect_args={"connect_timeout": 2})
    try:
        return inspect_readiness(engine, settings.upload_dir)
    finally:
        engine.dispose()
