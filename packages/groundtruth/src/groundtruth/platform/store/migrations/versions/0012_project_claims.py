"""Project claims: statements a person promoted for verification, with their original source.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_claims",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("source_document_id", sa.String(36), nullable=True),
        sa.Column("source_document_name", sa.String(255), nullable=True),
        sa.Column("source_document_sha256", sa.String(64), nullable=True),
        sa.Column("source_start", sa.Integer(), nullable=True),
        sa.Column("source_end", sa.Integer(), nullable=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("original_kind", sa.String(48), nullable=True),
        sa.Column("original_value", sa.Float(), nullable=True),
        sa.Column("original_unit", sa.String(40), nullable=True),
        sa.Column("original_period", sa.String(60), nullable=True),
        sa.Column("statement_text", sa.String(1000), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("claimed_value", sa.Float(), nullable=True),
        sa.Column("claimed_unit", sa.String(40), nullable=True),
        sa.Column("claimed_period", sa.String(60), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_project_claims"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_claims_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["project_documents.id"],
            name="fk_project_claims_source_document_id_project_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_project_claims_created_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_project_claims_updated_by_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_project_claims_project_id", "project_claims", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_claims_project_id", table_name="project_claims")
    op.drop_table("project_claims")
