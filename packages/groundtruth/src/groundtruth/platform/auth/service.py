"""Account operations. Each takes an open SQLAlchemy session and commits nothing itself."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from groundtruth.platform.auth import passwords
from groundtruth.platform.auth.ratelimit import FailureLimiter
from groundtruth.platform.auth.sessions import revoke_user_sessions, utcnow
from groundtruth.platform.store.models import UserRow

ROLE_RANK: dict[str, int] = {"user": 1, "dev": 2, "admin": 3}
DEFAULT_ROLE = "user"

_CODE_STATUS = {
    "invalid_credentials": 401,
    "email_taken": 409,
    "weak_password": 422,
    "too_many_attempts": 429,
    "unauthenticated": 401,
    "forbidden": 403,
    "csrf_origin_rejected": 403,
    "registration_closed": 403,
    "user_not_found": 404,
    "last_admin": 409,
    "no_active_organization": 409,
    "not_found": 404,
    "conflict": 409,
    "invalid_boundary": 422,
    "invalid_grant": 422,
    "invalid_cursor": 422,
}


def auth_error(code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException:
    """An ``HTTPException`` in the API's ``detail: {code, message, hint}`` shape."""
    return HTTPException(
        status_code=_CODE_STATUS[code],
        detail={"code": code, "message": message, "hint": None},
        headers=headers,
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register(db: Session, email: str, password: str, *, now: datetime | None = None) -> UserRow:
    email = normalize_email(email)
    problem = passwords.check_policy(password, email)
    if problem is not None:
        raise auth_error("weak_password", problem)
    if db.execute(select(UserRow.id).where(UserRow.email == email)).first() is not None:
        raise auth_error("email_taken", "An account with that email already exists.")
    # Bootstrap: a self-registered user is admin while no active admin exists. (Counting users
    # instead would let a seeded demo account consume the bootstrap.)
    first = (
        db.execute(
            select(func.count())
            .select_from(UserRow)
            .where(UserRow.role == "admin", UserRow.is_active.is_(True))
        ).scalar_one()
        == 0
    )
    user = UserRow(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=passwords.hash_password(password),
        role="admin" if first else DEFAULT_ROLE,
        is_active=True,
        created_at=now or utcnow(),
        last_login_at=None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise auth_error("email_taken", "An account with that email already exists.") from exc
    return user


def authenticate(
    db: Session,
    email: str,
    password: str,
    *,
    client_ip: str,
    limiter: FailureLimiter,
    now: datetime | None = None,
) -> UserRow:
    """Verify credentials. Unknown email, wrong password and inactive account look the same."""
    email = normalize_email(email)
    key = (email, client_ip)
    wait = limiter.retry_after(key)
    if wait is not None:
        raise auth_error(
            "too_many_attempts",
            "Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    user = db.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
    if user is None:
        passwords.dummy_verify(password)
        ok = False
    else:
        ok = passwords.verify_password(password, user.password_hash) and user.is_active
    if not ok or user is None:
        limiter.record_failure(key)
        raise auth_error("invalid_credentials", "Incorrect email or password.")
    limiter.reset(key)
    user.last_login_at = now or utcnow()
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    return user


def change_password(
    db: Session, user: UserRow, current: str, new: str, *, keep_token: str | None
) -> None:
    if not passwords.verify_password(current, user.password_hash):
        raise auth_error("invalid_credentials", "Incorrect current password.")
    problem = passwords.check_policy(new, user.email)
    if problem is not None:
        raise auth_error("weak_password", problem)
    user.password_hash = passwords.hash_password(new)
    revoke_user_sessions(db, user.id, except_token=keep_token)


def list_users(db: Session) -> list[UserRow]:
    return list(db.execute(select(UserRow).order_by(UserRow.created_at, UserRow.email)).scalars())


def update_user(db: Session, user_id: str, *, role: str | None, is_active: bool | None) -> UserRow:
    user = db.get(UserRow, user_id)
    if user is None:
        raise auth_error("user_not_found", "No such user.")
    new_role = role if role is not None else user.role
    new_active = is_active if is_active is not None else user.is_active
    was_admin = user.role == "admin" and user.is_active
    stays_admin = new_role == "admin" and new_active
    if was_admin and not stays_admin:
        others = db.execute(
            select(func.count())
            .select_from(UserRow)
            .where(UserRow.role == "admin", UserRow.is_active.is_(True), UserRow.id != user.id)
        ).scalar_one()
        if others == 0:
            raise auth_error("last_admin", "There must be at least one active admin.")
    user.role = new_role
    user.is_active = new_active
    if not new_active:
        revoke_user_sessions(db, user.id)
    return user
