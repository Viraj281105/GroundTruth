"""Observation ingestion requests: status, parameters and measured results per project.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_STATUSES = "'queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled'"


def upgrade() -> None:
    op.create_table(
        "observation_ingestions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("status_detail", sa.String(1000), nullable=True),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(100), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("ledger_record_id", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_observation_ingestions"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_observation_ingestions_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_observation_ingestions_requested_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),
    )
    op.create_index(
        "ix_observation_ingestions_project_created",
        "observation_ingestions",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_observation_ingestions_project_created", table_name="observation_ingestions")
    op.drop_table("observation_ingestions")
