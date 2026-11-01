"""Structured logging setup.

Analytical runs are audit artefacts, so log records carry the case id and the
pipeline stage rather than free-form prose.

Context that belongs to a whole job (its run id, case id, worker) is set once with
:func:`log_context` and added to every record logged while it is active, by any
logger, including the engine's own. The engine stays unaware of jobs: the context
travels with the thread, not through function arguments.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

CONTEXT_FIELDS: tuple[str, ...] = (
    "run_id",
    "case_id",
    "stage",
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


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in CONTEXT_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure the root logger once, idempotently."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for existing in list(root.handlers):
        root.removeHandler(existing)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter()
        if json_output
        else logging.Formatter("%(levelname)-8s %(name)s: %(message)s")
    )
    handler.addFilter(ContextFilter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""
    return logging.getLogger(f"groundtruth.{name}")
