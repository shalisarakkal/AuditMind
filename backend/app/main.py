import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ai, archive, assets, auth, dashboard, findings, import_profiles, orgs, reports, risk, scans
from app.core import archive_schedule
from app.core.config import settings
from app.core.middleware import UploadSizeLimitMiddleware


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(archive_schedule.fail_interrupted_jobs)
    task = asyncio.create_task(archive_schedule.auto_purge_loop()) if settings.ARCHIVE_AUTO_PURGE else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

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
app.include_router(import_profiles.router, prefix=api_router_prefix)
app.include_router(ai.router, prefix=api_router_prefix)
app.include_router(archive.router, prefix=api_router_prefix)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
