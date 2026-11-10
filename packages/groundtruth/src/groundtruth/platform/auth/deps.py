"""FastAPI dependencies: who is calling, and the role gate.

``require_role`` does nothing when ``AUTH_REQUIRED`` is false, and never touches the
store then, so deployments and tests without a database behave as they did before auth.
When auth is required and no store exists the answer is 503, never "allow".
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.platform.api.dependencies import get_store
from groundtruth.platform.auth.service import ROLE_RANK, auth_error
from groundtruth.platform.auth.sessions import COOKIE_NAME, resolve_session
from groundtruth.platform.config import get_settings
from groundtruth.platform.store.interface import EvidenceStore
from groundtruth.platform.store.models import UserRow

Role = Literal["user", "dev", "admin"]


class UserView(BaseModel):
    """A user account."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    id: str
    """User id."""
    email: str
    """Email address; also the sign-in name."""
    role: Role
    """Platform role: `user`, `dev` or `admin`. Organization roles are separate."""
    is_active: bool
    """False for a deactivated account, which cannot sign in."""
    created_at: datetime
    """When the account was created (UTC)."""
    last_login_at: datetime | None = None
    """When the user last signed in (UTC)."""


def to_view(user: UserRow) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def get_auth_sessions(
    store: Annotated[EvidenceStore, Depends(get_store)],
) -> sessionmaker[Session]:
    """The database session factory shared with the evidence store.

    Raises:
        HTTPException: 503 ``store_not_configured`` / ``store_unavailable``.
    """
    factory = getattr(store, "_sessions", None)
    if factory is None:  # a store without SQL sessions cannot hold accounts
        from groundtruth.platform.api.errors import ApiErrorCode, api_error

        raise api_error(ApiErrorCode.STORE_NOT_CONFIGURED, "Accounts need a SQL database.")
    return factory  # type: ignore[no-any-return]


Sessions = Annotated[sessionmaker[Session], Depends(get_auth_sessions)]


def resolve_sessions(request: Request) -> sessionmaker[Session]:
    """``get_auth_sessions``, honouring ``app.dependency_overrides`` (used by tests)."""
    overrides = request.app.dependency_overrides
    store = overrides.get(get_store, get_store)()
    return get_auth_sessions(store)


def session_token(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME) or None


def lookup_user(sessions: sessionmaker[Session], token: str | None) -> UserView | None:
    if not token:
        return None
    with sessions() as db:
        user = resolve_session(db, token)
        return to_view(user) if user is not None else None


def require_role(minimum: Role, *, always: bool = False) -> Callable[[Request], UserView | None]:
    """A dependency requiring a signed-in user of at least ``minimum`` rank.

    ``always=True`` enforces even when ``AUTH_REQUIRED`` is false (account management).
    """

    def dependency(request: Request) -> UserView | None:
        if not always and not get_settings().auth_required:
            return None
        sessions = resolve_sessions(request)  # 503 if there is no store
        user = lookup_user(sessions, session_token(request))
        if user is None:
            raise auth_error("unauthenticated", "Sign in to continue.")
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise auth_error("forbidden", "Your account is not allowed to do this.")
        return user

    dependency.__gt_authz__ = "role"  # type: ignore[attr-defined]
    return dependency
