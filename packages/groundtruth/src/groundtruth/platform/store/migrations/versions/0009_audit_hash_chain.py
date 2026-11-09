"""Audit ledger hash chain: sequence, previous root, record kind and hash scheme.

Rows written before this revision carry a NULL ``hash_scheme``. They were produced by the
earlier implementation, which filled missing dataset and intermediate hashes with fixed
placeholder values, so they are kept (the ledger is append-only) but are reported as
``legacy_unverifiable`` and never as verified.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_records", sa.Column("sequence", sa.Integer(), nullable=True))
    op.add_column("audit_records", sa.Column("prev_root_hash", sa.String(128), nullable=True))
    op.add_column(
        "audit_records",
        sa.Column("record_kind", sa.String(32), nullable=False, server_default="assessment"),
    )
    op.add_column("audit_records", sa.Column("hash_scheme", sa.String(32), nullable=True))
    op.create_index(
        "uq_audit_records_project_sequence",
        "audit_records",
        ["project_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_audit_records_project_sequence", table_name="audit_records")
    op.drop_column("audit_records", "hash_scheme")
    op.drop_column("audit_records", "record_kind")
    op.drop_column("audit_records", "prev_root_hash")
    op.drop_column("audit_records", "sequence")
