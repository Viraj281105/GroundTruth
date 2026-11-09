from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.contracts.errors import ProvenanceError
from groundtruth.platform.audit import service
from groundtruth.platform.audit.service import AUDIT_ACTIONS, list_events, record_event
from groundtruth.platform.store.models import AuditEventRow


def _record(db: Session, **kw: Any) -> AuditEventRow:
    args: dict[str, Any] = {
        "action": "org.switch",
        "outcome": "success",
        "actor_user_id": "u1",
        "organization_id": "o1",
        "resource_type": "organization",
    }
    args.update(kw)
    return record_event(db, **args)


def test_record_event_persists_fields(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as db:
        row = _record(db, resource_id="o1", details={"k": 1})
        db.commit()
        got = db.execute(select(AuditEventRow)).scalar_one()
        assert got.id == row.id
        assert (got.action, got.outcome, got.actor_user_id) == ("org.switch", "success", "u1")
        assert got.organization_id == "o1"
        assert (got.resource_type, got.resource_id) == ("organization", "o1")
        assert got.details == {"k": 1}
        assert "authz.denied" in AUDIT_ACTIONS and len(AUDIT_ACTIONS) == 17


def test_audit_rows_cannot_be_updated(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as db:
        _record(db)
        db.commit()
        row = db.execute(select(AuditEventRow)).scalar_one()
        row.action = "tampered"
        with pytest.raises(ProvenanceError):
            db.commit()


def test_audit_rows_cannot_be_deleted(tenancy_sessions: sessionmaker[Session]) -> None:
    with tenancy_sessions() as db:
        _record(db)
        db.commit()
        db.delete(db.execute(select(AuditEventRow)).scalar_one())
        with pytest.raises(ProvenanceError):
            db.commit()


def test_list_events_paginates_newest_first(tenancy_sessions: sessionmaker[Session]) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    with tenancy_sessions() as db:
        for i in range(5):
            db.add(
                AuditEventRow(
                    id=f"id-{i}",
                    occurred_at=base + timedelta(seconds=i),
                    organization_id="o1",
                    action="org.switch",
                    resource_type="organization",
                    resource_id=str(i),
                    outcome="success",
                    details={},
                )
            )
        _record(db, organization_id="other")
        db.commit()
    with tenancy_sessions() as db:
        page1, cur = list_events(db, "o1", cursor=None, limit=2)
        assert [r.resource_id for r in page1] == ["4", "3"] and cur
        page2, cur = list_events(db, "o1", cursor=cur, limit=2)
        assert [r.resource_id for r in page2] == ["2", "1"] and cur
        page3, cur = list_events(db, "o1", cursor=cur, limit=2)
        assert [r.resource_id for r in page3] == ["0"] and cur is None


def test_denied_events_rate_limited(tenancy_sessions: sessionmaker[Session]) -> None:
    service._denied_last.clear()
    with tenancy_sessions() as db:
        for _ in range(5):
            _record(db, action="authz.denied", outcome="denied", actor_user_id="rl-user")
        db.commit()
        n = len(db.execute(select(AuditEventRow)).scalars().all())
    assert n == 1


def test_audit_failure_is_counted_not_raised(tenancy_sessions: sessionmaker[Session]) -> None:
    before = service.audit_failure_count()
    with tenancy_sessions() as db:
        row = _record(db, outcome="bogus")  # violates the outcome check constraint
        db.commit()
        assert db.execute(select(AuditEventRow)).first() is None
    assert row.action == "org.switch"
    assert service.audit_failure_count() == before + 1


def test_audit_cursor_is_url_safe_for_timezone_aware_timestamps() -> None:
    """PostgreSQL timestamps carry '+00:00'; a raw '+' in a query string decodes to a space."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import pytest

    from groundtruth.platform.audit.service import _cursor, _decode_cursor

    when = datetime(2026, 11, 9, 12, 30, 45, 123456, tzinfo=UTC)
    token = _cursor(SimpleNamespace(occurred_at=when, id="evt-1"))  # type: ignore[arg-type]
    assert not any(ch in token for ch in "+/= |:")
    assert _decode_cursor(token) == (when, "evt-1")
    for bad in ("garbage", "", "bm9wZQ", "MjAyNi0xMS0wOVQxMjozMDo0NSswMDowMA"):
        with pytest.raises(ValueError):
            _decode_cursor(bad)
