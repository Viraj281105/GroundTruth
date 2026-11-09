"""Project documents: uploaded design documents and baseline records per project.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(300), nullable=False),
        sa.Column("uploaded_by", sa.String(36), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("status_detail", sa.String(500), nullable=True),
        sa.Column("extracted_text_chars", sa.Integer(), nullable=True),
        sa.Column("extracted_claims_count", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_project_documents"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_documents_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_project_documents_uploaded_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'text_extracted', 'extraction_unsupported', "
            "'extraction_failed')",
            name=op.f("ck_project_documents_status_valid"),
        ),
    )
    op.create_index("ix_project_documents_project_id", "project_documents", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_project_documents_project_id", table_name="project_documents")
    op.drop_table("project_documents")
