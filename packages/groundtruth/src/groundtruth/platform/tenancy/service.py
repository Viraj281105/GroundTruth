"""Organization and membership operations.

Functions flush but never commit: the caller owns the transaction so a membership change and
its audit event land together.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from groundtruth.contracts.errors import DataUnavailableError, GroundTruthError
from groundtruth.platform.store.models import (
    MembershipRow,
    OrganizationRow,
    SessionRow,
    UserRow,
)

OrgType = Literal["ngo", "funder", "auditor", "government", "reference"]
MemberRole = Literal["owner", "admin", "member", "viewer"]

_SLUG_MAX = 80


class TenancyConflictError(GroundTruthError):
    """A membership change that would break an invariant (for example no owner left)."""


class TenancyForbiddenError(GroundTruthError):
    """The acting member's role may not make this change (only owners touch owners)."""


_SLUG_ATTEMPTS = 8


def _check_may_grant(actor_role: str, *roles: str) -> None:
    """Admins manage admin|member|viewer only; anything involving ``owner`` needs an owner."""
    if "owner" in roles and actor_role != "owner":
        raise TenancyForbiddenError("only an owner may grant, change or remove the owner role")


def _now() -> datetime:
    return datetime.now(UTC)


def slugify(name: str) -> str:
    """Lowercase kebab slug. Never UUID-shaped, so a slug cannot be mistaken for an id."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:_SLUG_MAX].strip("-")
    if not slug:
        slug = "org"
    try:
        uuid.UUID(slug)
    except ValueError:
        return slug
    return f"org-{slug}"


def _unique_slug(db: Session, base: str) -> str:
    taken = set(
        db.execute(select(OrganizationRow.slug).where(OrganizationRow.slug.like(f"{base}%")))
        .scalars()
        .all()
    )
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def _next_slug(db: Session, base: str, tried: set[str]) -> str:
    slug = _unique_slug(db, base)
    n = 2
    while slug in tried:
        slug = f"{base}-{n}"
        n += 1
    return slug


def create_org(db: Session, *, name: str, type: OrgType, creator_user_id: str) -> OrganizationRow:
    """Create an organization with ``creator_user_id`` as its owner.

    The slug is chosen by a read, so a concurrent create can take it first; the insert runs in
    a savepoint and a unique-constraint loss retries with the next numeric suffix.
    """
    now = _now()
    base = slugify(name)
    tried: set[str] = set()
    for _ in range(_SLUG_ATTEMPTS):
        slug = _next_slug(db, base, tried)
        org = OrganizationRow(
            id=str(uuid.uuid4()), slug=slug, name=name.strip(), type=type, created_at=now
        )
        try:
            with db.begin_nested():
                db.add(org)
                db.flush()
        except IntegrityError:
            tried.add(slug)
            continue
        db.add(
            MembershipRow(
                id=str(uuid.uuid4()),
                user_id=creator_user_id,
                organization_id=org.id,
                role="owner",
                created_at=now,
            )
        )
        db.flush()
        return org
    raise TenancyConflictError("could not allocate a unique organization slug")


def list_user_memberships(db: Session, user_id: str) -> list[tuple[OrganizationRow, MembershipRow]]:
    rows = db.execute(
        select(OrganizationRow, MembershipRow)
        .join(MembershipRow, MembershipRow.organization_id == OrganizationRow.id)
        .where(MembershipRow.user_id == user_id)
        .order_by(MembershipRow.created_at, OrganizationRow.slug)
    ).all()
    return [(o, m) for o, m in rows]


def list_members(db: Session, org_id: str) -> list[tuple[MembershipRow, UserRow]]:
    rows = db.execute(
        select(MembershipRow, UserRow)
        .join(UserRow, UserRow.id == MembershipRow.user_id)
        .where(MembershipRow.organization_id == org_id)
        .order_by(MembershipRow.created_at, UserRow.email)
    ).all()
    return [(m, u) for m, u in rows]


def get_membership(db: Session, org_id: str, user_id: str) -> MembershipRow | None:
    return db.execute(
        select(MembershipRow).where(
            MembershipRow.organization_id == org_id, MembershipRow.user_id == user_id
        )
    ).scalar_one_or_none()


def add_member(
    db: Session, org_id: str, *, email: str, role: MemberRole, actor_role: str
) -> MembershipRow:
    """Add an existing user.

    Raises:
        DataUnavailableError: no account has that email.
        TenancyConflictError: the user is already a member.
        TenancyForbiddenError: ``role`` is owner and ``actor_role`` is not.
    """
    _check_may_grant(actor_role, role)
    user = db.execute(
        select(UserRow).where(UserRow.email == email.strip().lower())
    ).scalar_one_or_none()
    if user is None:
        raise DataUnavailableError("no account with that email")
    if get_membership(db, org_id, user.id) is not None:
        raise TenancyConflictError("user is already a member")
    row = MembershipRow(
        id=str(uuid.uuid4()),
        user_id=user.id,
        organization_id=org_id,
        role=role,
        created_at=_now(),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:  # a concurrent add won the unique (user, organization) race
        raise TenancyConflictError("user is already a member") from exc
    return row


def _owner_count(db: Session, org_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(MembershipRow)
        .where(MembershipRow.organization_id == org_id, MembershipRow.role == "owner")
    ).scalar_one()


def _require_member(db: Session, org_id: str, user_id: str) -> MembershipRow:
    row = get_membership(db, org_id, user_id)
    if row is None:
        raise DataUnavailableError("not a member of this organization")
    return row


def set_member_role(
    db: Session, org_id: str, user_id: str, role: MemberRole, *, actor_role: str
) -> MembershipRow:
    row = _require_member(db, org_id, user_id)
    _check_may_grant(actor_role, role, row.role)
    if row.role == "owner" and role != "owner" and _owner_count(db, org_id) <= 1:
        raise TenancyConflictError("organization must keep an owner")
    row.role = role
    db.flush()
    return row


def remove_member(db: Session, org_id: str, user_id: str, *, actor_role: str) -> None:
    row = _require_member(db, org_id, user_id)
    _check_may_grant(actor_role, row.role)
    if row.role == "owner" and _owner_count(db, org_id) <= 1:
        raise TenancyConflictError("organization must keep an owner")
    db.delete(row)
    db.flush()


def set_active_org(db: Session, session_token_hash: str, org_id: str | None) -> None:
    """Persist the active organization on a session row (caller checked membership)."""
    row = db.execute(
        select(SessionRow).where(SessionRow.token_hash == session_token_hash)
    ).scalar_one_or_none()
    if row is None:
        raise DataUnavailableError("session not found")
    row.active_organization_id = org_id
    db.flush()
