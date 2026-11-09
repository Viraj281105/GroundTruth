"""WP-E: project documents (upload, list, download, extraction, soft delete) and their surfaces."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "auth"))
from authhelpers import ORIGIN
from world import GRANTED_CASE, World

from groundtruth.platform.api.app import app
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import documents as docs
from groundtruth.platform.storage.blob_store import StorageTier
from groundtruth.platform.store.models import AuditEventRow, ProjectDocumentRow

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

KARIBA = GRANTED_CASE
TEXT = (
    b"The project protects 12,500 hectares and reduced deforestation by 40 percent "
    b"against the baseline.\n"
)
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def _doc_store(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "project_documents_dir", tmp_path / "docs")
    monkeypatch.setattr(get_settings(), "project_document_max_bytes", 10 * 1024 * 1024)


def _url(project: str = KARIBA, *rest: str) -> str:
    return "/".join([f"/projects/{project}/documents", *rest])


def _up(
    client: TestClient, name: str, data: bytes, project: str = KARIBA, ctype: str = "text/plain"
):
    return client.post(_url(project), files={"file": (name, data, ctype)})


def _events(world: World, action: str) -> list[AuditEventRow]:
    with world.sessions() as db:
        return list(
            db.execute(select(AuditEventRow).where(AuditEventRow.action == action)).scalars()
        )


def test_upload_text_list_download_hash(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    r = _up(ref, "design.txt", TEXT)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sha256"] == hashlib.sha256(TEXT).hexdigest()
    assert body["size_bytes"] == len(TEXT)
    assert body["status"] == "text_extracted"
    assert body["extracted_claims_count"] >= 1
    assert body["extracted_text_chars"] == len(TEXT.decode())
    assert "verified" not in body["status"]

    listing = ref.get(_url()).json()
    assert [d["id"] for d in listing["documents"]] == [body["id"]]
    assert listing["counts"] == {"text_extracted": 1}
    assert ".pdf" in listing["allowed_extensions"]

    dl = ref.get(_url(KARIBA, body["id"], "download"))
    assert dl.status_code == 200
    assert dl.content == TEXT
    assert dl.headers["content-type"].startswith("text/plain")
    assert "attachment" in dl.headers["content-disposition"]
    assert dl.headers["x-content-type-options"] == "nosniff"

    ex = ref.get(_url(KARIBA, body["id"], "extraction"))
    assert ex.status_code == 200
    out = ex.json()
    assert out["claims_count"] == body["extracted_claims_count"] >= 1
    assert out["verified"] is False
    first = out["candidates"][0]
    assert TEXT.decode()[first["start"] : first["end"]] == first["quote"]


def test_pdf_without_parser_is_extraction_unsupported(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    r = _up(ref, "plan.pdf", PDF, ctype="application/pdf")
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "extraction_unsupported"
    assert body["extracted_claims_count"] is None and body["extracted_text_chars"] is None
    assert "stored only" in body["status_detail"].lower()
    ex = ref.get(_url(KARIBA, body["id"], "extraction"))
    assert ex.status_code == 409
    assert ex.json()["detail"]["code"] == "extraction_not_available"
    assert ref.get(_url(KARIBA, body["id"], "download")).content == PDF


def test_csv_is_stored_not_parsed(tenant_world: World) -> None:
    r = _up(tenant_world.client("ref"), "baseline.csv", b"year,ha\n2019,100\n", ctype="text/csv")
    assert r.status_code == 201 and r.json()["status"] == "extraction_unsupported"


def test_rejections(tenant_world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    ref = tenant_world.client("ref")
    assert _up(ref, "empty.txt", b"").status_code == 422
    bad = _up(ref, "run.exe", b"MZ\x90\x00", ctype="application/octet-stream")
    assert bad.status_code == 415
    assert "not accepted" in bad.json()["detail"]["message"]
    assert _up(ref, "noext", b"hello").status_code == 415
    fake_pdf = _up(ref, "fake.pdf", b"not a pdf at all", ctype="application/pdf")
    assert fake_pdf.status_code == 422
    assert _up(ref, "bin.txt", b"abc\x00def").status_code == 422
    monkeypatch.setattr(get_settings(), "project_document_max_bytes", 64)
    big = _up(ref, "big.txt", b"x" * 65)
    assert big.status_code == 413
    assert _up(ref, "ok.txt", b"x" * 64).status_code == 201
    assert ref.get(_url()).json()["counts"] == {"text_extracted": 1}  # rejects left nothing


def test_filename_traversal_is_neutralised(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    r = _up(ref, "../../etc/passwd.txt", b"hello baseline")
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "passwd.txt"
    r2 = _up(ref, "..\\..\\windows\\evil.md", b"hello")
    assert r2.json()["filename"] == "evil.md"
    with tenant_world.sessions() as db:
        rows = list(db.execute(select(ProjectDocumentRow)).scalars())
    for row in rows:  # the key is server-generated, never the file name
        assert ".." not in row.storage_key and "passwd" not in row.storage_key
        assert row.storage_key == f"project-documents/{row.project_id}/{row.id}"
    root = get_settings().project_documents_dir.resolve()
    for p in root.rglob("*"):
        assert root in p.resolve().parents or p.resolve() == root
    assert not (root.parent / "etc").exists()


def test_cross_tenant_isolation(tenant_world: World) -> None:
    ref, out = tenant_world.client("ref"), tenant_world.client("outsider")
    doc = _up(ref, "design.txt", TEXT).json()["id"]
    assert out.get(_url()).status_code == 404
    assert out.get(_url(KARIBA, doc, "download")).status_code == 404
    assert out.get(_url(KARIBA, doc, "extraction")).status_code == 404
    assert _up(out, "x.txt", b"hi").status_code == 404
    assert out.delete(_url(KARIBA, doc)).status_code == 404
    # a document id never resolves under another project the caller can see
    other = tenant_world.project_ids["mikoko-pamoja"]
    assert ref.get(_url(other, doc, "download")).status_code == 404
    assert ref.get(_url(KARIBA, doc, "download")).status_code == 200  # still intact


def test_view_and_contribute_grantees_cannot_upload_or_delete(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    doc = _up(ref, "design.txt", TEXT).json()["id"]
    for who in ("funder", "ngo", "auditor"):
        c = tenant_world.client(who)
        assert _up(c, "x.txt", b"hi").status_code == 403, who
        assert c.delete(_url(KARIBA, doc)).status_code == 403, who
    funder = tenant_world.client("funder")  # view-level: may read
    assert funder.get(_url()).status_code == 200
    assert funder.get(_url(KARIBA, doc, "download")).content == TEXT


def test_unauthenticated_is_401(tenant_world: World) -> None:
    anon = TestClient(app, base_url=ORIGIN)
    assert anon.get(_url()).status_code == 401
    assert anon.post(_url(), files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 401
    assert anon.get(_url(KARIBA, "x", "download")).status_code == 401
    assert anon.delete(_url(KARIBA, "x")).status_code == 401


def test_soft_delete_keeps_row_and_audit(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    doc = _up(ref, "design.txt", TEXT).json()["id"]
    assert ref.delete(_url(KARIBA, doc)).status_code == 204
    assert ref.get(_url()).json()["documents"] == []
    assert ref.get(_url(KARIBA, doc, "download")).status_code == 404
    assert ref.delete(_url(KARIBA, doc)).status_code == 404
    with tenant_world.sessions() as db:
        row = db.get(ProjectDocumentRow, doc)
        assert row is not None and row.deleted_at is not None  # row kept
        key = row.storage_key
    assert not docs.blob_store().exists(StorageTier.RAW_SOURCE, key)  # bytes removed
    assert len(_events(tenant_world, "document.delete")) == 1


def test_audit_events_written(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    body = _up(ref, "design.txt", TEXT).json()
    ref.get(_url(KARIBA, body["id"], "download"))
    up = _events(tenant_world, "document.upload")
    dl = _events(tenant_world, "document.download")
    assert len(up) == 1 and len(dl) == 1
    assert up[0].resource_id == body["id"]
    assert up[0].details["sha256"] == body["sha256"] and up[0].details["status"] == "text_extracted"
    assert up[0].outcome == "success" and up[0].actor_user_id == tenant_world.user_ids["ref"]


def test_persistence_across_new_sessions(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    body = _up(ref, "design.txt", TEXT).json()
    from groundtruth.platform.store.database import create_db_engine, create_session_factory

    with tenant_world.sessions() as db:
        url = str(db.get_bind().url)
    fresh = create_session_factory(create_db_engine(url))
    with fresh() as db:
        row = db.get(ProjectDocumentRow, body["id"])
        assert row is not None and row.sha256 == body["sha256"] and row.status == "text_extracted"
        data = docs.blob_store().get_bytes(StorageTier.RAW_SOURCE, row.storage_key)
    assert data == TEXT


def _zip(content: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_dossier_includes_documents_manifest(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    url = f"/projects/{KARIBA}/export/dossier"
    before = _zip(ref.get(url).content)
    assert "documents-manifest.json" not in before  # unchanged when there are no documents
    body = _up(ref, "design.txt", TEXT).json()
    files = _zip(ref.get(url).content)
    assert set(before) | {"documents-manifest.json"} == set(files)
    assert list(files)[-1] == "manifest.json"
    manifest = json.loads(files["manifest.json"])
    for entry in manifest["files"]:
        assert hashlib.sha256(files[entry["path"]]).hexdigest() == entry["sha256"]
    assert "documents-manifest.json" in [e["path"] for e in manifest["files"]]
    dm = json.loads(files["documents-manifest.json"])
    (entry,) = dm["documents"]
    assert entry["filename"] == "design.txt" and entry["sha256"] == body["sha256"]
    assert entry["size_bytes"] == len(TEXT) and entry["status"] == "text_extracted"
    assert ref.get(url).content == ref.get(url).content  # still deterministic


def test_evidence_inventory_lists_documents_and_next_steps(tenant_world: World) -> None:
    ref = tenant_world.client("ref")
    inv0 = ref.get(f"/projects/{KARIBA}/evidence-inventory").json()
    assert inv0["documents_count"] == 0 and inv0["documents"] == []
    assert any("No project documents" in m for m in inv0["missing_evidence"])
    _up(ref, "design.txt", TEXT)
    _up(ref, "plan.pdf", PDF, ctype="application/pdf")
    inv = ref.get(f"/projects/{KARIBA}/evidence-inventory").json()
    assert inv["documents_count"] == 2
    assert inv["documents_by_status"] == {"text_extracted": 1, "extraction_unsupported": 1}
    assert "documents" in inv["kinds"]
    assert not any("No project documents" in m for m in inv["missing_evidence"])
    assert inv["observation_ingestion"]["available"] is False
    # a view grantee gets the counts but not the file list
    fi = tenant_world.client("funder").get(f"/projects/{KARIBA}/evidence-inventory").json()
    assert fi["documents_count"] == 2 and "documents" not in fi


def test_user_project_without_observations_says_what_is_missing(
    tenant_world: World, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "cases_dir", tmp_path / "cases")
    out = tenant_world.client("outsider")
    square = {
        "type": "Polygon",
        "coordinates": [[[30, -1], [30.1, -1], [30.1, -0.9], [30, -0.9], [30, -1]]],
    }
    r = out.post(
        "/orgs/outsider-ngo/projects",
        data={
            "name": "Riverbank",
            "country": "Zambia",
            "ecosystem": "miombo",
            "intervention": "reforestation",
            "treatment_start_year": "2018",
        },
        files={"boundary": ("b.geojson", json.dumps(square).encode())},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    up = _up(out, "baseline.md", b"# Baseline\nArea is 300 hectares.\n", project=pid)
    assert up.status_code == 201
    inv = out.get(f"/projects/{pid}/evidence-inventory").json()
    assert inv["documents_count"] == 1 and inv["observation_ingestion"]["available"] is True
    assert "Request them from the Earth observation tab" in inv["observation_ingestion"]["message"]
    assert any("No satellite observations" in m for m in inv["missing_evidence"])
    assert not any("boundary" in m.lower() for m in inv["missing_evidence"])
    ready = out.get(f"/projects/{pid}/readiness").json()
    needs = " ".join(c["evidence_needed"] for c in ready["criteria"])
    assert "Earth observation tab" in needs
    assert ready["attribution_ready"] is False


def test_document_candidates_cover_every_statement_and_flag_overclaims() -> None:
    """Document extraction uses the same analyser as the public claims workbench."""
    from groundtruth.platform.projects.documents import claim_candidates

    text = (
        "The project restores 1,200 hectares of degraded dry forest. 85% of planted seedlings "
        "survived after 3 years. NDVI increased by 0.15 since 2021. The project has sequestered "
        "40,000 tCO2e and proves biodiversity has fully recovered."
    )
    cands = claim_candidates(text, "doc-1")
    assert len(cands) >= 4
    assert all(text[c["start"] : c["end"]] == c["quote"] for c in cands)  # verbatim spans
    kinds = {c["kind"] for c in cands}
    assert any("overclaim" in k or "biodiversity" in k or "recover" in k for k in kinds), kinds
