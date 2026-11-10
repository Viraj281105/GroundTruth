"""Organizations, memberships and the active-organization switch (design spec section 4).

``GET /orgs``, ``POST /orgs`` and ``POST /orgs/active`` need only a signed-in user, because a
user may have no organization yet or several. Member routes need the path slug to be the
caller's active organization and a role that may manage members.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.platform.api.errors import ApiErrorBody
from groundtruth.platform.api.schemas import MemberView, OrgView
from groundtruth.platform.audit.service import record_event
from groundtruth.platform.auth.authz import AccessContext, Action, require_org_action
from groundtruth.platform.auth.deps import UserView, require_role, resolve_sessions, session_token
from groundtruth.platform.auth.service import auth_error
from groundtruth.platform.auth.sessions import hash_token
from groundtruth.platform.store.models import MembershipRow, OrganizationRow, UserRow
from groundtruth.platform.tenancy import service
from groundtruth.platform.tenancy.service import (
    MemberRole,
    TenancyConflictError,
    TenancyForbiddenError,
)

router = APIRouter(prefix="/orgs", tags=["organizations"])

_ERRORS = {
    401: {"model": ApiErrorBody, "description": "Not signed in."},
    403: {"model": ApiErrorBody, "description": "Your role does not allow this."},
    404: {"model": ApiErrorBody, "description": "Unknown organization or user."},
    409: {"model": ApiErrorBody, "description": "Would break an organization invariant."},
    503: {"model": ApiErrorBody, "description": "No database is configured."},
}

Caller = Annotated[UserView | None, Depends(require_role("user", always=True))]
Manager = Annotated[AccessContext, Depends(require_org_action(Action.MANAGE_MEMBERS))]


class CreateOrgRequest(BaseModel):
    """A new organization; you become its owner."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    name: str = Field(min_length=1, max_length=200)
    """Organization name."""
    type: Literal["ngo", "funder", "auditor", "government"]
    """ngo, funder, auditor or government."""


class SwitchOrgRequest(BaseModel):
    """Make another of your organizations the active one."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    slug: str = Field(min_length=1, max_length=100)
    """Slug of the organization."""


class AddMemberRequest(BaseModel):
    """Add an existing user to the organization."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    email: str = Field(max_length=254)
    """The user's email address."""
    role: MemberRole
    """Their role: admin, member or viewer."""


class SetRoleRequest(BaseModel):
    """Change a member's role."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    role: MemberRole
    """The new role."""


def org_view(org: OrganizationRow, member: MembershipRow) -> OrgView:
    return OrgView(
        id=org.id,
        slug=org.slug,
        name=org.name,
        type=org.type,  # type: ignore[arg-type]
        role=member.role,  # type: ignore[arg-type]
    )


def member_view(member: MembershipRow, user: UserRow) -> MemberView:
    return MemberView(
        user_id=user.id,
        email=user.email,
        role=member.role,  # type: ignore[arg-type]
        created_at=member.created_at,
    )


def _caller(user: UserView | None) -> UserView:
    assert user is not None  # always=True enforces a session
    return user


def _conflict(exc: TenancyConflictError) -> HTTPException:
    return auth_error("conflict", str(exc))


def _audit(
    db: Session,
    request: Request,
    *,
    action: str,
    actor: str,
    org_id: str,
    resource_type: str,
    resource_id: str | None,
    details: dict[str, str] | None = None,
) -> None:
    record_event(
        db,
        action=action,
        outcome="success",
        actor_user_id=actor,
        organization_id=org_id,
        resource_type=resource_type,
        resource_id=resource_id,
        request=request,
        details=details,
    )


@router.get(
    "",
    response_model=list[OrgView],
    summary="Organizations you belong to",
    responses={401: _ERRORS[401], 503: _ERRORS[503]},
)
def list_orgs(request: Request, user: Caller) -> list[OrgView]:
    """Every organization your account belongs to, with your role in each. Needs sign-in but no
    active organization."""
    me = _caller(user)
    with resolve_sessions(request)() as db:
        return [org_view(o, m) for o, m in service.list_user_memberships(db, me.id)]


@router.post(
    "",
    response_model=OrgView,
    status_code=201,
    summary="Create an organization (you become its owner)",
    responses={401: _ERRORS[401], 503: _ERRORS[503]},
)
def create_org(body: CreateOrgRequest, request: Request, user: Caller) -> OrgView:
    """Creates an organization of the given type, with you as its owner. Audited (`org.create`)."""
    me = _caller(user)
    with resolve_sessions(request)() as db:
        org = service.create_org(db, name=body.name, type=body.type, creator_user_id=me.id)
        member = service.get_membership(db, org.id, me.id)
        assert member is not None
        _audit(
            db,
            request,
            action="org.create",
            actor=me.id,
            org_id=org.id,
            resource_type="organization",
            resource_id=org.id,
            details={"type": org.type},
        )
        db.commit()
        return org_view(org, member)


@router.post(
    "/active",
    response_model=OrgView,
    summary="Choose the organization you are acting for",
    responses={401: _ERRORS[401], 404: _ERRORS[404], 503: _ERRORS[503]},
)
def switch_org(body: SwitchOrgRequest, request: Request, user: Caller) -> OrgView:
    """A slug you are not a member of answers 404, exactly like an unknown slug."""
    me = _caller(user)
    token = session_token(request)
    if not token:
        raise auth_error("unauthenticated", "Sign in to continue.")
    with resolve_sessions(request)() as db:
        match = next(
            ((o, m) for o, m in service.list_user_memberships(db, me.id) if o.slug == body.slug),
            None,
        )
        if match is None:
            raise auth_error("not_found", "Organization not found.")
        org, member = match
        service.set_active_org(db, hash_token(token), org.id)
        _audit(
            db,
            request,
            action="org.switch",
            actor=me.id,
            org_id=org.id,
            resource_type="organization",
            resource_id=org.id,
        )
        db.commit()
        return org_view(org, member)


@router.get(
    "/{slug}/members",
    response_model=list[MemberView],
    summary="List members of the active organization",
    responses={401: _ERRORS[401], 403: _ERRORS[403], 404: _ERRORS[404], 503: _ERRORS[503]},
)
def list_members(request: Request, ctx: Manager) -> list[MemberView]:
    """Members of the organization named by `slug`, which must be your active organization (404
    otherwise). Needs a role that may manage members (403 otherwise)."""
    with resolve_sessions(request)() as db:
        return [member_view(m, u) for m, u in service.list_members(db, ctx.org_id)]


@router.post(
    "/{slug}/members",
    response_model=MemberView,
    status_code=201,
    summary="Add an existing account to the active organization",
    responses={
        401: _ERRORS[401],
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        503: _ERRORS[503],
    },
)
def add_member(body: AddMemberRequest, request: Request, ctx: Manager) -> MemberView:
    """Adds an existing account, found by email, with a role. No such account is 404
    `user_not_found`; a change your role may not make is 403 `forbidden`; a change that breaks a
    membership rule (e.g. an existing member) is 409 `conflict` with the reason. `slug` must be
    your active organization. Audited (`org.member_add`)."""
    with resolve_sessions(request)() as db:
        try:
            member = service.add_member(
                db, ctx.org_id, email=body.email, role=body.role, actor_role=ctx.role
            )
        except DataUnavailableError as exc:
            raise auth_error("user_not_found", "No account with that email.") from exc
        except TenancyForbiddenError as exc:
            raise auth_error("forbidden", str(exc)) from exc
        except TenancyConflictError as exc:
            raise _conflict(exc) from exc
        user = db.execute(select(UserRow).where(UserRow.id == member.user_id)).scalar_one()
        _audit(
            db,
            request,
            action="org.member_add",
            actor=ctx.user_id,
            org_id=ctx.org_id,
            resource_type="membership",
            resource_id=member.id,
            details={"user_id": user.id, "role": member.role},
        )
        db.commit()
        return member_view(member, user)


@router.patch(
    "/{slug}/members/{user_id}",
    response_model=MemberView,
    summary="Change a member's role",
    responses={
        401: _ERRORS[401],
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        503: _ERRORS[503],
    },
)
def set_role(user_id: str, body: SetRoleRequest, request: Request, ctx: Manager) -> MemberView:
    """Changes a member's role. Not a member is 404 `user_not_found`; a change your role may not
    make is 403 `forbidden`; a change that breaks a membership rule is 409 `conflict` with the
    reason. Audited (`org.member_role`)."""
    with resolve_sessions(request)() as db:
        try:
            member = service.set_member_role(
                db, ctx.org_id, user_id, body.role, actor_role=ctx.role
            )
        except DataUnavailableError as exc:
            raise auth_error("user_not_found", "Not a member of this organization.") from exc
        except TenancyForbiddenError as exc:
            raise auth_error("forbidden", str(exc)) from exc
        except TenancyConflictError as exc:
            raise _conflict(exc) from exc
        user = db.execute(select(UserRow).where(UserRow.id == user_id)).scalar_one()
        _audit(
            db,
            request,
            action="org.member_role",
            actor=ctx.user_id,
            org_id=ctx.org_id,
            resource_type="membership",
            resource_id=member.id,
            details={"user_id": user_id, "role": body.role},
        )
        db.commit()
        return member_view(member, user)


@router.delete(
    "/{slug}/members/{user_id}",
    status_code=204,
    summary="Remove a member",
    responses={
        401: _ERRORS[401],
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        503: _ERRORS[503],
    },
)
def remove_member(user_id: str, request: Request, ctx: Manager) -> Response:
    """Removes a member. Not a member is 404 `user_not_found`; a removal your role may not make is
    403 `forbidden`; one that breaks a membership rule is 409 `conflict` with the reason. Answers
    204 with no body. Audited (`org.member_remove`)."""
    with resolve_sessions(request)() as db:
        member = service.get_membership(db, ctx.org_id, user_id)
        member_id = member.id if member is not None else None
        try:
            service.remove_member(db, ctx.org_id, user_id, actor_role=ctx.role)
        except DataUnavailableError as exc:
            raise auth_error("user_not_found", "Not a member of this organization.") from exc
        except TenancyForbiddenError as exc:
            raise auth_error("forbidden", str(exc)) from exc
        except TenancyConflictError as exc:
            raise _conflict(exc) from exc
        _audit(
            db,
            request,
            action="org.member_remove",
            actor=ctx.user_id,
            org_id=ctx.org_id,
            resource_type="membership",
            resource_id=member_id,
            details={"user_id": user_id},
        )
        db.commit()
    return Response(status_code=204)
