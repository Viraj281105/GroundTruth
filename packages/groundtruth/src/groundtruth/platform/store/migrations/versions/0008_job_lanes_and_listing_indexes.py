"""Job lanes, and the indexes that keep listing and claiming fast as runs accumulate (#47).

* ``jobs.lane``: ``interactive`` for a person waiting (``POST /jobs``) or ``batch`` (the CLI,
  case creation's first run). Workers take interactive work first, so a batch cannot keep a
  user waiting behind it. Existing jobs become ``batch``: they were all queued without one.
* ``ix_analysis_runs_project_id_created_at_run_id``: every listing a signed-in user makes
  filters by the projects their organization may see (revision 0007). Without this index a
  page walked the newest runs of every organization and discarded the rest.
* ``ix_jobs_lease_expires_at``: every claim first reaps expired leases with
  ``lease_expires_at < now``. Without this index each claim, by every worker, scanned every
  job ever run.

**Numbering.** Viraj's open PR #87 also adds a revision ``0008`` on top of ``0007``. If it
merges first, renumber this one to ``0009`` with ``down_revision = "0008"`` before opening the
pull request; the migration tooling refuses two heads.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("lane", sa.String(16), nullable=False, server_default="batch"))
        batch.create_check_constraint(
            op.f("ck_jobs_lane_valid"), "lane IN ('interactive', 'batch')"
        )
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])
    op.create_index(
        "ix_analysis_runs_project_id_created_at_run_id",
        "analysis_runs",
        ["project_id", "created_at", "run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_project_id_created_at_run_id", table_name="analysis_runs")
    op.drop_index("ix_jobs_lease_expires_at", table_name="jobs")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint(op.f("ck_jobs_lane_valid"), type_="check")
        batch.drop_column("lane")
