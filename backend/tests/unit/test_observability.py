"""Regression coverage for startup, HTTP telemetry, and concurrent metrics."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.core import observability as telemetry
from app.core.config import settings
from app.api.deps import require_sysadmin
from app.main import app


@pytest.fixture
def observed_app():
    instance = FastAPI()
    instance.add_middleware(telemetry.ObservabilityMiddleware)

    @instance.get("/ok/{item}")
    async def ok(item: str, request: Request):
        request.state.user_id = item
        await asyncio.sleep(0)
        return {"correlation_id": telemetry.CorrelationID.get()}

    @instance.get("/fail")
    async def fail():
        raise RuntimeError("password=secret-evidence")

    @instance.get("/forbidden")
    async def forbidden():
        raise HTTPException(403, "Access denied")

    @instance.get("/stream")
    async def stream():
        async def chunks():
            yield b"first"
            await asyncio.sleep(0)
            yield b"second"
        return StreamingResponse(chunks())

    return instance


def test_application_startup_health_and_metrics():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/metrics").status_code == 401
        app.dependency_overrides[require_sysadmin] = lambda: object()
        try:
            response = client.get("/metrics")
            assert response.status_code == 200
            assert isinstance(response.json()["request_latency_seconds"], float)
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["cache-control"] == "no-store"
        finally:
            app.dependency_overrides.pop(require_sysadmin)


def test_timer_accumulates_monotonic_seconds(monkeypatch):
    before = telemetry.get_metrics()["request_latency_seconds"]
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(telemetry.time, "perf_counter", lambda: next(ticks))
    assert telemetry.end_timer(telemetry.start_timer(), "test") == 0.25
    assert telemetry.get_metrics()["request_latency_seconds"] == before + 0.25


def test_request_status_error_redaction_and_context_cleanup(observed_app, caplog):
    before = telemetry.get_metrics()
    marker = telemetry.CorrelationID.set("parent")
    try:
        with TestClient(observed_app, raise_server_exceptions=False) as client:
            correlation = str(uuid4())
            response = client.get("/ok/private-value?token=private-token", headers={"x-correlation-id": correlation})
            assert response.status_code == 200
            assert response.headers["x-correlation-id"] == correlation
            assert response.json()["correlation_id"] == correlation
            missing = client.get("/missing", headers={"x-correlation-id": "unsafe-client-value"})
            UUID(missing.headers["x-correlation-id"])
            assert missing.status_code == 404
            failed = client.get("/fail")
            assert failed.status_code == 500
            assert failed.text == "Internal Server Error"
        assert telemetry.CorrelationID.get() == "parent"
    finally:
        telemetry.CorrelationID.reset(marker)
    after = telemetry.get_metrics()
    assert after["requests_total"] == before["requests_total"] + 3
    assert after["errors_total"] == before["errors_total"] + 1
    records = [record for record in caplog.records if record.name == telemetry._logger.name]
    output = "\n".join(telemetry.StructuredFormatter().format(record) for record in records)
    assert "password=secret-evidence" not in output
    assert "private-token" not in output
    assert "unsafe-client-value" not in output
    entries = [json.loads(telemetry.StructuredFormatter().format(record)) for record in records]
    assert any(entry.get("path") == "/ok/{item}" and entry["user_id"] == "private-value" for entry in entries)


def test_concurrent_request_context_isolation(observed_app):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=observed_app), base_url="http://test") as client:
            ids = [str(uuid4()) for _ in range(20)]
            responses = await asyncio.gather(*[
                client.get(f"/ok/{index}", headers={"x-correlation-id": value})
                for index, value in enumerate(ids)
            ])
            assert [response.json()["correlation_id"] for response in responses] == ids
        assert telemetry.CorrelationID.get() is None
        assert telemetry.UserID.get() is None
    asyncio.run(run())


def test_metrics_are_thread_safe_and_snapshots_are_independent():
    key = f"test_{uuid4().hex}"
    def increment():
        for _ in range(1000):
            telemetry.increment_metric(key)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: increment(), range(8)))
        assert telemetry.get_metrics()[key] == 8000
        snapshot = telemetry.get_metrics()
        snapshot["requests_by_status"]["fake"] = 99
        assert "fake" not in telemetry.get_metrics()["requests_by_status"]
    finally:
        with telemetry._metrics_lock:
            telemetry._metrics.pop(key, None)


def test_structured_logging_does_not_mutate_caller_metadata(caplog):
    metadata = {"pathname": "example", "lineno": 1, "status_code": 200}
    telemetry.log_structured("INFO", "test", metadata)
    assert metadata == {"pathname": "example", "lineno": 1, "status_code": 200}


def test_expected_errors_and_streaming_keep_response_contract(observed_app):
    before = telemetry.get_metrics()["errors_total"]
    with TestClient(observed_app) as client:
        denied = client.get("/forbidden")
        assert denied.status_code == 403
        assert denied.json() == {"detail": "Access denied"}
        response = client.get("/stream")
        assert response.status_code == 200
        assert response.content == b"firstsecond"
        UUID(response.headers["x-correlation-id"])
    assert telemetry.get_metrics()["errors_total"] == before


@pytest.mark.parametrize("fails", [False, True])
def test_middleware_restores_every_context_variable(fails):
    async def run():
        variables = (telemetry.CorrelationID, telemetry.RequestID, telemetry.UserID, telemetry.OrgID, telemetry.JobID)
        tokens = [variable.set("parent") for variable in variables]
        async def downstream(scope, receive, send):
            assert telemetry.UserID.get() is None
            assert telemetry.OrgID.get() is None
            assert telemetry.JobID.get() is None
            scope["state"] = {"user_id": "user", "org_id": "org"}
            if fails:
                raise RuntimeError("test error")
            await Response(status_code=204)(scope, receive, send)
        try:
            scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
            async def receive():
                return {"type": "http.request", "body": b""}
            async def send(message):
                pass
            middleware = telemetry.ObservabilityMiddleware(downstream)
            if fails:
                with pytest.raises(RuntimeError, match="test error"):
                    await middleware(scope, receive, send)
            else:
                await middleware(scope, receive, send)
            assert [variable.get() for variable in variables] == ["parent"] * 5
        finally:
            for variable, token in zip(variables, tokens):
                variable.reset(token)
    asyncio.run(run())


def test_outer_middleware_preserves_cors_security_and_upload_limits():
    with TestClient(app) as client:
        preflight = client.options("/health", headers={
            "origin": "http://localhost:3000", "access-control-request-method": "GET",
        })
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert preflight.headers["x-frame-options"] == "DENY"
        response = client.post("/api/v1/orgs/test/assets/import", headers={
            "origin": "http://localhost:3000", "content-length": str(10 * 1024**3),
        })
        assert response.status_code == 413
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert response.headers["x-content-type-options"] == "nosniff"


def test_chunked_upload_limit_is_preserved_without_authentication(monkeypatch):
    monkeypatch.setattr(settings, "IMPORT_MAX_BYTES", 100)
    def upload_chunks():
        yield b'--B\r\nContent-Disposition: form-data; name="file"; filename="big.csv"\r\n\r\n'
        for _ in range(48):
            yield b"x" * 65536
        yield b"\r\n--B--\r\n"
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/orgs/{uuid4()}/findings/import",
            content=upload_chunks(),
            headers={"content-type": "multipart/form-data; boundary=B"},
        )
    assert response.status_code == 413
    assert "upload limit" in response.json()["detail"]
