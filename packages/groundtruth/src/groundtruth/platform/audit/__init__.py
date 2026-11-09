"""Append-only audit log: the immutability guard lives here, the service in ``service``.

Importing this package registers a ``before_flush`` listener that rejects any update or
delete of an ``AuditEventRow``. ``store/models.py`` imports it, so the guard is active
whenever the schema is. This module must not import ``store.models`` at load time (that
would be circular); the guard resolves the model lazily when a flush happens.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from groundtruth.contracts.errors import ProvenanceError


def _reject_audit_mutation(session: Session, flush_context: Any, instances: Any) -> None:
    from groundtruth.platform.store.models import AuditEventRow

    for obj in session.deleted:
        if isinstance(obj, AuditEventRow):
            raise ProvenanceError("audit_events is append-only: rows cannot be deleted.")
    for obj in session.dirty:
        if isinstance(obj, AuditEventRow) and session.is_modified(obj):
            raise ProvenanceError("audit_events is append-only: rows cannot be modified.")


if not event.contains(Session, "before_flush", _reject_audit_mutation):
    event.listen(Session, "before_flush", _reject_audit_mutation)
