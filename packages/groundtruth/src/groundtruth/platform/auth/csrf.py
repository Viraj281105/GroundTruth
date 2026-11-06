"""Origin check for cookie-authenticated unsafe requests.

Only requests that are unsafe (not GET/HEAD/OPTIONS) *and* carry the session cookie are
checked: a request without the cookie cannot act as a signed-in user, so there is
nothing to forge. The ``Origin`` (or, failing that, ``Referer``) must be in the CORS
allow-list.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from groundtruth.platform.auth.sessions import COOKIE_NAME

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_BODY = json.dumps(
    {
        "detail": {
            "code": "csrf_origin_rejected",
            "message": "The request's origin is not allowed.",
            "hint": None,
        }
    }
).encode()


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def _has_session_cookie(cookie_header: str) -> bool:
    return any(part.strip().startswith(f"{COOKIE_NAME}=") for part in cookie_header.split(";"))


class CsrfOriginMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Callable[[], list[str]]) -> None:
        self.app = app
        self._allowed = allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if not _has_session_cookie(headers.get("cookie", "")):
            await self.app(scope, receive, send)
            return
        origin = headers.get("origin")
        if origin is None or origin == "null":
            referer = headers.get("referer")
            origin = _origin_of(referer) if referer and origin is None else None
        allowed = {o.lower() for o in self._allowed()}
        if origin is not None and origin.lower() in allowed:
            await self.app(scope, receive, send)
            return
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY})
