import json
import time
import logging
from copy import deepcopy
from contextvars import ContextVar
from threading import Lock
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Context variables for structured logging correlation
CorrelationID = ContextVar("correlation_id", default=None)
RequestID = ContextVar("request_id", default=None)
UserID = ContextVar("user_id", default=None)
OrgID = ContextVar("org_id", default=None)
JobID = ContextVar("job_id", default=None)

# Metrics counters (in-memory for now; can be replaced with Prometheus later)
_metrics: Dict[str, Any] = {
    "requests_total": 0,
    "requests_by_status": {},
    "request_latency_seconds": 0.0,
    "imports_total": 0,
    "imports_failed": 0,
    "imports_succeeded": 0,
    "imports_bytes_processed": 0,
    "worker_heartbeats": 0,
    "worker_failures": 0,
    "db_query_count": 0,
    "db_query_time_seconds": 0.0,
    "claude_requests_total": 0,
    "claude_request_cost_usd": 0.0,
    "errors_total": 0,
    "errors_by_type": {},
}
_metrics_lock = Lock()


class ObservabilityMiddleware:
    """Observe HTTP without buffering uploads or changing exception semantics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = dict(scope.get("headers", [])).get(b"x-correlation-id", b"")
        try:
            correlation = str(UUID(supplied.decode("ascii")))
        except (ValueError, UnicodeDecodeError):
            correlation = str(uuid4())
        variables = (CorrelationID, RequestID, UserID, OrgID, JobID)
        tokens = [variable.set(value) for variable, value in zip(
            variables, (correlation, str(uuid4()), None, None, None),
        )]
        started = start_timer()
        status_code = 500

        async def observed_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Correlation-ID"] = correlation
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        except Exception as exc:
            # Preserve upload-limit and server error handling in outer layers.
            if isinstance(exc, HTTPException):
                status_code = exc.status_code
            else:
                increment_metric("errors_total")
                increment_metric(f"errors_by_type_{type(exc).__name__}")
                log_structured("ERROR", "Unhandled request exception", extra={
                    "exception_type": type(exc).__name__, "method": scope["method"],
                })
            raise
        finally:
            try:
                state = scope.get("state", {})
                UserID.set(str(state["user_id"]) if state.get("user_id") else None)
                OrgID.set(str(state["org_id"]) if state.get("org_id") else None)
                duration = end_timer(started, "http_request")
                increment_metric("requests_total")
                increment_metric(f"requests_by_status_{status_code}")
                log_structured("INFO", "HTTP request completed", extra={
                    "method": scope["method"],
                    "path": getattr(scope.get("route"), "path", "unmatched"),
                    "status_code": status_code, "duration_seconds": duration,
                })
            finally:
                for variable, token in zip(variables, tokens):
                    variable.reset(token)

# Logger setup
_logger = logging.getLogger("auditmind.observability")
_logger.setLevel(logging.INFO)


class StructuredFormatter(logging.Formatter):
    """JSON logging formatter that injects correlation context variables."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "correlation_id": getattr(record, "correlation_id", None),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
            "org_id": getattr(record, "org_id", None),
            "job_id": getattr(record, "job_id", None),
            "message": record.getMessage(),
        }
        # Merge any extra keys set on the record
        for key in (
            "metric_key", "current", "threshold", "method", "path",
            "status_code", "duration_seconds", "exception_type",
        ):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        return json.dumps(entry)


_handler = logging.StreamHandler()
_handler.setFormatter(StructuredFormatter())
_logger.addHandler(_handler)


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context (request/job)."""
    CorrelationID.set(cid)


def set_request_id(rid: str) -> None:
    """Set the request ID for the current HTTP request."""
    RequestID.set(rid)


def set_user_id(uid: str) -> None:
    """Set the user ID for the current context."""
    UserID.set(uid)


def set_org_id(oid: str) -> None:
    """Set the organization ID for the current context."""
    OrgID.set(oid)


def set_job_id(jid: str) -> None:
    """Set the job ID for the current background worker job."""
    JobID.set(jid)


def increment_metric(name: str, value: int | float = 1) -> None:
    """Increment a metrics counter by the given value."""
    with _metrics_lock:
        _metrics[name] = _metrics.get(name, 0) + value


def set_metric(name: str, value: Any) -> None:
    """Set a metrics counter to an explicit value."""
    with _metrics_lock:
        _metrics[name] = deepcopy(value)


def get_metrics() -> Dict[str, Any]:
    """Return a snapshot of current metrics."""
    with _metrics_lock:
        return deepcopy(_metrics)


def log_structured(
    level: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a structured JSON message with correlation context.

    Includes active context variables. The JSON formatter emits only the
    selected metadata fields above; callers must keep message text safe.
    """
    extra = dict(extra or {})
    record = _logger.makeRecord(
        name=_logger.name,
        level=getattr(logging, level.upper(), logging.INFO),
        fn=extra.pop("pathname", ""),
        lno=extra.pop("lineno", 0),
        msg=message,
        args=(),
        exc_info=extra.pop("exc_info", None) if extra else None,
    )
    # Inject context variables into the record
    record.correlation_id = CorrelationID.get()
    record.request_id = RequestID.get()
    record.user_id = UserID.get()
    record.org_id = OrgID.get()
    record.job_id = JobID.get()
    if extra:
        record.__dict__.update(extra)
    _logger.handle(record)


def start_timer() -> float:
    """Start a timer for measuring request latency. Returns the start time."""
    return time.perf_counter()


def end_timer(start_time: float, label: str, extra: Optional[Dict[str, Any]] = None) -> float:
    """End a timer and accumulate elapsed seconds without retaining samples.

    Returns the elapsed time in seconds.
    """
    elapsed = time.perf_counter() - start_time
    increment_metric("request_latency_seconds", elapsed)  # coarse aggregation
    # Also log as structured message
    log_structured(
        "INFO",
        f"request_latency_{label}: {elapsed:.3f}s",
        extra=extra or {},
    )
    return elapsed


# --- Alert helpers (simple in-memory; can connect to Alertmanager/Prometheus) ---

_alert_handlers: list = []


def register_alert_handler(handler) -> None:
    """Register a callable that receives alert dicts.

    Handler signature: handler(alert: dict) -> None
    """
    _alert_handlers.append(handler)


def alert(
    level: str,
    title: str,
    description: str,
    metric_key: Optional[str] = None,
    current: Optional[float] = None,
    threshold: Optional[float] = None,
) -> None:
    """Emit an alert with optional metric-based triggering.

    If metric_key and threshold are provided, the alert is only fired
    when the current value exceeds the threshold.
    """
    alert_data = {
        "timestamp": time.time(),
        "level": level,
        "title": title,
        "description": description,
    }
    if metric_key and current is not None and threshold is not None:
        if current > threshold:
            alert_data["metric_key"] = metric_key
            alert_data["current"] = current
            alert_data["threshold"] = threshold
            for handler in _alert_handlers:
                try:
                    handler(alert_data)
                except Exception:
                    pass  # never let alert handler break the app
    else:
        # Fire regardless (useful for static alerts)
        for handler in _alert_handlers:
            try:
                handler(alert_data)
            except Exception:
                pass
