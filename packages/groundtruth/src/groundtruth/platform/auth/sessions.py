"""Opaque session tokens. Only the SHA-256 of a token is ever stored."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from groundtruth.platform.store.models import SessionRow, UserRow

COOKIE_NAME = "gt_session"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they were written as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def create_session(
    db: Session, user: UserRow, *, days: int, user_agent: str | None, now: datetime | None = None
) -> str:
    """Insert a session for ``user`` and return the raw token (never stored)."""
    now = now or utcnow()
    token = new_token()
    db.add(
        SessionRow(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + timedelta(days=days),
            revoked_at=None,
            user_agent=user_agent[:300] if user_agent else None,
        )
    )
    return token


def resolve_session(db: Session, token: str, *, now: datetime | None = None) -> UserRow | None:
    """The active user a live session belongs to, else ``None``."""
    now = now or utcnow()
    row = db.execute(
        select(SessionRow, UserRow)
        .join(UserRow, UserRow.id == SessionRow.user_id)
        .where(SessionRow.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None
    session_row, user = row
    if session_row.revoked_at is not None or as_utc(session_row.expires_at) <= now:
        return None
    if not user.is_active:
        return None
    return user


def revoke_token(db: Session, token: str, *, now: datetime | None = None) -> None:
    db.execute(
        update(SessionRow)
        .where(SessionRow.token_hash == hash_token(token), SessionRow.revoked_at.is_(None))
        .values(revoked_at=now or utcnow())
    )


def revoke_user_sessions(
    db: Session, user_id: str, *, except_token: str | None = None, now: datetime | None = None
) -> None:
    stmt = update(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
    if except_token is not None:
        stmt = stmt.where(SessionRow.token_hash != hash_token(except_token))
    db.execute(stmt.values(revoked_at=now or utcnow()))
