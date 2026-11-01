"""Store each run's request, and each job's lease expiry.

Two things the job lifecycle (issue #24) needs that revisions 0001 and 0002 lack:

* ``analysis_runs.request``: the full ``AnalysisRequest``. A queued run may execute
  hours later, after a restart; rebuilding its request from the case file then would
  run whatever the file says *now*, which need not match the run's ``spec_hash``.
* ``jobs.lease_expires_at``: when a claim lapses. Stored, so workers configured with
  different lease lengths still agree on which jobs are abandoned.

Both are nullable for the same reason as 0002: no row was written before the job
layer existed, and a backfill would have to invent values.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("request", JSON_DOCUMENT, nullable=True))
    op.add_column("jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "lease_expires_at")
    op.drop_column("analysis_runs", "request")
