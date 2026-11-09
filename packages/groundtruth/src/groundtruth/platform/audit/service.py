"""Record and read audit events.

``record_event`` adds and *flushes* the row inside the caller's session (in a savepoint);
it never commits, so the caller's transaction decides whether the event persists. An audit
failure is logged and counted, never raised into the request.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import Request
from sqlalchemy.orm import Session

from groundtruth.platform.store.models import AuditEventRow

logger = logging.getLogger(__name__)

AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "auth.login",
        "auth.login_failed",
        "auth.logout",
        "auth.register",
        "auth.password_change",
        "org.member_add",
        "org.member_remove",
        "org.member_role",
        "org.switch",
        "project.create",
        "project.update",
        "project.grant",
        "project.revoke",
        "run.start",
        "run.cancel",
        "export.download",
        "authz.denied",
    }
)

# No metrics backend exists in observability/, so the counter is a module-level integer
# (name kept as the metric name to export later). Per process.
groundtruth_audit_failures_total = 0
_counter_lock = threading.Lock()

# Denied events are throttled to one per (user, action) per window, per process, so a
# client hammering a forbidden endpoint cannot flood the log.
DENIED_WINDOW_SECONDS = 1.0
_denied_last: dict[tuple[str | None, str], float] = {}
_denied_lock = threading.Lock()

Outcome = Literal["success", "denied", "error"]


def note_audit_failure(action: str) -> None:
    """Log and count an audit write that failed outside ``record_event``."""
    _count_failure()
    logger.exception("audit event %s could not be recorded", action)


def audit_failure_count() -> int:
    return groundtruth_audit_failures_total


def _count_failure() -> None:
    global groundtruth_audit_failures_total
    with _counter_lock:
        groundtruth_audit_failures_total += 1


def audit_throttled(actor: str | None, action: str) -> bool:
    """True if an event for ``(actor, action)`` was already allowed within the window.

    Callers pass e.g. a user id or client ip. The first call per window returns False.
    """
    now = time.monotonic()
    key = (actor, action)
    with _denied_lock:
        last = _denied_last.get(key)
        if last is not None and now - last < DENIED_WINDOW_SECONDS:
            return True
        _denied_last[key] = now
        return False


def record_event(
    db: Session,
    *,
    action: str,
    outcome: Outcome,
    actor_user_id: str | None,
    organization_id: str | None,
    resource_type: str,
    resource_id: str | None = None,
    request: Request | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditEventRow:
    """Add an audit row to ``db`` and flush it. Never raises; returns the row.

    On failure (or when a denied event is rate limited) the returned row is transient.
    """
    ip = None
    user_agent = None
    if request is not None:
        ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
    row = AuditEventRow(
        id=str(uuid.uuid4()),
        occurred_at=datetime.now(UTC),
        actor_user_id=actor_user_id,
        organization_id=organization_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        ip=ip,
        user_agent=user_agent[:300] if user_agent else None,
        details=dict(details) if details else {},
    )
    if action == "authz.denied" and audit_throttled(actor_user_id, action):
        return row
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except Exception:
        _count_failure()
        logger.exception("audit event %s could not be recorded", action)
    return row


def _cursor(row: AuditEventRow) -> str:
    """Opaque, URL-safe position of ``row``.

    The raw ISO timestamp of a timezone-aware value (PostgreSQL) contains ``+00:00``, and a ``+``
    in a query string decodes to a space, which silently broke the next-page request for any
    client that passes the cursor through unencoded. Base64url has no such characters.
    """
    raw = f"{row.occurred_at.isoformat()}|{row.id}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(token: str) -> tuple[datetime, str]:
    """The (occurred_at, id) a cursor names. Raises ``ValueError`` for anything else."""
    try:
        padded = token + "=" * (-len(token) % 4)
        text = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("malformed cursor") from exc
    ts_text, sep, last_id = text.partition("|")
    if not sep or not last_id:
        raise ValueError("malformed cursor")
    return datetime.fromisoformat(ts_text), last_id


def list_events(
    db: Session, organization_id: str, *, cursor: str | None, limit: int = 50
) -> tuple[list[AuditEventRow], str | None]:
    """Newest first. The cursor is ``occurred_at|id`` of the last row of the previous page."""
    stmt = sa.select(AuditEventRow).where(AuditEventRow.organization_id == organization_id)
    if cursor:
        ts, last_id = _decode_cursor(cursor)
        stmt = stmt.where(
            sa.or_(
                AuditEventRow.occurred_at < ts,
                sa.and_(AuditEventRow.occurred_at == ts, AuditEventRow.id < last_id),
            )
        )
    stmt = stmt.order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.id.desc()).limit(limit + 1)
    rows = list(db.execute(stmt).scalars())
    if len(rows) > limit:
        rows = rows[:limit]
        return rows, _cursor(rows[-1])
    return rows, None


ACTIVITY_PREFIXES: tuple[str, ...] = ("project.", "run.", "export.")
"""The only event families the member-visible activity feed may show (no auth, org or authz)."""
_ACTIVITY_SCAN = 500


def list_activity(
    db: Session,
    organization_id: str,
    *,
    accessible_project_ids: frozenset[str],
    owned_project_ids: frozenset[str],
    limit: int = 20,
) -> list[AuditEventRow]:
    """Newest first: successful ``project.*``/``run.*``/``export.*`` events the org may see.

    Events attributable to the viewing org (``organization_id``) on a project it can still
    access, plus project-resource events (``resource_type="project"``) by any org on projects
    it owns. ``run.*`` events written with ``resource_type="run"`` by a grantee org are NOT
    visible to the owner.
    An event on a project the org cannot (or can no longer) access is never shown. A run event
    names its project in ``details.project_id``; one without it is shown to its own org only.
    Scans the newest ``_ACTIVITY_SCAN`` candidate rows; the feed is a recent-activity view, not
    the audit log.
    """
    stmt = (
        sa.select(AuditEventRow)
        .where(
            AuditEventRow.outcome == "success",
            sa.or_(
                *(AuditEventRow.action.startswith(p, autoescape=True) for p in ACTIVITY_PREFIXES)
            ),
            sa.or_(
                AuditEventRow.organization_id == organization_id,
                sa.and_(
                    AuditEventRow.resource_type == "project",
                    AuditEventRow.resource_id.in_(owned_project_ids or {""}),
                ),
            ),
        )
        .order_by(AuditEventRow.occurred_at.desc(), AuditEventRow.id.desc())
        .limit(_ACTIVITY_SCAN)
    )
    out: list[AuditEventRow] = []
    for row in db.execute(stmt).scalars():
        own = row.organization_id == organization_id
        if row.resource_type == "project":
            allowed = row.resource_id in accessible_project_ids
        else:
            pid = row.details.get("project_id") if isinstance(row.details, dict) else None
            allowed = own and (pid is None or pid in accessible_project_ids)
        if allowed:
            out.append(row)
            if len(out) >= limit:
                break
    return out
