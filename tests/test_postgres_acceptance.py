"""PostgreSQL acceptance: migrations, record preservation, and database-level guarantees.

Skipped unless ``GT_TEST_PG_ADMIN_URL`` points at a disposable PostgreSQL server (see
``tests/pgdb.py``). The rest of the database-backed suites (tenancy, auth, ledger, ingestion,
claims, documents) run unchanged against the same server when that variable is set; these tests add
what only a real server can show.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pgdb import TestDatabase, new_database, using_postgres

from groundtruth.platform.audit.ledger import STATUS_LEGACY, AuditLedger
from groundtruth.platform.store import migrate
from groundtruth.platform.store.database import create_db_engine, create_session_factory

pytestmark = pytest.mark.skipif(
    not using_postgres(), reason="needs a disposable PostgreSQL server (GT_TEST_PG_ADMIN_URL)"
)

NEW_TABLES = {"project_documents", "observation_ingestions", "project_claims"}


@pytest.fixture
def pg(tmp_path: Path) -> Iterator[TestDatabase]:
    db = new_database(tmp_path, "unused.db")
    yield db
    db.drop()


def _tables(url: str) -> set[str]:
    return set(sa.inspect(sa.create_engine(url)).get_table_names())


def _columns(url: str, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(sa.create_engine(url)).get_columns(table)}


def _dummy(col: sa.Column[Any]) -> Any:
    t = col.type
    if isinstance(t, sa.Boolean):
        return False
    if isinstance(t, sa.Integer):
        return 1
    if isinstance(t, sa.Float | sa.Numeric):
        return 1.0
    if isinstance(t, sa.DateTime):
        return datetime(2026, 1, 1, tzinfo=UTC)
    if isinstance(t, sa.JSON):
        return {}
    return f"x-{uuid.uuid4().hex[:8]}"


def _insert(conn: sa.Connection, meta: sa.MetaData, table: str, **values: Any) -> dict[str, Any]:
    """Insert a row, filling any other NOT NULL column with a type-appropriate dummy."""
    t = meta.tables[table]
    row = dict(values)
    for col in t.columns:
        if col.name not in row and not col.nullable and col.server_default is None:
            row[col.name] = _dummy(col)
    conn.execute(t.insert().values(**row))
    return row


# --- migrations ------------------------------------------------------------------------------------------


def test_migrations_apply_from_empty_and_reach_head(pg: TestDatabase) -> None:
    migrate.upgrade(pg.url)
    assert migrate.is_at_head(pg.url)
    assert migrate.current_revision(pg.url) == migrate.head_revision()
    assert NEW_TABLES <= _tables(pg.url)
    assert {"sequence", "prev_root_hash", "record_kind", "hash_scheme"} <= _columns(
        pg.url, "audit_records"
    )


def test_migrations_roll_back_and_forward_again(pg: TestDatabase) -> None:
    migrate.upgrade(pg.url)
    migrate.downgrade(pg.url, "0008")
    assert NEW_TABLES.isdisjoint(_tables(pg.url))
    assert "sequence" not in _columns(pg.url, "audit_records")
    migrate.upgrade(pg.url)
    assert migrate.is_at_head(pg.url) and NEW_TABLES <= _tables(pg.url)


def test_existing_records_survive_the_new_migrations(pg: TestDatabase) -> None:
    """Rows written under the old schema (0008) are intact, and the legacy ledger row stays unverified."""
    migrate.upgrade(pg.url, "0008")
    engine = sa.create_engine(pg.url)
    meta = sa.MetaData()
    meta.reflect(engine)
    org_id, proj_id, user_id = (str(uuid.uuid4()) for _ in range(3))
    with engine.begin() as conn:
        _insert(conn, meta, "users", id=user_id, email=f"{user_id}@example.org", role="user")
        _insert(conn, meta, "organizations", id=org_id, slug=f"org-{org_id[:6]}", type="ngo")
        _insert(
            conn,
            meta,
            "projects",
            id=proj_id,
            slug=f"p-{proj_id[:6]}",
            organization_id=org_id,
            data_mode="observed",
        )
        _insert(
            conn,
            meta,
            "audit_records",
            record_id="AUDIT-LEGACY-1",
            project_id=proj_id,
            merkle_root_hash="sha256:" + "00" * 32,
            final_findings={"att": 0.5},
            deterministic_reproducible=True,
        )
    before = {
        "projects": sa.select(sa.func.count()).select_from(meta.tables["projects"]),
        "orgs": sa.select(sa.func.count()).select_from(meta.tables["organizations"]),
        "users": sa.select(sa.func.count()).select_from(meta.tables["users"]),
    }
    with engine.connect() as c:
        counts_before = {k: c.execute(q).scalar_one() for k, q in before.items()}
        legacy_before = c.execute(
            sa.text("SELECT final_findings, merkle_root_hash FROM audit_records")
        ).one()

    migrate.upgrade(pg.url)  # 0009 -> 0012

    with sa.create_engine(pg.url).connect() as c:
        for key, table in (("projects", "projects"), ("orgs", "organizations"), ("users", "users")):
            assert (
                c.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
                == counts_before[key]
            )
        row = c.execute(
            sa.text(
                "SELECT record_id, final_findings, merkle_root_hash, sequence, prev_root_hash, "
                "record_kind, hash_scheme FROM audit_records"
            )
        ).one()
    assert row.record_id == "AUDIT-LEGACY-1"
    assert row.final_findings == legacy_before.final_findings == {"att": 0.5}
    assert row.merkle_root_hash == legacy_before.merkle_root_hash
    assert row.sequence is None and row.prev_root_hash is None and row.hash_scheme is None
    assert row.record_kind == "assessment"  # the server default applied to the existing row

    ledger = AuditLedger(create_session_factory(create_db_engine(pg.url)))
    result = ledger.verify_project(proj_id)
    assert result.status == STATUS_LEGACY and result.legacy_record_count == 1
    # new records chain independently of the legacy one
    rec = ledger.record_assessment(proj_id, {"type": "Point", "coordinates": [0, 0]}, {}, {"a": 1})
    assert rec.sequence == 1 and ledger.verify_project(proj_id).record_count == 1


# --- database-level guarantees -------------------------------------------------------------------------------


def _seeded(pg: TestDatabase) -> tuple[sa.Engine, sa.MetaData, str, str]:
    migrate.upgrade(pg.url)
    engine = sa.create_engine(pg.url)
    meta = sa.MetaData()
    meta.reflect(engine)
    org_id, proj_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        _insert(conn, meta, "organizations", id=org_id, slug=f"org-{org_id[:6]}", type="ngo")
        _insert(
            conn,
            meta,
            "projects",
            id=proj_id,
            slug=f"p-{proj_id[:6]}",
            organization_id=org_id,
            data_mode="observed",
        )
    return engine, meta, org_id, proj_id


def test_the_ledger_sequence_is_unique_per_project_in_the_database(pg: TestDatabase) -> None:
    engine, meta, _, proj = _seeded(pg)
    base = {
        "project_id": proj,
        "sequence": 1,
        "hash_scheme": "gt-merkle-v2",
        "merkle_root_hash": "sha256:" + "11" * 32,
    }
    with engine.begin() as conn:
        _insert(conn, meta, "audit_records", record_id="AUDIT-A", **base)
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        _insert(conn, meta, "audit_records", record_id="AUDIT-B", **base)


def test_invalid_ingestion_status_is_rejected_by_the_database(pg: TestDatabase) -> None:
    engine, meta, _, proj = _seeded(pg)
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
        _insert(
            conn,
            meta,
            "observation_ingestions",
            id=str(uuid.uuid4()),
            project_id=proj,
            status="banana",
            params={},
        )
    with engine.begin() as conn:
        _insert(
            conn,
            meta,
            "observation_ingestions",
            id=str(uuid.uuid4()),
            project_id=proj,
            status="queued",
            params={"a": 1},
        )


def test_deleting_a_project_removes_its_documents_ingestions_and_claims(pg: TestDatabase) -> None:
    engine, meta, _, proj = _seeded(pg)
    with engine.begin() as conn:
        doc_id = str(uuid.uuid4())
        _insert(conn, meta, "project_documents", id=doc_id, project_id=proj, status="uploaded")
        _insert(
            conn,
            meta,
            "observation_ingestions",
            id=str(uuid.uuid4()),
            project_id=proj,
            status="queued",
            params={},
        )
        _insert(
            conn,
            meta,
            "project_claims",
            id=str(uuid.uuid4()),
            project_id=proj,
            source_document_id=doc_id,
            kind="area_hectares",
        )
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM projects WHERE id = :p"), {"p": proj})
    with engine.connect() as conn:
        for table in ("project_documents", "observation_ingestions", "project_claims"):
            assert conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table


def test_a_source_document_deleted_leaves_the_claim_and_its_original_text(pg: TestDatabase) -> None:
    engine, meta, _, proj = _seeded(pg)
    doc_id, claim_id = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        _insert(conn, meta, "project_documents", id=doc_id, project_id=proj, status="uploaded")
        _insert(
            conn,
            meta,
            "project_claims",
            id=claim_id,
            project_id=proj,
            source_document_id=doc_id,
            original_text="We restored 12,000 ha",
            kind="area_hectares",
        )
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM project_documents WHERE id = :d"), {"d": doc_id})
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT source_document_id, original_text FROM project_claims WHERE id = :c"),
            {"c": claim_id},
        ).one()
    assert row.source_document_id is None and row.original_text == "We restored 12,000 ha"


def test_timestamps_keep_their_timezone_and_json_round_trips(pg: TestDatabase) -> None:
    engine, meta, _, proj = _seeded(pg)
    when = datetime(2026, 11, 9, 12, 30, 45, 123456, tzinfo=UTC)
    payload = {"years": [2021, 2023], "nested": {"ok": True, "n": 0.5}, "text": "ünïcode ✓"}
    rid = str(uuid.uuid4())
    with engine.begin() as conn:
        _insert(
            conn,
            meta,
            "observation_ingestions",
            id=rid,
            project_id=proj,
            status="succeeded",
            params=payload,
            created_at=when,
            finished_at=when,
            result=payload,
        )
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT params, result, created_at FROM observation_ingestions WHERE id = :i"),
            {"i": rid},
        ).one()
    assert row.params == payload and row.result == payload
    assert row.created_at == when and row.created_at.utcoffset() == when.utcoffset()
