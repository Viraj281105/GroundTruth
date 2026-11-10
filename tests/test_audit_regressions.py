"""Regression tests for security, storage, context, and API hardening fixes."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundtruth.data_access.store import ParquetStore
from groundtruth.platform.api.app import app
from groundtruth.platform.api.ledger import MAX_REPORT_VERIFY_BYTES
from groundtruth.platform.intelligence.context import build_project_context
from groundtruth.platform.storage.blob_store import LocalStorageBackend, StorageTier
from groundtruth.platform.store.models import ProjectRow


def test_parquet_store_rejects_quote_and_sql_injection(tmp_path: Path) -> None:
    store = ParquetStore(tmp_path)
    for bad in ('foo"', 'foo" OR 1=1 --', "_internal", "../escape", "a;DROP TABLE b"):
        with pytest.raises(ValueError, match="invalid table name"):
            store.path(bad)
    assert store.path("valid-donors_01").name == "valid-donors_01.parquet"


def test_local_storage_backend_blocks_tier_escape(tmp_path: Path) -> None:
    store = LocalStorageBackend(tmp_path)
    with pytest.raises(ValueError, match="outside tier root"):
        store._resolve_path(StorageTier.RAW_SOURCE, "")
    resolved = store._resolve_path(StorageTier.RAW_SOURCE, "proj/doc.txt")
    assert resolved.is_relative_to((tmp_path / "raw").resolve())


def test_verify_report_rejects_oversized_upload(
    tenant_world, monkeypatch: pytest.MonkeyPatch
) -> None:
    from groundtruth.platform.api import ledger as ledger_api

    monkeypatch.setattr(ledger_api, "MAX_REPORT_VERIFY_BYTES", 64)
    ref = tenant_world.client("ref")
    pid = ref.get("/projects/kariba-redd").json()["id"]
    rid = ref.get("/projects/kariba-redd/export/dossier").headers["x-groundtruth-ledger-record"]

    res = ref.post(
        f"/projects/{pid}/ledger/verify-report",
        data={"record_id": rid},
        files={"file": ("big.zip", b"x" * 128, "application/zip")},
    )
    assert res.status_code == 413
    assert MAX_REPORT_VERIFY_BYTES >= 1024 * 1024


def test_extract_pdf_validates_payload_size_and_magic_header() -> None:
    client = TestClient(app)
    non_pdf = base64.b64encode(b"NOT_A_PDF").decode("ascii")
    res = client.post("/claims/extract-pdf", json={"file_base64": non_pdf, "filename": "a.pdf"})
    # Either 501 (pypdf optional dep absent) or 422 (magic header rejected when pypdf installed).
    assert res.status_code in (422, 501)


def test_verify_rejects_unknown_data_mode(tenant_world) -> None:
    ref = tenant_world.client("ref")
    res = ref.post("/cases/kariba-redd/verify", json={"data_mode": "made_up_mode"})
    assert res.status_code == 422


def test_intelligence_context_recognizes_text_extracted_documents(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from groundtruth.platform.auth.authz import ProjectLevel

    project = ProjectRow(
        id="p-ctx-1",
        slug="ctx-project",
        organization_id="o-ctx-1",
        case_id=None,
        name="Context Test Project",
        country="IN",
        ecosystem="forest",
        intervention="restoration",
        treatment_start_year=2022,
        data_mode="observed",
        created_at=datetime.now(UTC),
    )
    ctx = build_project_context(
        project,
        ProjectLevel.VIEW,
        tmp_path,
        documents=[{"id": "d1", "filename": "pdd.md", "status": "text_extracted"}],
    )
    assert ctx.sufficient is True
    assert any("text_extracted" in f.statement for f in ctx.facts)


def test_document_extraction_preserves_markdown_extension(
    tenant_world, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from groundtruth.platform.config import get_settings
    from groundtruth.platform.projects import documents as docs

    monkeypatch.setattr(get_settings(), "project_documents_dir", tmp_path / "docs")
    monkeypatch.setattr(get_settings(), "project_document_max_bytes", 10 * 1024 * 1024)

    md = b"We restored 150 hectares of native woodland between 2020 and 2023.\n"
    ref = tenant_world.client("ref")
    pid = tenant_world.project_ids["kariba-redd"]
    upload = ref.post(
        f"/projects/{pid}/documents",
        files={"file": ("design.md", md, "text/markdown")},
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]

    seen_exts: list[str] = []
    real_extract = docs.extract_text

    def spy_extract(ext: str, data: bytes):
        seen_exts.append(ext)
        return real_extract(ext, data)

    monkeypatch.setattr(docs, "extract_text", spy_extract)
    ext_res = ref.get(f"/projects/{pid}/documents/{doc_id}/extraction")
    assert ext_res.status_code == 200, ext_res.text
    assert seen_exts == [".md"]


def test_verify_projects_batch_matches_individual_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from groundtruth.platform.audit.ledger import AuditLedger
    from groundtruth.platform.config import get_settings

    monkeypatch.setattr(get_settings(), "database_url", "")
    ledger = AuditLedger()
    ledger.record_report_seal(
        "p1",
        report_kind="dossier",
        content=b"report-one",
        boundary_geometry_hash="sha256:p1",
    )
    ledger.record_report_seal(
        "p2",
        report_kind="dossier",
        content=b"report-two",
        boundary_geometry_hash="sha256:p2",
    )

    batch = ledger.verify_projects(["p1", "p2", "p3"])
    assert set(batch) == {"p1", "p2", "p3"}
    from dataclasses import replace

    for pid in ("p1", "p2", "p3"):
        single_v = ledger.verify_project(pid)
        single_recs = ledger.get_records(pid)
        batch_v, batch_recs = batch[pid]
        assert replace(batch_v, verified_at=single_v.verified_at) == single_v
        assert batch_recs == single_recs


def test_audit_throttled_prunes_cache_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from groundtruth.platform.audit import service as audit_svc

    monkeypatch.setattr(audit_svc, "_MAX_DENIED_CACHE", 4)
    monkeypatch.setattr(audit_svc, "_denied_last", {})
    for i in range(6):
        assert audit_svc.audit_throttled(f"actor-{i}", "authz.denied") is False
    assert len(audit_svc._denied_last) <= 4
