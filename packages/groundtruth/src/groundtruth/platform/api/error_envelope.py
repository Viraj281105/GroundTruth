"""One shape for every error the API sends, whichever router produced it (#39).

**Owner: Bhumi.** The UI must be able to act on an error without parsing prose, tell a
scientific refusal from a malfunction, and never be shown a stack trace or a file path. Routes
raise errors in several ways (``api_error``, a bare ``HTTPException``, FastAPI's own validation
error, Viraj's ``auth_error``, the CSRF guard, an unexpected exception), so rather than touch
each one this middleware normalises the response on its way out. It sits inside CORS, so even
a 500 carries CORS headers and the browser can read it.

What it does to a response with status 400 or above whose body is JSON:

* adds ``request_id`` (also sent as the ``X-Request-ID`` header on **every** response) and a
  top-level ``is_refusal``. A scientific refusal says ``true``; everything else says ``false``.
  A dict ``detail`` gets ``is_refusal`` inside it too, where engine failures already had it;
* turns FastAPI's validation list into the same envelope without losing its field names: the
  ``detail`` list stays (``loc``, ``msg``, ``type`` per entry, which the UI already reads), and
  ``code: "validation_error"``, a ``message`` and the dotted ``fields`` are added. The
  submitted ``input`` is dropped, because a rejected password field would otherwise be echoed;
* scrubs every string in the body: absolute file paths (the file name is kept), tracebacks,
  SQL and its parameters, credentials in connection strings, and any configured secret.

It never removes a key, and the scrub only rewrites the patterns above, so ``code``,
``remediation``, ``stage`` and ``hint`` reach the UI intact.

An exception no route handled becomes a JSON 500 with a safe generic message and the request
id. The real traceback goes to the server log, with configured secrets removed first.
"""

from __future__ import annotations

import json
import re
import traceback
import uuid
from typing import Any
from urllib.parse import urlsplit

from pydantic import SecretStr
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from groundtruth.logging import get_logger
from groundtruth.platform.config import get_settings

logger = get_logger("api.errors")

REQUEST_ID_HEADER = b"x-request-id"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "The server hit an unexpected error and could not complete the request."

# --- scrubbing ---------------------------------------------------------------------------

_WINDOWS_PATH = re.compile(
    # A drive letter that is not the tail of a URL scheme ("s:" in https://), then at least one
    # component. Directories may hold spaces; the final file name may not.
    r"""(?<![A-Za-z0-9+.\-])[A-Za-z]:[\\/](?![\\/])(?:[^\\/'"<>|?*:\r\n]+[\\/])*[^\\/\s'"<>|?*:]+"""
)
_POSIX_PATH = re.compile(
    r"""(?<![\w:/.\-])/(?:home|Users|usr|var|app|opt|tmp|srv|mnt|root|etc|proc|workspace|builds|snap)"""
    r"""(?:/[^/\s'"<>]+)*/?"""
)
_TRACEBACK = re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL)
_FRAME = re.compile(r'File "[^"\n]*", line \d+(?:, in [^\s,]+)?')
_SQL = re.compile(r"\[SQL:.*", re.DOTALL)
_PARAMETERS = re.compile(r"\[parameters:.*", re.DOTALL)
_CONNECTION_CREDENTIALS = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.\-]*://)[^/\s:@]+(?::[^/\s@]*)?@")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=\-]{16,}")
_PEM = re.compile(r"-----BEGIN[^-]*-----.*?-----END[^-]*-----", re.DOTALL)
_TRAILING_PUNCTUATION = ".,;:)]}"
_MIN_SECRET_LENGTH = 6


def _keep_file_name(match: re.Match[str]) -> str:
    """Replace a path with ``<path>/name``: the directories go, the file name stays."""
    text = match.group(0)
    stripped = text.rstrip(_TRAILING_PUNCTUATION)
    tail = text[len(stripped) :]
    name = re.split(r"[\\/]", stripped)[-1]
    return f"<path>/{name}{tail}" if name else f"<path>{tail}"


def _secret_values() -> list[str]:
    """Every secret the settings hold, longest first, so a longer one is not cut by a shorter."""
    settings = get_settings()
    found: set[str] = set()
    for name in type(settings).model_fields:
        value = getattr(settings, name, None)
        if isinstance(value, SecretStr):
            found.add(value.get_secret_value())
    url = getattr(settings, "database_url", None)
    if url:
        try:
            password = urlsplit(str(url)).password
        except ValueError:
            password = None
        if password:
            found.add(password)
    return sorted((s for s in found if len(s) >= _MIN_SECRET_LENGTH), key=len, reverse=True)


def redact_secrets(text: str) -> str:
    """``text`` without configured secrets, connection-string credentials or key material.

    Safe for logs: file paths and tracebacks are left alone, because a developer needs them.
    """
    for secret in _secret_values():
        text = text.replace(secret, "[redacted]")
    text = _PEM.sub("[redacted]", text)
    text = _BEARER.sub(r"\1[redacted]", text)
    return _CONNECTION_CREDENTIALS.sub(r"\1<credentials>@", text)


def scrub_text(text: str) -> str:
    """``text`` that is safe to send to a client.

    Rewrites only: absolute paths (the file name is kept), tracebacks and their frames, SQL and
    its parameters, and secrets. Everything else, including codes and instructions, is returned
    exactly as it came in.
    """
    text = redact_secrets(text)
    text = _TRACEBACK.sub("[traceback removed]", text)
    text = _FRAME.sub("[frame removed]", text)
    text = _SQL.sub("[SQL removed]", text)
    text = _PARAMETERS.sub("[parameters removed]", text)
    text = _WINDOWS_PATH.sub(_keep_file_name, text)
    return _POSIX_PATH.sub(_keep_file_name, text)


def scrub_optional(text: str | None) -> str | None:
    """:func:`scrub_text` for a field that may be absent."""
    return None if text is None else scrub_text(text)


def scrub_json(value: Any) -> Any:
    """:func:`scrub_text` applied to every string value inside a JSON-like structure."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: scrub_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_json(item) for item in value]
    return value


# --- the envelope ------------------------------------------------------------------------


def _dotted(loc: Any) -> str:
    return ".".join(str(part) for part in loc) if isinstance(loc, list | tuple) else str(loc)


def normalise_error_body(body: dict[str, Any], status: int, request_id: str) -> dict[str, Any]:
    """The envelope for one error body. Keeps every existing key and shape of ``detail``."""
    detail = body.get("detail")
    refusal = body.get("is_refusal")
    if not isinstance(refusal, bool):
        inner = detail.get("is_refusal") if isinstance(detail, dict) else None
        refusal = inner if isinstance(inner, bool) else False

    out = dict(body)
    if isinstance(detail, list):
        # FastAPI's validation errors: keep the field names, drop what was submitted.
        entries = [
            {key: entry[key] for key in ("type", "loc", "msg") if key in entry}
            for entry in detail
            if isinstance(entry, dict)
        ]
        fields = [_dotted(entry["loc"]) for entry in entries if "loc" in entry]
        summary = "; ".join(
            f"{_dotted(entry.get('loc', '?'))}: {entry.get('msg', 'invalid')}"
            for entry in entries[:5]
        )
        out["detail"] = entries
        out.setdefault("code", "validation_error")
        out.setdefault("message", f"Invalid request. {summary}".strip())
        out.setdefault("fields", fields)
    elif isinstance(detail, dict):
        out["detail"] = {**detail, "is_refusal": refusal}
    elif isinstance(detail, str):
        out.setdefault("code", f"http_{status}")
        out.setdefault("message", detail)
    out["is_refusal"] = refusal
    out["request_id"] = request_id
    return scrub_json(out)  # type: ignore[no-any-return]


def internal_error_body(request_id: str) -> dict[str, Any]:
    """The body of a 500 for an exception nobody handled."""
    return {
        "detail": {
            "code": INTERNAL_ERROR_CODE,
            "message": INTERNAL_ERROR_MESSAGE,
            "hint": f"Try again. If it keeps happening, report this request id: {request_id}.",
            "is_refusal": False,
        },
        "is_refusal": False,
        "request_id": request_id,
    }


def _set_headers(
    headers: list[tuple[bytes, bytes]], request_id: str, *, length: int | None = None
) -> list[tuple[bytes, bytes]]:
    drop = {REQUEST_ID_HEADER} | ({b"content-length"} if length is not None else set())
    kept = [(k, v) for k, v in headers if k.lower() not in drop]
    kept.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
    if length is not None:
        kept.append((b"content-length", str(length).encode("ascii")))
    return kept


def _is_json(headers: list[tuple[bytes, bytes]]) -> bool:
    return any(k.lower() == b"content-type" and b"json" in v.lower() for k, v in headers)


def _incoming_request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key.lower() == REQUEST_ID_HEADER:
            candidate = value.decode("latin-1")
            if _VALID_REQUEST_ID.fullmatch(candidate):
                return candidate
    return uuid.uuid4().hex[:16]


class ErrorEnvelopeMiddleware:
    """Gives every error response the envelope described in the module docstring."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        sent_start = False
        held: Message | None = None
        chunks: list[bytes] = []

        async def wrapped_send(message: Message) -> None:
            nonlocal sent_start, held
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if message["status"] >= 400 and _is_json(headers):
                    held = {**message, "headers": headers}  # decided once the body is in
                    return
                sent_start = True
                await send({**message, "headers": _set_headers(headers, request_id)})
                return
            if message["type"] == "http.response.body" and held is not None:
                chunks.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                start, raw = held, b"".join(chunks)
                held = None
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict):
                    raw = json.dumps(
                        normalise_error_body(parsed, start["status"], request_id), default=str
                    ).encode("utf-8")
                sent_start = True
                await send(
                    {
                        **start,
                        "headers": _set_headers(start["headers"], request_id, length=len(raw)),
                    }
                )
                await send({"type": "http.response.body", "body": raw})
                return
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception as exc:
            trace = redact_secrets("".join(traceback.format_exception(exc)))
            logger.error(
                "unhandled exception on %s %s (request %s)\n%s",
                scope.get("method", "?"),
                scope.get("path", "?"),
                request_id,
                trace,
            )
            if sent_start:
                raise  # the client already has a response; nothing safe is left to send
            raw = json.dumps(internal_error_body(request_id)).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": _set_headers(
                        [(b"content-type", b"application/json")], request_id, length=len(raw)
                    ),
                }
            )
            await send({"type": "http.response.body", "body": raw})


__all__ = [
    "INTERNAL_ERROR_CODE",
    "ErrorEnvelopeMiddleware",
    "internal_error_body",
    "normalise_error_body",
    "redact_secrets",
    "scrub_json",
    "scrub_optional",
    "scrub_text",
]
