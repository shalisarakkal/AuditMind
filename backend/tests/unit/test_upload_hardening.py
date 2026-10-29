"""Admission must precede body consumption, authentication and disk spooling."""
import asyncio
import io
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.api.uploads import _receive
from app.core.config import settings
from app.core.middleware import UploadSizeLimitMiddleware, _upload_budget
from app.main import app
from app.services.rate_limit import SlidingWindowLimiter


@pytest.mark.parametrize("path", ["/orgs/test/documents", "/platform/documents"])
@pytest.mark.parametrize("suffix", ["", "/"])
@pytest.mark.parametrize("declared", [None, "1", str(11 * 1024**2 + 1)])
def test_document_transport_limits_streamed_and_declared_bodies(path, suffix, declared, monkeypatch):
    monkeypatch.setattr(settings, "API_V1_STR", "/custom")
    sent, reads = [], []
    async def receive():
        reads.append(True)
        return {"type": "http.request", "body": b"x" * (3 * 1024**2), "more_body": True}
    async def send(message):
        sent.append(message)
    async def downstream(scope, receive, send):
        while (await receive())["more_body"]:
            pass
        raise AssertionError("Oversized body reached endpoint")
    scope = {"type": "http", "method": "POST", "path": "/custom" + path + suffix,
             "headers": [] if declared is None else [(b"content-length", declared.encode())]}
    asyncio.run(UploadSizeLimitMiddleware(downstream)(scope, receive, send))
    assert sent[0]["status"] == 413
    assert b"11 MiB" in sent[1]["body"]
    assert len(reads) == (0 if declared == str(11 * 1024**2 + 1) else 4)


@pytest.mark.parametrize("path", ["/orgs/test/documents", "/platform/documents"])
def test_document_size_limit_precedes_auth_and_preserves_outer_headers(path):
    with TestClient(app) as client:
        response = client.post("/api/v1" + path, headers={
            "content-length": str(11 * 1024**2 + 1), "origin": "http://localhost:3000"})
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize("path", ["/api/v1/orgs/x/assets/import", "/api/v1/orgs/x/findings/import",
    "/api/v1/orgs/x/imports", "/api/v1/orgs/x/documents", "/api/v1/platform/documents", "/api/v1/orgs/x/logo"])
def test_upload_rate_limit_precedes_body_reads_and_cannot_be_forwarded_header_spoofed(path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT_PER_MINUTE", 1)
    async def run():
        sent, admitted = [], []
        async def receive():
            raise AssertionError("Do not read a rejected body")
        async def send(message):
            sent.append(message)
        async def downstream(scope, receive, send):
            admitted.append(True)
            await send({"type": "http.response.start", "status": 204, "headers": []})
        middleware = UploadSizeLimitMiddleware(downstream)
        scope = {"type": "http", "method": "POST", "path": path, "headers": [], "client": ("192.0.2.1", 123)}
        await middleware(scope, receive, send)
        scope["headers"] = [(b"x-forwarded-for", b"192.0.2.99")]
        await middleware(scope, receive, send)
        assert len(admitted) == 1
        assert sent[1]["status"] == 429
        assert int(dict(sent[1]["headers"])[b"retry-after"]) > 0
        assert dict(sent[1]["headers"])[b"cache-control"] == b"no-store"
        scope["client"] = ("192.0.2.2", 123)
        await middleware(scope, receive, send)
        assert len(admitted) == 2
    asyncio.run(run())


def test_all_upload_types_share_one_address_bucket_and_nonuploads_do_not(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT_PER_MINUTE", 1)
    with TestClient(app) as client:
        assert client.post("/api/v1/platform/documents").status_code != 429
        rejected = client.post("/api/v1/orgs/test/logo", headers={"origin": "http://localhost:3000"})
        assert rejected.status_code == 429
        assert rejected.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert rejected.headers["x-content-type-options"] == "nosniff"
        assert client.get("/health").status_code == 200
        assert client.post("/api/v1/orgs/test/documents/search").status_code != 429


@pytest.mark.parametrize("path", ["/not-api/orgs/x/documents", "/api/v1/platform/documents/load-baseline",
    "/api/v1/orgs/x/documents/search", "/api/v1/orgs/x/documents/bulk-retire",
    "/api/v1/orgs/x/documents/versions/y/reactivate", "/api/v1/unrelated/imports"])
def test_non_upload_routes_are_not_mistaken_for_file_transports(path):
    assert _upload_budget(path) is None


def test_limiter_is_bounded_fail_closed_and_recovers_without_resetting_live_keys():
    now = [0.0]
    limiter = SlidingWindowLimiter(lambda: 1, clock=lambda: now[0], max_keys=2)
    assert limiter.hit("a") is None
    assert limiter.hit("b") is None
    assert limiter.hit("c") is not None
    assert len(limiter._hits) == 2
    assert limiter.hit("a") is not None
    now[0] = 60.0
    assert limiter.hit("c") is None
    assert limiter.hit("a") is None
    assert len(limiter._hits) == 2


def test_limiter_threaded_admission_never_exceeds_quota():
    limiter = SlidingWindowLimiter(lambda: 7)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: limiter.hit("shared"), range(80)))
    assert sum(value is None for value in results) == 7


def test_large_upload_uses_private_exclusive_file_and_preserves_hash(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "private"))
    result = asyncio.run(_receive(UploadFile(file=io.BytesIO(b"test payload")), 100, 1))
    assert result.content is None
    assert result.path.read_bytes() == b"test payload"
    assert result.sha256 == hashlib.sha256(b"test payload").hexdigest()
    if os.name == "posix":
        assert stat.S_IMODE(result.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(result.path.parent.stat().st_mode) == 0o700


def test_interrupted_upload_removes_only_its_owned_temporary_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    class Interrupted:
        reads = 0
        async def read(self, count):
            self.reads += 1
            if self.reads == 1:
                return b"payload"
            raise InterruptedError("Synthetic interrupted upload")
    with pytest.raises(InterruptedError):
        asyncio.run(_receive(Interrupted(), 100, 1))
    assert list(tmp_path.iterdir()) == []
