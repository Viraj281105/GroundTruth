"""Auth routes write audit events (kept here to reuse the auth client fixtures)."""

from __future__ import annotations

from typing import Any

from authhelpers import ORIGIN, PASSWORD, login, register
from sqlalchemy import select

from groundtruth.platform.store.models import AuditEventRow


def test_login_and_failed_login_are_audited(client: Any, sessions: Any, _fast_scrypt: Any) -> None:
    assert register(client, "a@example.org").status_code == 201
    assert login(client, "a@example.org", "wrong password!!").status_code == 401
    assert login(client, "a@example.org", PASSWORD).status_code == 200
    client.post("/auth/logout", headers={"Origin": ORIGIN})
    with sessions() as db:
        rows = db.execute(select(AuditEventRow).order_by(AuditEventRow.occurred_at)).scalars().all()
    actions = [r.action for r in rows]
    assert "auth.register" in actions and "auth.login_failed" in actions
    assert "auth.login" in actions and "auth.logout" in actions
    failed = next(r for r in rows if r.action == "auth.login_failed")
    assert failed.outcome == "denied" and failed.actor_user_id is None
    assert failed.details == {"code": "invalid_credentials"}


def test_failed_login_audit_is_throttled_per_client(
    client: Any, sessions: Any, _fast_scrypt: Any
) -> None:
    from groundtruth.platform.audit import service

    service._denied_last.clear()
    assert register(client, "b@example.org").status_code == 201
    codes = [login(client, "b@example.org", "wrong password!!").status_code for _ in range(10)]
    assert codes[:5] == [401] * 5 and 429 in codes  # responses unchanged by auditing
    with sessions() as db:
        rows = [
            r
            for r in db.execute(select(AuditEventRow)).scalars()
            if r.action == "auth.login_failed"
        ]
    by_code = sorted(r.details["code"] for r in rows)
    assert by_code == ["invalid_credentials", "too_many_attempts"]  # one each, total == 2
    assert len(rows) == 2


def test_note_audit_failure_counts_and_logs(caplog: Any) -> None:
    from groundtruth.platform.audit import service

    before = service.audit_failure_count()
    with caplog.at_level("ERROR"):
        service.note_audit_failure("auth.login_failed")
    assert service.audit_failure_count() == before + 1
    assert "auth.login_failed" in caplog.text
