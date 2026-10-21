"""Atomic rolling-hour admission, shared across API/worker processes.

Reservations commit before network I/O. Unknown outcomes remain charged at the
reservation estimate; a restart cannot reset limits or forget in-flight calls.
Costs are estimates, not an invoice from the provider.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_usage import AIUsage


def reserve(bind, org_id: uuid.UUID, model: str, estimated_usd: float) -> uuid.UUID:
    from app.services.claude_service import ClaudeOperationalError

    amount = max(settings.CLAUDE_ATTEMPT_RESERVE_USD, estimated_usd)
    with Session(bind) as db, db.begin():
        lock = int.from_bytes(hashlib.sha256(f"ai:{org_id}".encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        now = datetime.now(timezone.utc)
        count, cost = db.execute(select(func.count(), func.coalesce(func.sum(case(
            (AIUsage.status == "succeeded", AIUsage.cost_usd), else_=AIUsage.reserved_usd)), 0))
            .where(AIUsage.org_id == org_id, AIUsage.created_at > now - timedelta(hours=1))).one()
        if count >= settings.CLAUDE_ORG_CALLS_PER_HOUR or cost + amount > settings.CLAUDE_ORG_MAX_COST_PER_HOUR_USD:
            raise ClaudeOperationalError("Organization Claude hourly quota exceeded", status_code=429)
        row = AIUsage(id=uuid.uuid4(), org_id=org_id, model=model, reserved_usd=amount, created_at=now)
        db.add(row)
        return row.id


def finish(bind, attempt_id: uuid.UUID, *, input_tokens=0, output_tokens=0, cost_usd=0.0, success=False):
    with Session(bind) as db, db.begin():
        row = db.get(AIUsage, attempt_id, with_for_update=True)
        if row.status != "reserved":
            return
        row.status = "succeeded" if success else "failed"
        row.input_tokens = input_tokens
        row.output_tokens = output_tokens
        row.cost_usd = cost_usd
