import asyncio

import pytest

from app.core.middleware import UploadSizeLimitMiddleware
from app.core.config import settings


@pytest.mark.parametrize("declared,chunks,expected", [
    (str(3 * 1024 * 1024 + 1), [], 413),
    (None, [b"x" * 1024 * 1024] * 4, 413),
    ("1", [b"x" * 1024 * 1024] * 4, 413),
    ("2", [b"ok"], 200),
], ids=["declared", "chunked", "underreported", "within-limit"])
@pytest.mark.parametrize("prefix", ["/api/v1", "/custom-api"])
def test_logo_request_is_bounded_before_multipart_parsing(declared, chunks, expected, prefix, monkeypatch):
    monkeypatch.setattr(settings, "API_V1_STR", prefix)
    sent = []
    remaining = list(chunks)

    async def receive():
        body = remaining.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(remaining)}

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        while (await receive())["more_body"]:
            pass
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    scope = {"type": "http", "method": "POST", "path": prefix + "/orgs/test/logo",
             "headers": [(b"content-length", declared.encode())] if declared else []}
    asyncio.run(UploadSizeLimitMiddleware(downstream)(scope, receive, send))
    assert sent[0]["status"] == expected
    if expected == 413:
        assert b"3 MiB" in sent[1]["body"]
