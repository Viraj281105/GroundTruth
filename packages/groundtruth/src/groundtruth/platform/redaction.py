"""Remove credentials from text before it is logged or sent anywhere (#39, #50).

**Owner: Bhumi.** Used by the API's error envelope and by every log handler the API and the
worker configure, so no log line carries a configured secret, a database password, a bearer
token or key material. It rewrites only those; file paths and tracebacks stay, because a
developer reading the server log needs them. (What a *client* may see is narrower still: see
:func:`groundtruth.platform.api.error_envelope.scrub_text`.)
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import SecretStr

from groundtruth.platform.config import get_settings

REDACTED = "[redacted]"

CONNECTION_CREDENTIALS = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.\-]*://)[^/\s:@]+(?::[^/\s@]*)?@")
BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=\-]{16,}")
PEM = re.compile(r"-----BEGIN[^-]*-----.*?-----END[^-]*-----", re.DOTALL)
MIN_SECRET_LENGTH = 6
"""Shorter values are not searched for: replacing every "abc" would make logs unreadable."""


def secret_values() -> list[str]:
    """Every secret the settings hold, longest first, so a longer one is not cut by a shorter."""
    settings = get_settings()
    found: set[str] = set()
    for name in getattr(type(settings), "model_fields", {}):
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
    return sorted((s for s in found if len(s) >= MIN_SECRET_LENGTH), key=len, reverse=True)


def redact_secrets(text: str) -> str:
    """``text`` without configured secrets, connection-string credentials or key material."""
    for secret in secret_values():
        text = text.replace(secret, REDACTED)
    text = PEM.sub(REDACTED, text)
    text = BEARER.sub(rf"\1{REDACTED}", text)
    return CONNECTION_CREDENTIALS.sub(r"\1<credentials>@", text)


__all__ = ["REDACTED", "redact_secrets", "secret_values"]
