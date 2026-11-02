"""Record which stage a running job is in, so the API can show it.

The worker runs a job in stages (claim, data, engine, record) but until now only logged
them, so nothing the API could read said where a job was. The job status endpoint
(issue #37) needs that.

* ``jobs.stage``: the stage the job is in now.
* ``jobs.stage_log``: when each stage began, as ``{"claim": "<iso time>", ...}``. A
  stage ends when the next begins, so its duration is the difference; no end time is
  stored, so none can disagree with the next stage's start.

Both are nullable: a row written before this revision has no stage, and the API shows
that as "unknown", not as a guess. A retry clears them, so a job waiting to run again
does not display the failed attempt's progress.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

JSON_DOCUMENT = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def upgrade() -> None:
    op.add_column("jobs", sa.Column("stage", sa.String(20), nullable=True))
    op.add_column("jobs", sa.Column("stage_log", JSON_DOCUMENT, nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "stage_log")
    op.drop_column("jobs", "stage")
