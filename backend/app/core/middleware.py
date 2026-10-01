import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.exceptions import HTTPException

from app.core.config import settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

IMPORT_PATH_SUFFIXES = ("/assets/import", "/findings/import", "/imports")
# Room for the multipart envelope around the file itself; the exact file
# limit is enforced again when the endpoint reads the upload.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class _TooLarge(HTTPException):
    # An HTTPException, so FastAPI passes it through body parsing (anything
    # else there becomes a generic 400) and renders it as a 413.
    def __init__(self) -> None:
        super().__init__(status_code=413, detail=upload_limit_message())


class UploadSizeLimitMiddleware:
    """Rejects import uploads over IMPORT_MAX_BYTES while they arrive.

    FastAPI parses (and spools) a multipart body before any dependency runs,
    auth included, so without this anyone could make the server store an
    arbitrarily large upload before being turned away. The declared
    Content-Length is checked up front, and the bytes actually received are
    counted as well (chunked uploads declare no length)."""

    def __init__(self, app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not (
            scope["type"] == "http" and scope["method"] == "POST" and scope["path"].endswith(IMPORT_PATH_SUFFIXES)
        ):
            await self.app(scope, receive, send)
            return

        limit = settings.IMPORT_MAX_BYTES + _MULTIPART_OVERHEAD_BYTES
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _reject(send)
            return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _TooLarge:
            if not started:
                await _reject(send)


def upload_limit_message() -> str:
    return f"File exceeds the {settings.IMPORT_MAX_BYTES // (1024 * 1024)} MB upload limit"


async def _reject(send: Send) -> None:
    body = json.dumps({"detail": upload_limit_message()}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
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
