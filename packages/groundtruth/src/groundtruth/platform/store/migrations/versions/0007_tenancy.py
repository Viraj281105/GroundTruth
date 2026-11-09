"""Multi-tenant ownership: organizations, memberships, projects, grants and the audit log.

* ``organizations`` / ``memberships``: who a user acts for, and with which role.
* ``projects``: owned by one organization; ``case_id`` links to the engine's case.
* ``project_grants``: access an owner gives another organization.
* ``audit_events``: append-only record of security-relevant events.
* ``sessions.active_organization_id``, ``analysis_runs.project_id``, ``jobs.project_id``:
  nullable, so every existing row stays valid. The ``project_id`` backfill from
  ``case_id`` is done by ``groundtruth seed`` once the projects exist; no project can
  exist before this migration runs.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.CheckConstraint(
            "type IN ('ngo', 'funder', 'auditor', 'government', 'reference')",
            name=op.f("ck_organizations_type_valid"),
        ),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_memberships_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id", "organization_id", name="uq_memberships_user_id_organization_id"
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name=op.f("ck_memberships_role_valid"),
        ),
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("case_id", sa.String(100), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("ecosystem", sa.String(100), nullable=False),
        sa.Column("intervention", sa.String(100), nullable=False),
        sa.Column("treatment_start_year", sa.Integer(), nullable=False),
        sa.Column("boundary_path", sa.String(500), nullable=True),
        sa.Column("boundary_sha256", sa.String(64), nullable=True),
        sa.Column("data_mode", sa.String(16), nullable=False),
        sa.Column("reported_funding_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("reported_funding_currency", sa.String(3), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_projects_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.case_id"], name="fk_projects_case_id_cases"),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_projects_created_by_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("slug", name="uq_projects_slug"),
        sa.UniqueConstraint("case_id", name="uq_projects_case_id"),
        sa.CheckConstraint(
            "data_mode IN ('observed', 'simulated')", name=op.f("ck_projects_data_mode_valid")
        ),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
    op.create_table(
        "project_grants",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("grantee_organization_id", sa.String(36), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("granted_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_project_grants"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_grants_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["grantee_organization_id"],
            ["organizations.id"],
            name="fk_project_grants_grantee_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            name="fk_project_grants_granted_by_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "project_id",
            "grantee_organization_id",
            name="uq_project_grants_project_id_grantee_organization_id",
        ),
        sa.CheckConstraint(
            "level IN ('view', 'audit', 'contribute')", name=op.f("ck_project_grants_level_valid")
        ),
    )
    op.create_index(
        "ix_project_grants_grantee_organization_id", "project_grants", ["grantee_organization_id"]
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=True),
        sa.Column("organization_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("details", sa.JSON(none_as_null=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.CheckConstraint(
            "outcome IN ('success', 'denied', 'error')", name=op.f("ck_audit_events_outcome_valid")
        ),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index(
        "ix_audit_events_organization_id_occurred_at",
        "audit_events",
        ["organization_id", "occurred_at"],
    )

    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("active_organization_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_sessions_active_organization_id_organizations",
            "organizations",
            ["active_organization_id"],
            ["id"],
            ondelete="SET NULL",
        )
    for table in ("analysis_runs", "jobs"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("project_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_project_id_projects", "projects", ["project_id"], ["id"]
            )


def downgrade() -> None:
    for table in ("jobs", "analysis_runs"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_project_id_projects", type_="foreignkey")
            batch.drop_column("project_id")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint(
            "fk_sessions_active_organization_id_organizations", type_="foreignkey"
        )
        batch.drop_column("active_organization_id")
    op.drop_index("ix_audit_events_organization_id_occurred_at", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_project_grants_grantee_organization_id", table_name="project_grants")
    op.drop_table("project_grants")
    op.drop_index("ix_projects_organization_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_memberships_organization_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("organizations")
