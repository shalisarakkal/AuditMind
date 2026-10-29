from typing import Any

from fastapi import Depends, FastAPI, Response
from fastapi.responses import JSONResponse
from app.services.readiness import readiness_checks
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_sysadmin
from app.api.routes import (
    ai,
    archive,
    assets,
    auth,
    dashboard,
    documents,
    events,
    findings,
    import_profiles,
    orgs,
    people,
    platform,
    reports,
    risk,
    scans,
    scoring_qualifications,
)
from app.core.config import check_secret_key, settings
from app.core.middleware import DOCUMENT_MAX_BYTES, SecurityHeadersMiddleware, UploadSizeLimitMiddleware
from app.services.organization_logos import MAX_UPLOAD as LOGO_MAX_BYTES
from app.core.observability import (
    ObservabilityMiddleware,
    log_structured,
    register_alert_handler,
)

check_secret_key(settings.SECRET_KEY)


# Background work (large imports, archive jobs, the daily purges) runs in
# the background worker, python -m app.worker, not here.
app = FastAPI(title=settings.PROJECT_NAME)

# Register alert handler - logs alerts as structured messages
def _alert_handler(alert_data: dict) -> None:
    log_structured("WARNING", f"ALERT: {alert_data['title']}", extra=alert_data)

register_alert_handler(_alert_handler)


app.add_middleware(ObservabilityMiddleware)
# Added first so CORS wraps it: its 413s still carry CORS headers.
app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Outermost, so every response has them, CORS preflights and errors too.
app.add_middleware(SecurityHeadersMiddleware)

api_router_prefix = settings.API_V1_STR
app.include_router(auth.router, prefix=api_router_prefix)
app.include_router(orgs.router, prefix=api_router_prefix)
app.include_router(people.router, prefix=api_router_prefix)
app.include_router(platform.router, prefix=api_router_prefix)
app.include_router(assets.router, prefix=api_router_prefix)
app.include_router(scans.router, prefix=api_router_prefix)
app.include_router(findings.router, prefix=api_router_prefix)
app.include_router(risk.router, prefix=api_router_prefix)
app.include_router(reports.router, prefix=api_router_prefix)
app.include_router(dashboard.router, prefix=api_router_prefix)
app.include_router(import_profiles.router, prefix=api_router_prefix)
app.include_router(ai.router, prefix=api_router_prefix)
app.include_router(archive.router, prefix=api_router_prefix)
app.include_router(events.router, prefix=api_router_prefix)
app.include_router(documents.router, prefix=api_router_prefix)
app.include_router(scoring_qualifications.router, prefix=api_router_prefix)


@app.get(f"{api_router_prefix}/upload-limits", tags=["uploads"])
def upload_limits(response: Response) -> dict[str, int]:
    """Non-sensitive browser preflight ceilings; no DB access or setting writes.

    Server transport/parser limits remain authoritative. Imports use the actual
    configured ceiling, not a frontend guess or a configuration/secret dump.
    """
    response.headers["Cache-Control"] = "no-store"
    return {
        "import_max_bytes": settings.IMPORT_MAX_BYTES,
        "document_max_bytes": DOCUMENT_MAX_BYTES,
        "logo_max_bytes": LOGO_MAX_BYTES,
    }


@app.get("/metrics", include_in_schema=False, dependencies=[Depends(require_sysadmin)])
def metrics() -> JSONResponse:
    """Expose process-local counters only to an authenticated platform admin.

    This is intentionally simple and in-memory; for production deployment,
    integrate with Prometheus, Datadog, or similar.
    """
    from app.core.observability import get_metrics
    return JSONResponse(content=get_metrics(), headers={"Cache-Control": "no-store"})


def get_current_metrics() -> dict[str, Any]:
    """Return a snapshot of current metrics from the observability module."""
    from app.core.observability import get_metrics
    return get_metrics()


@app.get("/health")
def health() -> dict[str, str]:
    """Cheap liveness probe; dependency readiness is a separate concern."""
    return {"status": "ok"}


@app.get("/ready")
def ready(checks: dict = Depends(readiness_checks)):
    healthy = all(checks.values())
    return JSONResponse(status_code=200 if healthy else 503,
                        content={"status": "ready" if healthy else "not_ready", "checks": checks},
                        headers={"Cache-Control": "no-store"})
