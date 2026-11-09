"""Sign-up, sign-in, sign-out and account management (see docs/security/auth.md).

Responses carry the user's own fields only: never a password, a hash or a session token.
The session token lives solely in the ``gt_session`` HttpOnly cookie.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.orgs import org_view
from groundtruth.platform.api.rate_limiting import RateLimiter
from groundtruth.platform.api.schemas import OrgView
from groundtruth.platform.audit.service import audit_throttled, note_audit_failure, record_event
from groundtruth.platform.auth import service
from groundtruth.platform.auth.deps import (
    Role,
    Sessions,
    UserView,
    lookup_user,
    require_role,
    resolve_sessions,
    session_token,
    to_view,
)
from groundtruth.platform.auth.ratelimit import login_limiter
from groundtruth.platform.auth.sessions import (
    COOKIE_NAME,
    create_session,
    hash_token,
    revoke_token,
)
from groundtruth.platform.config import get_settings
from groundtruth.platform.store.models import SessionRow, UserRow
from groundtruth.platform.tenancy.service import list_user_memberships, set_active_org

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

_ERRORS = {
    401: {"model": ApiErrorBody, "description": "Not signed in, or wrong credentials."},
    403: {"model": ApiErrorBody, "description": "Not allowed."},
    503: {"model": ApiErrorBody, "description": "No database is configured."},
}


class RegisterRequest(BaseModel):
    email: str = Field(max_length=254, pattern=_EMAIL_PATTERN)
    password: str = Field(max_length=1024)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class UpdateUserRequest(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class MeResponse(BaseModel):
    auth_required: bool
    registration_open: bool
    user: UserView | None
    organizations: list[OrgView] = Field(default_factory=list)
    active_organization: OrgView | None = None


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.auth_session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        path="/",
    )


def _client_ip(request: Request) -> str:
    # The direct peer only. X-Forwarded-For is client-controlled and is not trusted.
    return request.client.host if request.client else "unknown"


def _audit_failed_login(sessions: sessionmaker[Session], request: Request, code: str) -> None:
    """Record a rejected sign-in in its own transaction; never alters the response.

    Throttled to one write per second per client ip so a lockout cannot flood the log.
    """
    if audit_throttled(f"ip:{_client_ip(request)}", f"auth.login_failed:{code}"):
        return
    try:
        with sessions() as db:
            record_event(
                db,
                action="auth.login_failed",
                outcome="denied",
                actor_user_id=None,
                organization_id=None,
                resource_type="session",
                request=request,
                details={"code": code},
            )
            db.commit()
    except Exception:
        note_audit_failure("auth.login_failed")


def _current(sessions: sessionmaker[Session], request: Request) -> UserView:
    user = lookup_user(sessions, session_token(request))
    if user is None:
        raise service.auth_error("unauthenticated", "Sign in to continue.")
    return user


@router.post(
    "/register",
    response_model=UserView,
    status_code=201,
    summary="Create an account",
    responses={
        403: _ERRORS[403],
        429: {"model": ApiErrorBody, "description": "Rate limit exceeded."},
        503: _ERRORS[503],
    },
    dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope_prefix="auth"))],
)
def register(
    body: RegisterRequest, request: Request, response: Response, sessions: Sessions
) -> UserView:
    """Create an account and sign in. The first account becomes `admin`; later ones `user`.

    When registration is closed, only a signed-in admin may create accounts, and that
    admin stays signed in as themselves.
    """
    by_admin = False
    if not get_settings().auth_allow_registration:
        caller = lookup_user(sessions, session_token(request))
        if caller is None or caller.role != "admin":
            raise service.auth_error("registration_closed", "Registration is closed.")
        by_admin = True
    with sessions() as db:
        user = service.register(db, body.email, body.password)
        token = None
        if not by_admin:
            token = create_session(
                db,
                user,
                days=get_settings().auth_session_days,
                user_agent=request.headers.get("user-agent"),
            )
        record_event(
            db,
            action="auth.register",
            outcome="success",
            actor_user_id=user.id,
            organization_id=None,
            resource_type="user",
            resource_id=user.id,
            request=request,
            details={"by_admin": by_admin},
        )
        db.commit()
        view = to_view(user)
    if token is not None:
        _set_cookie(response, token)
    return view


@router.post(
    "/login",
    response_model=UserView,
    summary="Sign in",
    responses={
        401: _ERRORS[401],
        429: {
            "model": ApiErrorBody,
            "description": "Too many failed attempts or rate limit exceeded.",
        },
        503: _ERRORS[503],
    },
    dependencies=[Depends(RateLimiter(limit=10, window_seconds=60, scope_prefix="auth"))],
)
def login(body: LoginRequest, request: Request, response: Response, sessions: Sessions) -> UserView:
    with sessions() as db:
        try:
            user = service.authenticate(
                db, body.email, body.password, client_ip=_client_ip(request), limiter=login_limiter
            )
        except HTTPException as exc:
            detail = exc.detail
            code = detail.get("code", "error") if isinstance(detail, dict) else "error"
            _audit_failed_login(sessions, request, str(code))
            raise
        old = session_token(request)
        if old:
            revoke_token(db, old)
        token = create_session(
            db,
            user,
            days=get_settings().auth_session_days,
            user_agent=request.headers.get("user-agent"),
        )
        record_event(
            db,
            action="auth.login",
            outcome="success",
            actor_user_id=user.id,
            organization_id=None,
            resource_type="session",
            request=request,
        )
        db.commit()
        view = to_view(user)
    _set_cookie(response, token)
    return view


@router.post(
    "/logout",
    status_code=204,
    summary="Sign out",
    responses={503: _ERRORS[503]},
)
def logout(request: Request, sessions: Sessions) -> Response:
    """Revoke the session server-side and clear the cookie. Safe to repeat."""
    token = session_token(request)
    if token:
        actor = lookup_user(sessions, token)
        with sessions() as db:
            revoke_token(db, token)
            if actor is not None:
                record_event(
                    db,
                    action="auth.logout",
                    outcome="success",
                    actor_user_id=actor.id,
                    organization_id=None,
                    resource_type="session",
                    request=request,
                )
            db.commit()
    response = Response(status_code=204)
    _clear_cookie(response)
    return response


@router.get(
    "/me", response_model=MeResponse, summary="The current session", responses={503: _ERRORS[503]}
)
def me(request: Request) -> MeResponse:
    settings = get_settings()
    try:
        sessions = resolve_sessions(request)
    except HTTPException:
        if settings.auth_required:
            raise
        # Auth is off and there is no database: report that, rather than an error.
        return MeResponse(auth_required=False, registration_open=False, user=None)
    token = session_token(request)
    user = lookup_user(sessions, token)
    organizations: list[OrgView] = []
    active: OrgView | None = None
    if user is not None and token:
        with sessions() as db:
            pairs = list_user_memberships(db, user.id)
            organizations = [org_view(o, m) for o, m in pairs]
            row = db.execute(
                select(SessionRow).where(SessionRow.token_hash == hash_token(token))
            ).scalar_one_or_none()
            if row is not None:
                active_id = row.active_organization_id
                if active_id is None and len(pairs) == 1:
                    # Same rule as authz.get_access_context: one membership is the default.
                    active_id = pairs[0][0].id
                    set_active_org(db, hash_token(token), active_id)
                    db.commit()
                active = next((v for v in organizations if v.id == active_id), None)
    return MeResponse(
        auth_required=settings.auth_required,
        registration_open=settings.auth_allow_registration,
        user=user,
        organizations=organizations,
        active_organization=active,
    )


@router.post(
    "/change-password",
    status_code=204,
    summary="Change your password",
    responses={401: _ERRORS[401], 503: _ERRORS[503]},
)
def change_password(body: ChangePasswordRequest, request: Request, sessions: Sessions) -> Response:
    """Other sessions of this account are revoked; this one stays signed in."""
    token = session_token(request)
    user_view = _current(sessions, request)
    with sessions() as db:
        user = db.get(UserRow, user_view.id)
        assert user is not None
        service.change_password(
            db, user, body.current_password, body.new_password, keep_token=token
        )
        record_event(
            db,
            action="auth.password_change",
            outcome="success",
            actor_user_id=user.id,
            organization_id=None,
            resource_type="user",
            resource_id=user.id,
            request=request,
        )
        db.commit()
    return Response(status_code=204)


@router.get(
    "/users",
    response_model=list[UserView],
    summary="List accounts (admin)",
    dependencies=[Depends(require_role("admin", always=True))],
    responses={401: _ERRORS[401], 403: _ERRORS[403], 503: _ERRORS[503]},
)
def list_users(sessions: Sessions) -> list[UserView]:
    with sessions() as db:
        return [to_view(u) for u in service.list_users(db)]


@router.patch(
    "/users/{user_id}",
    response_model=UserView,
    summary="Change an account's role or active flag (admin)",
    dependencies=[Depends(require_role("admin", always=True))],
    responses={
        401: _ERRORS[401],
        403: _ERRORS[403],
        404: {"model": ApiErrorBody, "description": "No such user."},
        409: {"model": ApiErrorBody, "description": "Would leave no active admin."},
        503: _ERRORS[503],
    },
)
def update_user(user_id: str, body: UpdateUserRequest, sessions: Sessions) -> UserView:
    with sessions() as db:
        user = service.update_user(db, user_id, role=body.role, is_active=body.is_active)
        db.commit()
        return to_view(user)
