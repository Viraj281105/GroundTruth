"""Initial schema: cases, analysis runs, evidence bundles, datasets and jobs.

Written by hand rather than generated from the models, and deliberately repeating
literals (status values, constraint names) instead of importing them. A migration
describes the schema as it was at one moment; importing live constants would let a
later change to the models silently rewrite history.

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# JSONB on PostgreSQL (indexable, compact); plain JSON text elsewhere. none_as_null
# stores Python None as SQL NULL so "absent" is queryable with IS NULL.
JSON_DOCUMENT = sa.JSON(none_as_null=True).with_variant(
    postgresql.JSONB(none_as_null=True), "postgresql"
)


def _timestamp(name: str, *, default_now: bool = False) -> sa.Column[datetime]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=not default_now,
        server_default=sa.func.now() if default_now else None,
    )


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("indicator", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("definition", JSON_DOCUMENT, nullable=False),
        _timestamp("created_at", default_now=True),
        _timestamp("updated_at", default_now=True),
        sa.PrimaryKeyConstraint("case_id", name="pk_cases"),
        sa.CheckConstraint(
            "status IN ('scaffolded', 'data-wired', 'analysed')", name=op.f("ck_cases_status_valid")
        ),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(100), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("engine_status", sa.String(16), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("error", JSON_DOCUMENT, nullable=True),
        sa.Column("verdict_label", sa.String(40), nullable=True),
        sa.Column("data_mode", sa.String(16), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("engine_version", sa.String(40), nullable=True),
        sa.Column("engine_git_sha", sa.String(64), nullable=True),
        sa.Column("contract_version", sa.String(20), nullable=False),
        sa.Column("dataset_refs", JSON_DOCUMENT, nullable=False),
        sa.Column("metrics", JSON_DOCUMENT, nullable=True),
        sa.Column("requested_by", sa.String(100), nullable=True),
        _timestamp("created_at", default_now=True),
        _timestamp("started_at"),
        _timestamp("finished_at"),
        sa.PrimaryKeyConstraint("run_id", name="pk_analysis_runs"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.case_id"], name="fk_analysis_runs_case_id_cases"
        ),
        sa.UniqueConstraint("run_id", "case_id", name="uq_analysis_runs_run_id_case_id"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_analysis_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "data_mode IN ('observed', 'simulated')", name=op.f("ck_analysis_runs_data_mode_valid")
        ),
        sa.CheckConstraint(
            "is_simulated = (data_mode = 'simulated')",
            name=op.f("ck_analysis_runs_simulated_flag_matches_data_mode"),
        ),
    )
    op.create_index(
        "ix_analysis_runs_case_id_created_at", "analysis_runs", ["case_id", "created_at"]
    )
    op.create_index("ix_analysis_runs_status_created_at", "analysis_runs", ["status", "created_at"])
    op.create_index("ix_analysis_runs_spec_hash", "analysis_runs", ["spec_hash"])
    op.create_index("ix_analysis_runs_created_at", "analysis_runs", ["created_at"])

    op.create_table(
        "evidence_bundles",
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(100), nullable=False),
        sa.Column("contract_version", sa.String(20), nullable=False),
        sa.Column("bundle", JSON_DOCUMENT, nullable=False),
        sa.Column("verdict_label", sa.String(40), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        _timestamp("created_at", default_now=True),
        sa.PrimaryKeyConstraint("run_id", name="pk_evidence_bundles"),
        sa.ForeignKeyConstraint(
            ["run_id", "case_id"],
            ["analysis_runs.run_id", "analysis_runs.case_id"],
            name="fk_evidence_bundles_run_id_case_id_analysis_runs",
        ),
        sa.CheckConstraint(
            "item_count >= 0", name=op.f("ck_evidence_bundles_item_count_non_negative")
        ),
    )
    op.create_index(
        "ix_evidence_bundles_case_id_created_at", "evidence_bundles", ["case_id", "created_at"]
    )
    op.create_index(
        "ix_evidence_bundles_verdict_label_created_at",
        "evidence_bundles",
        ["verdict_label", "created_at"],
    )
    op.create_index("ix_evidence_bundles_created_at", "evidence_bundles", ["created_at"])

    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(100), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("asset", sa.String(500), nullable=True),
        sa.Column("source_uri", sa.String(1000), nullable=True),
        _timestamp("retrieved_at"),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("retrieval_metadata", JSON_DOCUMENT, nullable=True),
        _timestamp("registered_at", default_now=True),
        sa.PrimaryKeyConstraint("dataset_id", "version", "provider", name="pk_datasets"),
    )

    op.create_table(
        "jobs",
        sa.Column("run_id", sa.String(32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        _timestamp("available_at", default_now=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        _timestamp("heartbeat_at"),
        _timestamp("cancel_requested_at"),
        sa.Column("last_error", JSON_DOCUMENT, nullable=True),
        _timestamp("created_at", default_now=True),
        _timestamp("updated_at", default_now=True),
        sa.PrimaryKeyConstraint("run_id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analysis_runs.run_id"], name="fk_jobs_run_id_analysis_runs"
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_attempts_non_negative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_jobs_max_attempts_positive")),
    )
    op.create_index("ix_jobs_available_at", "jobs", ["available_at"])

    _forbid_bundle_updates()


def downgrade() -> None:
    _allow_bundle_updates()
    # Reverse dependency order: children before the tables they reference. Dropping
    # a table drops its indexes.
    op.drop_table("jobs")
    op.drop_table("datasets")
    op.drop_table("evidence_bundles")
    op.drop_table("analysis_runs")
    op.drop_table("cases")


# --- immutability ---------------------------------------------------------------
# Bundles are never updated; a re-run is a new run_id. A trigger enforces that in
# the database, so code that bypasses the ORM cannot rewrite history either.

_IMMUTABLE_MESSAGE = "evidence_bundles rows are immutable: a re-run is a new run_id"


def _forbid_bundle_updates() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "CREATE FUNCTION forbid_evidence_bundle_update() RETURNS trigger AS $$ "
                f"BEGIN RAISE EXCEPTION '{_IMMUTABLE_MESSAGE}'; END; "
                "$$ LANGUAGE plpgsql"
            )
        )
        op.execute(
            sa.text(
                "CREATE TRIGGER evidence_bundles_immutable BEFORE UPDATE ON evidence_bundles "
                "FOR EACH ROW EXECUTE FUNCTION forbid_evidence_bundle_update()"
            )
        )
    else:
        op.execute(
            sa.text(
                "CREATE TRIGGER evidence_bundles_immutable BEFORE UPDATE ON evidence_bundles "
                f"BEGIN SELECT RAISE(ABORT, '{_IMMUTABLE_MESSAGE}'); END"
            )
        )


def _allow_bundle_updates() -> None:
    op.execute(sa.text("DROP TRIGGER evidence_bundles_immutable" + _drop_trigger_suffix()))
    if op.get_context().dialect.name == "postgresql":
        op.execute(sa.text("DROP FUNCTION forbid_evidence_bundle_update()"))


def _drop_trigger_suffix() -> str:
    # PostgreSQL scopes a trigger to its table; SQLite does not accept ON <table>.
    return " ON evidence_bundles" if op.get_context().dialect.name == "postgresql" else ""
