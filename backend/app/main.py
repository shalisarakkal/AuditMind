from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ai, assets, auth, dashboard, findings, orgs, reports, risk, scans
from app.core.config import settings
from app.core.middleware import UploadSizeLimitMiddleware

app = FastAPI(title=settings.PROJECT_NAME)

# Added first so CORS wraps it: its 413s still carry CORS headers.
app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router_prefix = settings.API_V1_STR
app.include_router(auth.router, prefix=api_router_prefix)
app.include_router(orgs.router, prefix=api_router_prefix)
app.include_router(assets.router, prefix=api_router_prefix)
app.include_router(scans.router, prefix=api_router_prefix)
app.include_router(findings.router, prefix=api_router_prefix)
app.include_router(risk.router, prefix=api_router_prefix)
app.include_router(reports.router, prefix=api_router_prefix)
app.include_router(dashboard.router, prefix=api_router_prefix)
app.include_router(ai.router, prefix=api_router_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
