"""Persistent cryptographic audit ledger: audit_records table.

Binds project geometry, dataset versions/hashes, analytical parameters,
Git commit SHA, intermediate calculation hashes, and final findings
into an immutable, tamper-evident Merkle root hash.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_records",
        sa.Column("record_id", sa.String(64), nullable=False),
        sa.Column("project_id", sa.String(100), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("git_commit_sha", sa.String(64), nullable=False),
        sa.Column("contract_version", sa.String(32), nullable=False),
        sa.Column("engine_version", sa.String(32), nullable=False),
        sa.Column("methodology_version", sa.String(64), nullable=False),
        sa.Column("boundary_geometry_hash", sa.String(128), nullable=False),
        sa.Column("input_files_hashes", sa.JSON(), nullable=False),
        sa.Column("dataset_versions_hashes", sa.JSON(), nullable=False),
        sa.Column("analytical_parameters", sa.JSON(), nullable=False),
        sa.Column("intermediate_hashes", sa.JSON(), nullable=False),
        sa.Column("final_findings", sa.JSON(), nullable=False),
        sa.Column("report_version", sa.String(32), nullable=False),
        sa.Column("merkle_root_hash", sa.String(128), nullable=False),
        sa.Column("deterministic_reproducible", sa.Boolean(), nullable=False, default=True),
        sa.PrimaryKeyConstraint("record_id", name="pk_audit_records"),
    )
    op.create_index("ix_audit_records_project_id", "audit_records", ["project_id"])
    op.create_index("ix_audit_records_timestamp", "audit_records", ["timestamp"])
    op.create_index("ix_audit_records_merkle_root_hash", "audit_records", ["merkle_root_hash"])


def downgrade() -> None:
    op.drop_index("ix_audit_records_merkle_root_hash", table_name="audit_records")
    op.drop_index("ix_audit_records_timestamp", table_name="audit_records")
    op.drop_index("ix_audit_records_project_id", table_name="audit_records")
    op.drop_table("audit_records")
