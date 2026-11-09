"""Tests for Persistent Audit Ledger, Tamper Detection, and Process Restart Durability.

Verifies:
- Audit records persist to SQLite/PostgreSQL database.
- Server restart (in-memory cache eviction) successfully reloads full history.
- Cryptographic Merkle tree recalculation detects tampering if parameters/findings are altered.
- Non-existent records return None and fail closed.
- Concurrent multi-threaded recordings execute safely without collision.
"""

from __future__ import annotations

import concurrent.futures

import pytest

from groundtruth.platform.audit.ledger import (
    AuditLedger,
)


@pytest.fixture
def clean_ledger(tmp_path, monkeypatch) -> AuditLedger:
    """Create an isolated ledger instance for testing with an isolated database."""
    from groundtruth.platform.config import get_settings
    from groundtruth.platform.store.database import create_db_engine
    from groundtruth.platform.store.models import Base

    db_path = tmp_path / "test_audit.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setattr(get_settings(), "database_url", db_url)

    engine = create_db_engine(db_url)
    Base.metadata.create_all(engine)

    ledger = AuditLedger()
    return ledger


def test_record_persisted_and_reloaded_from_db(clean_ledger: AuditLedger) -> None:
    """Test that records are persisted and survive cache clearing (restart simulation)."""
    project_id = "test-project-persistence-01"
    geo = {
        "type": "Polygon",
        "coordinates": [
            [[30.0, -20.0], [31.0, -20.0], [31.0, -21.0], [30.0, -21.0], [30.0, -20.0]]
        ],
    }
    params = {"seed": 42, "sutva_km": 15.0, "caliper": 0.25}
    findings = {"att": 0.045, "p_val": 0.012}

    # Record assessment
    record = clean_ledger.record_assessment(
        project_id=project_id,
        boundary_geojson=geo,
        analytical_parameters=params,
        final_findings=findings,
    )
    assert record.record_id.startswith(f"AUDIT-{project_id.upper()}")
    assert record.merkle_root_hash.startswith("sha256:")

    # SIMULATE SERVER RESTART: wipe the in-memory dictionary
    clean_ledger._records.clear()
    assert project_id not in clean_ledger._records

    # Retrieve from database
    reloaded = clean_ledger.get_records(project_id)
    assert len(reloaded) >= 1
    found = next((r for r in reloaded if r.record_id == record.record_id), None)
    assert found is not None
    assert found.merkle_root_hash == record.merkle_root_hash
    assert found.analytical_parameters["seed"] == 42
    assert found.final_findings["att"] == 0.045


def test_cryptographic_tamper_detection(clean_ledger: AuditLedger) -> None:
    """Test that tampering with stored findings or Merkle root is immediately detected."""
    project_id = "test-tamper-02"
    geo = {
        "type": "Polygon",
        "coordinates": [[[20.0, 0.0], [21.0, 0.0], [21.0, 1.0], [20.0, 1.0], [20.0, 0.0]]],
    }
    params = {"seed": 99, "sutva_km": 20.0}
    findings = {"att": 0.038, "p_val": 0.002}

    record = clean_ledger.record_assessment(
        project_id=project_id,
        boundary_geojson=geo,
        analytical_parameters=params,
        final_findings=findings,
    )

    # 1. Untampered record verifies successfully
    is_valid, msg = clean_ledger.verify_integrity(record.record_id)
    assert is_valid is True
    assert "verified" in msg.lower()

    # 2. Tamper with record in database (e.g. inflate att from 0.038 to 0.150)
    from groundtruth.platform.audit.ledger import _get_db_session
    from groundtruth.platform.store.models import AuditRecordRow

    session = _get_db_session()
    if session is not None:
        try:
            row = session.get(AuditRecordRow, record.record_id)
            if row:
                row.final_findings = {"att": 0.150, "p_val": 0.0001}  # TAMPERED!
                session.commit()
        finally:
            session.close()

    # Also wipe in-memory cache to force reloading from tampered DB row
    clean_ledger._records.clear()

    # Verification must catch the discrepancy
    is_valid, msg = clean_ledger.verify_integrity(record.record_id)
    assert is_valid is False
    assert "TAMPERING DETECTED" in msg


def test_missing_audit_record(clean_ledger: AuditLedger) -> None:
    """Test lookup of non-existent audit record returns None or fails closed."""
    non_existent = clean_ledger.get_record_by_id("AUDIT-NON-EXISTENT-999")
    assert non_existent is None

    is_valid, msg = clean_ledger.verify_integrity("AUDIT-NON-EXISTENT-999")
    assert is_valid is False
    assert "not found" in msg.lower()


def test_concurrent_audit_recording(clean_ledger: AuditLedger) -> None:
    """Test thread-safety under concurrent write requests."""
    project_id = "test-concurrent-03"

    def record_job(idx: int) -> str:
        rec = clean_ledger.record_assessment(
            project_id=f"{project_id}-{idx % 3}",
            boundary_geojson={"type": "Point", "coordinates": [idx, idx]},
            analytical_parameters={"job_idx": idx},
            final_findings={"att": idx * 0.01},
        )
        return rec.record_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(record_job, i) for i in range(24)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 24
    assert len(set(results)) == 24  # All 24 records have unique Merkle roots
