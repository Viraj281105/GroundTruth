"""Indexes that serve keyset pagination of runs exactly, and the engine-version filter.

The run listing API (issue #35) orders by ``(created_at DESC, run_id DESC)`` and pages
with ``WHERE (created_at, run_id) < (:t, :r)``. The indexes from revision 0001 end at
``created_at``, so the database still had to sort ties on ``run_id``, and filtering by
engine version had no index at all (a full scan). The new indexes end in ``run_id``,
so each page is an index range scan with no sort.

Three indexes from 0001 are replaced because each is a strict prefix of its successor:
a second index with the same leading columns costs writes and answers nothing the new
one cannot. ``downgrade`` recreates them exactly as 0001 defined them.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# (name, columns) as revision 0001 created them. downgrade() restores exactly these.
SUPERSEDED = (
    ("ix_analysis_runs_case_id_created_at", ["case_id", "created_at"]),
    ("ix_analysis_runs_status_created_at", ["status", "created_at"]),
    ("ix_analysis_runs_created_at", ["created_at"]),
)

ADDED = (
    ("ix_analysis_runs_case_id_created_at_run_id", ["case_id", "created_at", "run_id"]),
    ("ix_analysis_runs_status_created_at_run_id", ["status", "created_at", "run_id"]),
    (
        "ix_analysis_runs_engine_version_created_at_run_id",
        ["engine_version", "created_at", "run_id"],
    ),
    ("ix_analysis_runs_created_at_run_id", ["created_at", "run_id"]),
)


def upgrade() -> None:
    for name, columns in ADDED:
        op.create_index(name, "analysis_runs", columns)
    for name, _ in SUPERSEDED:
        op.drop_index(name, table_name="analysis_runs")


def downgrade() -> None:
    for name, columns in SUPERSEDED:
        op.create_index(name, "analysis_runs", columns)
    for name, _ in ADDED:
        op.drop_index(name, table_name="analysis_runs")
