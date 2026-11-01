"""Opaque pagination cursors for the run listing.

A cursor is the position of the last run on a page, ``(created_at, run_id)``, plus a
fingerprint of the filters it was issued for. Binding it to the filters catches the
easy mistake of changing a filter and keeping the old cursor, which would otherwise
return a page that belongs to neither query.

It is not signed: it holds nothing secret, and a forged cursor can only move where the
page starts. The fingerprint uses ``blake2b``, never Python's salted ``hash()`` (R8).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from groundtruth.platform.store.interface import RunCursor, RunFilter

_VERSION = 1


class CursorError(ValueError):
    """The cursor is malformed, or was issued for different filters."""


def filters_fingerprint(filters: RunFilter) -> str:
    """A short stable digest of the filters, independent of the page size."""
    payload: dict[str, Any] = {
        "case_id": filters.case_id,
        "statuses": sorted(filters.statuses),
        "engine_version": filters.engine_version,
        "data_mode": filters.data_mode,
        "created_after": filters.created_after.isoformat() if filters.created_after else None,
        "created_before": filters.created_before.isoformat() if filters.created_before else None,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=8).hexdigest()


def encode_cursor(cursor: RunCursor, filters: RunFilter) -> str:
    """The URL-safe token a client passes back to get the next page."""
    payload = {
        "v": _VERSION,
        "t": cursor.created_at.astimezone(UTC).isoformat(),
        "r": cursor.run_id,
        "f": filters_fingerprint(filters),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(token: str, filters: RunFilter) -> RunCursor:
    """The position a token names.

    Raises:
        CursorError: if the token is not one this API issued, or was issued for
            different filters.
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict) or payload.get("v") != _VERSION:
            raise CursorError("unrecognised cursor")
        created_at = datetime.fromisoformat(payload["t"])
        run_id = payload["r"]
        fingerprint = payload["f"]
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeError) as exc:
        if isinstance(exc, CursorError):
            raise
        raise CursorError("malformed cursor") from exc
    if created_at.tzinfo is None or not isinstance(run_id, str):
        raise CursorError("malformed cursor")
    if fingerprint != filters_fingerprint(filters):
        raise CursorError("this cursor was issued for different filters")
    return RunCursor(created_at=created_at.astimezone(UTC), run_id=run_id)
