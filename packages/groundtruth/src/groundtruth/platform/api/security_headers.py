"""Security headers on every API response (#51).

**Owner: Bhumi.** The API serves JSON, CSV, PDF and GeoJSON, never a page, so the policy is the
strictest there is: nothing may load, nothing may frame it, and a browser must not guess a
content type. The interactive docs (``/docs``, ``/redoc``) are the one exception: they are
pages that load Swagger UI and ReDoc from the jsDelivr CDN, so they get a policy that allows
exactly that. ``Strict-Transport-Security`` is sent only when ``APP_ENV=production``, because a
development server speaks plain HTTP and HSTS would lock a browser out of it.

A header a route has already set is left alone.
"""

from __future__ import annotations

from collections.abc import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from groundtruth.platform.config import get_settings

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
"""Nothing loads, nothing frames, no forms: right for a JSON API."""

DOCS_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
"""What Swagger UI and ReDoc need, as FastAPI serves them, and no more."""

DOCS_PATHS = ("/docs", "/redoc")

HSTS = "max-age=31536000; includeSubDomains"

BASE_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
    ("cross-origin-opener-policy", "same-origin"),
    ("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
)


def headers_for(path: str, *, production: bool) -> list[tuple[str, str]]:
    """The security headers for a response to ``path``."""
    docs = path == DOCS_PATHS[0] or path.startswith(f"{DOCS_PATHS[0]}/") or path == DOCS_PATHS[1]
    headers = [*BASE_HEADERS, ("content-security-policy", DOCS_CSP if docs else API_CSP)]
    if production:
        headers.append(("strict-transport-security", HSTS))
    return headers


class SecurityHeadersMiddleware:
    """Adds :func:`headers_for` to every HTTP response, errors and CORS preflights included."""

    def __init__(self, app: ASGIApp, *, production: Callable[[], bool] | None = None) -> None:
        self.app = app
        self._production = production or (lambda: get_settings().app_env == "production")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = headers_for(scope.get("path", ""), production=self._production())

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                for name, value in extra:
                    key = name.encode("latin-1")
                    if key not in present:
                        headers.append((key, value.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


__all__ = ["API_CSP", "DOCS_CSP", "SecurityHeadersMiddleware", "headers_for"]
