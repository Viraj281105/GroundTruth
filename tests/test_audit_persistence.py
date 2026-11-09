"""Audit ledger integrity: Merkle roots, hash chain, persistence, tamper detection.

Replaces the earlier tests, which asserted behaviour that was fabricated: a Kariba record
invented for any project id, placeholder dataset hashes (including the SHA-256 of empty input)
and an unauthenticated ledger route.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import sys
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent))
from groundtruth.platform.audit.ledger import (
    GENESIS,
    STATUS_EMPTY,
    STATUS_FAILED,
    STATUS_LEGACY,
    STATUS_VERIFIED,
    AuditLedger,
    compute_sha256,
    ledger_root,
    merkle_root,
)
from groundtruth.platform.store.database import create_db_engine
from groundtruth.platform.store.models import Base
from pgdb import new_database

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
GEO = {
    "type": "Polygon",
    "coordinates": [[[30.0, -20.0], [31.0, -20.0], [31.0, -21.0], [30.0, -21.0], [30.0, -20.0]]],
}


@pytest.fixture
def db_url(tmp_path: Path) -> Iterator[str]:
    db = new_database(tmp_path, "ledger.db")
    Base.metadata.create_all(create_db_engine(db.url))
    yield db.url
    db.drop()


def _ledger(url: str) -> AuditLedger:
    """A ledger on its own engine: each call models a fresh process (a restart)."""
    return AuditLedger(sessionmaker(create_db_engine(url)))


@pytest.fixture
def ledger(db_url: str) -> AuditLedger:
    return _ledger(db_url)


def _add(ledger: AuditLedger, project: str, n: int = 1) -> list[str]:
    return [
        ledger.record_assessment(
            project,
            GEO,
            {"seed": i},
            {"att": 0.01 * i},
            dataset_hashes={"chirps": compute_sha256(f"chirps-{i}")},
        ).record_id
        for i in range(n)
    ]


def _sql(url: str, statement: str, **params: object) -> None:
    """Change stored data below the ORM, as an attacker with database access would."""
    engine = create_db_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text(statement), params)


# --- honesty ---------------------------------------------------------------------------------


def test_empty_ledger_is_reported_empty_not_verified(ledger: AuditLedger) -> None:
    result = ledger.verify_project("proj-empty")
    assert result.status == STATUS_EMPTY
    assert result.record_count == 0
    assert result.ledger_root is None
    assert ledger.get_records("proj-empty") == []  # no invented Kariba record


def test_unknown_project_never_gets_a_seeded_record(ledger: AuditLedger) -> None:
    for project in ("kariba-redd", "kariba", "anything"):
        assert ledger.get_records(project) == []


def test_no_placeholder_hashes_are_stored(ledger: AuditLedger) -> None:
    rec = ledger.record_assessment("p", GEO, {"seed": 1}, {"att": 0.1})
    assert rec.dataset_versions_hashes == {}
    assert rec.intermediate_hashes == {}
    stored = repr(rec.to_dict())
    assert EMPTY_SHA256 not in stored
    assert rec.git_commit_sha != "7f8a920bca918274619a8273618bca9125c28e81"
    assert rec.deterministic_reproducible is False  # not asserted without a re-run


def test_root_is_not_the_empty_input_digest(ledger: AuditLedger) -> None:
    rec = ledger.record_assessment("p", GEO, {}, {})
    assert EMPTY_SHA256 not in rec.merkle_root_hash


def test_merkle_tree_needs_leaves_and_promotes_odd_nodes() -> None:
    with pytest.raises(ValueError):
        merkle_root([])
    a, b, c = (hashlib.sha256(x).digest() for x in (b"a", b"b", b"c"))
    assert merkle_root([a]) == a
    # three leaves must not equal four with the last duplicated (no duplicate-leaf ambiguity)
    assert merkle_root([a, b, c]) != merkle_root([a, b, c, c])
    assert ledger_root([]) is None


# --- single and multiple records -----------------------------------------------------------------


def test_single_record_verifies(ledger: AuditLedger) -> None:
    (rid,) = _add(ledger, "p1")
    result = ledger.verify_project("p1")
    assert result.status == STATUS_VERIFIED
    assert result.record_count == 1 and result.head_sequence == 1
    rec = ledger.get_record_by_id(rid)
    assert rec is not None and rec.prev_root_hash == GENESIS and rec.sequence == 1
    assert ledger.verify_integrity(rid)[0] is True
    assert result.ledger_root == ledger_root([rec.merkle_root_hash])


def test_multiple_records_chain(ledger: AuditLedger) -> None:
    ids = _add(ledger, "p2", 4)
    recs = ledger.get_records("p2")
    assert [r.sequence for r in recs] == [1, 2, 3, 4]
    assert recs[0].prev_root_hash == GENESIS
    for prev, cur in pairwise(recs):
        assert cur.prev_root_hash == prev.merkle_root_hash
    assert ledger.verify_project("p2").status == STATUS_VERIFIED
    assert len(set(ids)) == 4


def test_projects_are_independent_chains(ledger: AuditLedger) -> None:
    _add(ledger, "a", 2)
    _add(ledger, "b", 1)
    assert ledger.verify_project("a").record_count == 2
    assert ledger.verify_project("b").record_count == 1
    assert ledger.get_records("b")[0].prev_root_hash == GENESIS


# --- tamper detection ----------------------------------------------------------------------------


def test_modification_is_detected(db_url: str, ledger: AuditLedger) -> None:
    ids = _add(ledger, "p3", 3)
    _sql(
        db_url,
        "UPDATE audit_records SET final_findings = CAST(:f AS JSON) WHERE record_id = :r",
        f='{"att": 0.9}',
        r=ids[1],
    )
    fresh = _ledger(db_url)
    result = fresh.verify_project("p3")
    assert result.status == STATUS_FAILED
    assert any(f.record_id == ids[1] and "modified" in f.reason for f in result.failures)
    ok, msg = fresh.verify_integrity(ids[1])
    assert ok is False and "TAMPERING DETECTED" in msg


def test_modifying_a_stored_root_breaks_the_chain(db_url: str, ledger: AuditLedger) -> None:
    ids = _add(ledger, "p4", 3)
    _sql(
        db_url,
        "UPDATE audit_records SET merkle_root_hash = :h WHERE record_id = :r",
        h="sha256:" + "ab" * 32,
        r=ids[0],
    )
    assert _ledger(db_url).verify_project("p4").status == STATUS_FAILED


def test_deletion_is_detected(db_url: str, ledger: AuditLedger) -> None:
    ids = _add(ledger, "p5", 4)
    _sql(db_url, "DELETE FROM audit_records WHERE record_id = :r", r=ids[1])
    result = _ledger(db_url).verify_project("p5")
    assert result.status == STATUS_FAILED
    assert any("removed, inserted or reordered" in f.reason for f in result.failures)


def test_reordering_is_detected(db_url: str, ledger: AuditLedger) -> None:
    ids = _add(ledger, "p6", 3)
    # swap sequence numbers 2 and 3 (temporarily clear one to satisfy the unique index)
    _sql(db_url, "UPDATE audit_records SET sequence = 99 WHERE record_id = :r", r=ids[1])
    _sql(db_url, "UPDATE audit_records SET sequence = 2 WHERE record_id = :r", r=ids[2])
    _sql(db_url, "UPDATE audit_records SET sequence = 3 WHERE record_id = :r", r=ids[1])
    assert _ledger(db_url).verify_project("p6").status == STATUS_FAILED


def test_replaying_a_record_into_another_project_is_detected(
    db_url: str, ledger: AuditLedger
) -> None:
    (rid,) = _add(ledger, "origin")
    _sql(db_url, "UPDATE audit_records SET project_id = 'other' WHERE record_id = :r", r=rid)
    assert _ledger(db_url).verify_project("other").status == STATUS_FAILED


def test_orm_cannot_update_or_delete_ledger_rows(db_url: str, ledger: AuditLedger) -> None:
    from groundtruth.contracts.errors import ProvenanceError
    from groundtruth.platform.store.models import AuditRecordRow

    (rid,) = _add(ledger, "p7")
    factory = sessionmaker(create_db_engine(db_url))
    with factory() as session:
        row = session.get(AuditRecordRow, rid)
        assert row is not None
        row.final_findings = {"att": 5}
        with pytest.raises(ProvenanceError):
            session.flush()
    with factory() as session:
        session.delete(session.get(AuditRecordRow, rid))
        with pytest.raises(ProvenanceError):
            session.flush()


def test_missing_record_fails_closed(ledger: AuditLedger) -> None:
    assert ledger.get_record_by_id("AUDIT-NOPE") is None
    ok, msg = ledger.verify_integrity("AUDIT-NOPE")
    assert ok is False and "not found" in msg.lower()


# --- legacy rows -------------------------------------------------------------------------------


def test_legacy_rows_are_unverifiable_never_verified(db_url: str, ledger: AuditLedger) -> None:
    _sql(
        db_url,
        "INSERT INTO audit_records (record_id, project_id, timestamp, git_commit_sha, "
        "contract_version, engine_version, methodology_version, boundary_geometry_hash, "
        "input_files_hashes, dataset_versions_hashes, analytical_parameters, "
        "intermediate_hashes, final_findings, report_version, merkle_root_hash, "
        "deterministic_reproducible, record_kind) VALUES ('AUDIT-OLD', 'legacy', "
        "'2026-11-09 08:00:00', 'x', '1', '1', 'm', 'h', '{}', '{}', '{}', '{}', '{}', "
        "'2.0-verified', 'sha256:" + "00" * 32 + "', TRUE, 'assessment')",
    )
    result = ledger.verify_project("legacy")
    assert result.status == STATUS_LEGACY
    assert result.record_count == 0 and result.legacy_record_count == 1
    assert ledger.verify_integrity("AUDIT-OLD")[0] is False


# --- persistence and concurrency ---------------------------------------------------------------


def test_restart_reloads_history_and_continues_the_chain(db_url: str) -> None:
    first = _ledger(db_url)
    ids = _add(first, "p8", 2)
    del first  # "restart": a brand-new ledger, engine and session factory
    second = _ledger(db_url)
    assert [r.record_id for r in second.get_records("p8")] == ids
    assert second.verify_project("p8").status == STATUS_VERIFIED
    (third,) = _add(second, "p8")
    assert second.get_record_by_id(third).sequence == 3  # type: ignore[union-attr]
    assert _ledger(db_url).verify_project("p8").record_count == 3


def test_concurrent_writes_to_one_project_keep_a_single_chain(db_url: str) -> None:
    ledger = _ledger(db_url)

    def job(i: int) -> str:
        return ledger.record_assessment("shared", GEO, {"i": i}, {"att": i}).record_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(job, range(24)))
    assert len(set(ids)) == 24
    result = _ledger(db_url).verify_project("shared")
    assert result.status == STATUS_VERIFIED
    assert result.record_count == 24 and result.head_sequence == 24


def test_concurrent_writers_in_separate_ledgers(db_url: str) -> None:
    """Two processes (separate ledger objects) racing on the same project must not fork it."""

    def job(i: int) -> str:
        return _ledger(db_url).record_assessment("raced", GEO, {"i": i}, {"x": i}).record_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        ids = list(pool.map(job, range(12)))
    assert len(set(ids)) == 12
    assert _ledger(db_url).verify_project("raced").status == STATUS_VERIFIED


# --- report association --------------------------------------------------------------------------


def test_report_is_bound_to_the_ledger_by_content_hash(ledger: AuditLedger) -> None:
    _add(ledger, "p9")
    report = b"PK\x03\x04 pretend zip bytes"
    seal = ledger.record_report_seal(
        "p9", report_kind="technical_dossier", content=report, boundary_geometry_hash="h"
    )
    assert seal.record_kind == "report.sealed" and seal.sequence == 2
    assert seal.final_findings["report_sha256"] == compute_sha256(report)

    ok, _ = ledger.verify_report(seal.record_id, report)
    assert ok is True
    ok, msg = ledger.verify_report(seal.record_id, report + b"x")
    assert ok is False and "does not match" in msg
    ok, _ = ledger.verify_report(ledger.get_records("p9")[0].record_id, report)
    assert ok is False  # an assessment record seals no report


def test_report_verification_fails_once_the_ledger_is_tampered(
    db_url: str, ledger: AuditLedger
) -> None:
    ids = _add(ledger, "p10")
    report = b"bytes"
    seal = ledger.record_report_seal(
        "p10", report_kind="technical_dossier", content=report, boundary_geometry_hash="h"
    )
    _sql(db_url, "UPDATE audit_records SET git_commit_sha='forged' WHERE record_id = :r", r=ids[0])
    ok, msg = _ledger(db_url).verify_report(seal.record_id, report)
    assert ok is False and "TAMPERING" in msg


def test_deleting_the_sealing_record_is_visible_to_a_holder_of_the_report(
    db_url: str, ledger: AuditLedger
) -> None:
    _add(ledger, "p11")
    seal = ledger.record_report_seal(
        "p11", report_kind="technical_dossier", content=b"r", boundary_geometry_hash="h"
    )
    _sql(db_url, "DELETE FROM audit_records WHERE record_id = :r", r=seal.record_id)
    ok, msg = _ledger(db_url).verify_report(seal.record_id, b"r")
    assert ok is False and "not found" in msg


# --- reproducibility ---------------------------------------------------------------------------


def test_reproducibility_compares_only_shared_findings(ledger: AuditLedger) -> None:
    rec = ledger.record_assessment("p12", GEO, {}, {"att": 0.5, "p": 0.01})
    assert ledger.verify_reproducibility(rec.record_id, {"att": 0.5, "p": 0.01}) is True
    assert ledger.verify_reproducibility(rec.record_id, {"att": 0.6}) is False
    assert ledger.verify_reproducibility(rec.record_id, {"unrelated": 1}) is False
    assert ledger.verify_reproducibility("AUDIT-NOPE", {"att": 0.5}) is False


def test_in_memory_ledger_still_chains_and_verifies() -> None:
    mem = AuditLedger(session_factory=None)
    mem._explicit_factory = None
    # no DATABASE_URL in this process configuration is not guaranteed, so force memory mode
    mem._factory = lambda: None  # type: ignore[method-assign]
    mem.record_assessment("m", GEO, {}, {"a": 1})
    mem.record_assessment("m", GEO, {}, {"a": 2})
    assert mem.verify_project("m").status == STATUS_VERIFIED
    assert mem.durable is False


@pytest.fixture(autouse=True)
def _no_ambient_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests pass an explicit session factory; the global ledger must not reach a real DB."""
    from groundtruth.platform.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", None)
    yield
