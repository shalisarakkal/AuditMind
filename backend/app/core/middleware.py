import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.exceptions import HTTPException

from app.core.config import settings
from app.services.rate_limit import upload_limiter

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

# Room for the multipart envelope around the file itself; the exact file
# limit is enforced again when the endpoint reads the upload.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
DOCUMENT_MAX_BYTES = 10 * 1024 * 1024


def _upload_budget(path: str) -> tuple[int, str] | None:
    """Only file-bearing endpoints, including their trailing-slash redirect.

    Keep metadata/search/lifecycle requests outside the upload budget. Limits
    are checked before Starlette can parse/spool an unauthenticated body.
    """
    path = path.rstrip("/")
    prefix = settings.API_V1_STR.rstrip("/")
    if not path.startswith(prefix + "/"):
        return None
    parts = path[len(prefix) + 1:].split("/")
    org = len(parts) >= 3 and parts[0] == "orgs" and bool(parts[1])
    if (org and parts[2:] == ["documents"]) or parts == ["platform", "documents"]:
        return (DOCUMENT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES,
                "Document request exceeds the 11 MiB transport limit (file limit: 10 MiB)")
    if org and parts[2:] == ["logo"]:
        return (2 * 1024 * 1024 + _MULTIPART_OVERHEAD_BYTES,
                "Logo request exceeds the 3 MiB transport limit (file limit: 2 MiB)")
    if org and tuple(parts[2:]) in (("assets", "import"), ("findings", "import"), ("imports",)):
        return settings.IMPORT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES, upload_limit_message()
    return None


class _TooLarge(HTTPException):
    # An HTTPException, so FastAPI passes it through body parsing (anything
    # else there becomes a generic 400) and renders it as a 413.
    def __init__(self, detail: str | None = None) -> None:
        super().__init__(status_code=413, detail=detail or upload_limit_message())


class UploadSizeLimitMiddleware:
    """Bound and throttle imports, documents and logos before body parsing.

    FastAPI parses (and spools) a multipart body before any dependency runs,
    auth included, so without this anyone could make the server store an
    arbitrarily large upload before being turned away. The declared
    Content-Length is checked up front, and the bytes actually received are
    counted as well (chunked uploads declare no length)."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        budget = _upload_budget(scope.get("path", "")) if scope["type"] == "http" and scope["method"] == "POST" else None
        if budget is None:
            await self.app(scope, receive, send)
            return

        # The ASGI client address is supplied by the server's trusted-proxy
        # configuration, not an arbitrary X-Forwarded-For request header.
        client = scope.get("client")
        retry_after = upload_limiter.hit(str(client[0]) if client else "unknown")
        if retry_after is not None:
            await _reject(send, "Too many upload requests; wait before retrying", status=429, retry_after=retry_after)
            return
        limit, detail = budget
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _reject(send, detail)
            return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge(detail)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _reject(send, detail)


def upload_limit_message() -> str:
    limit = settings.IMPORT_MAX_BYTES
    if limit >= 1024**3 and limit % 1024**3 == 0:
        return f"File exceeds the {limit // 1024**3} GB upload limit"
    return f"File exceeds the {limit // (1024 * 1024)} MB upload limit"


async def _reject(send: Send, detail: str | None = None, *, status: int = 413,
                  retry_after: int | None = None) -> None:
    body = json.dumps({"detail": detail or upload_limit_message()}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"cache-control", b"no-store")]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode()))
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


# Swagger and ReDoc load their scripts and styles from a CDN.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_API_CSP = b"default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware:
    """Headers on every response: no framing, no type sniffing, no
    referrer; on the API a CSP that allows nothing (it serves JSON, not
    pages) and no caching of sign-in responses; HSTS over HTTPS. The
    frontend's pages get their own CSP (frontend/src/proxy.ts)."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                ]
                if not path.startswith(_DOCS_PATHS):
                    headers.append((b"content-security-policy", _API_CSP))
                if path.startswith(f"{settings.API_V1_STR}/auth"):
                    headers.append((b"cache-control", b"no-store"))
                if settings.COOKIE_SECURE:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, with_headers)
