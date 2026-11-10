"""Structured logging setup.

Analytical runs are audit artefacts, so log records carry the case id and the
pipeline stage rather than free-form prose.

Context that belongs to a whole job (its run id, case id, worker) is set once with
:func:`log_context` and added to every record logged while it is active, by any
logger, including the engine's own. The engine stays unaware of jobs: the context
travels with the thread, not through function arguments.

In JSON output every line has ``run_id``, ``case_id`` and ``stage`` (#50): their value
outside an analysis is ``null``, so a log query can rely on the keys being there. A
process that configures logging may pass a ``redact`` function, applied to the message,
the exception and every text field before the line is written, so no credential reaches
a log (the platform passes ``groundtruth.platform.redaction.redact_secrets``; this module
imports nothing from the platform, so the engine can keep using it).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

ALWAYS_PRESENT: tuple[str, ...] = ("run_id", "case_id", "stage")
"""Written on every JSON line, as ``null`` when the line is not about an analysis."""

CONTEXT_FIELDS: tuple[str, ...] = (
    "run_id",
    "case_id",
    "stage",
    "request_id",
    "path",
    "worker_id",
    "attempt",
    "data_mode",
    "status",
    "estimator",
    "n_donors",
)
"""Structured fields copied into JSON output when a record carries them."""

_context: ContextVar[dict[str, Any] | None] = ContextVar("groundtruth_log_context", default=None)


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    """Add ``fields`` to every record logged in this thread until the block exits.

    Nested blocks add to (and may override) the outer context, so a job can set its
    identity once and each stage only its ``stage``. ``None`` values are ignored.
    A new thread starts with no context; pass :func:`current_log_context` to it.
    """
    merged = {**current_log_context(), **{k: v for k, v in fields.items() if v is not None}}
    token = _context.set(merged)
    try:
        yield
    finally:
        _context.reset(token)


def current_log_context() -> dict[str, Any]:
    """A copy of the context active in this thread."""
    return dict(_context.get() or {})


class ContextFilter(logging.Filter):
    """Copy the active :func:`log_context` onto each record a handler receives.

    Attached to handlers, not loggers, because a logger's filters do not see records
    propagated from its children. A field passed explicitly with ``extra=`` wins.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in current_log_context().items():
            if getattr(record, key, None) is None:
                setattr(record, key, value)
        return True


Redact = Callable[[str], str]
"""Removes credentials from a piece of text before it is logged."""


def _unchanged(text: str) -> str:
    return text


REDACTION_FAILED = "[unloggable: redaction failed]"


def _fail_closed(redact: Redact) -> Redact:
    """``redact``, but text it cannot process is withheld rather than written unredacted."""

    def safe(text: str) -> str:
        try:
            return redact(text)
        except Exception:
            return REDACTION_FAILED

    return safe


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON, every line with the same core keys."""

    def __init__(self, redact: Redact | None = None) -> None:
        super().__init__()
        self._redact = _fail_closed(redact) if redact else _unchanged

    def format(self, record: logging.LogRecord) -> str:
        redact = self._redact
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key in CONTEXT_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact(value) if isinstance(value, str) else value
            elif key in ALWAYS_PRESENT:
                payload[key] = None
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        elif record.exc_text:
            payload["exception"] = redact(record.exc_text)
        return json.dumps(payload, default=str)


class RedactingFormatter(logging.Formatter):
    """The plain text format, with credentials removed from the finished line."""

    def __init__(self, fmt: str, redact: Redact | None = None) -> None:
        super().__init__(fmt)
        self._redact = _fail_closed(redact) if redact else _unchanged

    def format(self, record: logging.LogRecord) -> str:
        return self._redact(super().format(record))


PLAIN_FORMAT = "%(levelname)-8s %(name)s: %(message)s"


def configure_logging(
    level: str = "INFO", *, json_output: bool = False, redact: Redact | None = None
) -> None:
    """Configure the root logger once, idempotently.

    Args:
        level: The root level.
        json_output: One JSON object per line (deployments) instead of plain text.
        redact: Applied to everything a line contains before it is written.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())
    for existing in list(root.handlers):
        root.removeHandler(existing)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter(redact) if json_output else RedactingFormatter(PLAIN_FORMAT, redact)
    )
    handler.addFilter(ContextFilter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""
    return logging.getLogger(f"groundtruth.{name}")
