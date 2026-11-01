"""Record the contract version the engine targets, on each run.

``EngineRef`` carries two versions: the engine build and the contract it targets.
Revision 0001 stored the first and not the second, so a stored result could not be
rebuilt exactly. Added as a new revision because 0001 has been applied and a
migration that has been applied is never edited.

The column is nullable: nothing wrote to ``analysis_runs`` before the evidence store
existed, so there is no existing row to backfill, and inventing a value for one
would fabricate data. The store always writes it and refuses to read a run without it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs", sa.Column("engine_contract_version", sa.String(20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("analysis_runs", "engine_contract_version")
