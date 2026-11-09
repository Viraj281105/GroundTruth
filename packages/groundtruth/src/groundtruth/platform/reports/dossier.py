"""The technical dossier: a ZIP an auditor can check without trusting this server.

Everything in it is reshaped from provenance-checked artifacts and the same assessment the API
serves; nothing is computed here and no carbon or biomass value exists anywhere in it (the
pipeline is uncalibrated, R1). ``manifest.json`` lists the sha256 of every other file, so a
reader can confirm the files are the ones that were exported.

The archive is deterministic: fixed timestamps, a fixed file order, sorted JSON keys and no
generation time, so the same inputs always give the same bytes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from groundtruth.engine import ENGINE_VERSION
from groundtruth.platform.api.schemas import SIMULATED_NOTICE
from groundtruth.platform.projects import views
from groundtruth.platform.projects.assessment import INDICATORS, build_project_assessment
from groundtruth.platform.store.models import ProjectRow

DOSSIER_LEVEL = "audit"
"""Dossiers go to owner and audit levels only; both see every field, so the full views are used."""

_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
CONTENT_FILES: tuple[str, ...] = (
    "README.md",
    "assessment.json",
    "climate.csv",
    "evidence-inventory.json",
    "observations.csv",
    "provenance.json",
    "readiness.json",
)
"""Sorted by name; ``manifest.json`` follows them."""
MANIFEST = "manifest.json"
DOCUMENTS_MANIFEST = "documents-manifest.json"
CLAIMS_FILE = "claims.json"
INGESTIONS_FILE = "observation-ingestions.json"
"""Added (in sorted position) only when the project has uploaded documents."""


def _json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(["" if cell is None else cell for cell in row] for row in rows)
    return buffer.getvalue().encode("utf-8")


def _observations_csv(project: ProjectRow, data_dir: Path) -> tuple[bytes, dict[str, Any]]:
    rows: list[list[Any]] = []
    sources: dict[str, Any] = {}
    for indicator in INDICATORS:
        view = views.build_observations(project, indicator, DOSSIER_LEVEL, data_dir)
        sources[indicator] = {
            "status": view.status,
            "reason": view.reason,
            "unit_id": view.unit_id,
            "source": view.source,
        }
        for p in view.points:
            rows.append(
                [
                    indicator,
                    p.year,
                    p.value,
                    p.evidence_state,
                    p.sensor,
                    p.clear_pixel_fraction,
                    p.n_scenes,
                    p.aoi_coverage_pct,
                    "|".join(p.scene_ids or []),
                    p.scenes_sha256,
                ]
            )
    header = [
        "indicator",
        "year",
        "value",
        "evidence_state",
        "sensor",
        "clear_pixel_fraction",
        "n_scenes",
        "aoi_coverage_pct",
        "scene_ids",
        "scenes_sha256",
    ]
    return _csv(header, rows), sources


def _climate_csv(project: ProjectRow, data_dir: Path) -> tuple[bytes, dict[str, Any]]:
    view = views.build_climate(project, DOSSIER_LEVEL, data_dir)
    header = [
        "year",
        "valid_months",
        "is_complete_year",
        "annual_rainfall_mm",
        "rainfall_anomaly_mm",
        "rainfall_anomaly_z",
        "spi_12",
        "drought_classification",
        "mean_temp_c",
    ]
    rows = [
        [
            y.year,
            y.valid_months,
            y.is_complete_year,
            y.annual_rainfall_mm,
            y.rainfall_anomaly_mm,
            y.rainfall_anomaly_z,
            y.spi_12,
            y.drought_classification,
            y.mean_temp_c,
        ]
        for y in view.years
    ]
    meta = {
        "status": view.status,
        "reason": view.reason,
        "bundle_sha256": view.bundle_sha256,
        "sources": [s.model_dump(mode="json") for s in view.sources],
        "missing_months": view.missing_months,
    }
    return _csv(header, rows), meta


def _readme(
    project: ProjectRow,
    assessment: Any,
    simulated: bool,
    has_documents: bool = False,
    has_claims: bool = False,
    has_ingestions: bool = False,
) -> bytes:
    a = assessment.attribution
    lines = [
        f"# Technical dossier: {project.name}",
        "",
        f"Project: `{project.slug}` ({project.country}, {project.ecosystem}, "
        f"{project.intervention}, intervention from {project.treatment_start_year}).",
        f"Data mode: **{views.data_mode_of(project)}**.",
        f"Assessment level: **{assessment.level} - {assessment.level_name}** "
        f"(evidence confidence: {assessment.evidence_confidence}).",
        "",
    ]
    if simulated:
        lines += [f"> **{SIMULATED_NOTICE}**", ""]
    lines += [
        "## Limitations",
        "",
        "- This dossier is monitoring evidence only. It describes what satellite and climate "
        "records show for the project area; it is not a verification of any claim.",
        f"- Attribution status: **{a.verdict}** (limitation: {a.limitation}). {a.finding}",
        "- Observed change is not causal effect. Read the attribution status before reading any "
        "trend as an effect of the intervention.",
        "- The pipeline is uncalibrated: carbon not estimated. No carbon or biomass quantity "
        "appears in any file, and none may be inferred from a vegetation index.",
        "- Missing evidence is reported as unavailable, never filled in.",
        "",
        "## Files",
        "",
        "| File | Contents |",
        "| --- | --- |",
        "| `assessment.json` | The eight-dimension assessment, with evidence references. |",
        "| `climate.csv` | Annual climate series (blank when none was ingested). |",
        "| `evidence-inventory.json` | What evidence exists, with scene checksums. |",
        "| `observations.csv` | Annual vegetation-index observations, all indicators. |",
        "| `provenance.json` | Sources, checksums and engine version. |",
        "| `readiness.json` | Criteria for attempting causal attribution. |",
        *(
            [
                f"| `{DOCUMENTS_MANIFEST}` | Names, sizes, sha256 and processing status of the "
                "uploaded project documents (the documents themselves are not included; "
                "status is storage/extraction status, never verification). |"
            ]
            if has_documents
            else []
        ),
        *(
            [
                f"| `{CLAIMS_FILE}` | Claims a person chose to check, each with the document wording it "
                "came from, what was tested, and how it compares with the evidence on file. A "
                "comparison, never a verification; claims about survival, carbon or biodiversity "
                "are listed as insufficiently evidenced with the reason. |"
            ]
            if has_claims
            else []
        ),
        *(
            [
                f"| `{INGESTIONS_FILE}` | Satellite-data requests for this project: parameters, "
                "status, per-year scenes and coverage, stored-file hashes and ledger record id. |"
            ]
            if has_ingestions
            else []
        ),
        f"| `{MANIFEST}` | sha256 of every other file, in the order listed. |",
        "",
        "To check an export, hash each file and compare it with `manifest.json`.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _documents_manifest(documents: list[dict[str, Any]]) -> bytes:
    return _json(
        {
            "algorithm": "sha256",
            "note": "Stored-document manifest. Status is processing status only; no document "
            "is verified evidence of any claim.",
            "documents": [
                {
                    "id": d["id"],
                    "filename": d["filename"],
                    "content_type": d["content_type"],
                    "size_bytes": d["size_bytes"],
                    "sha256": d["sha256"],
                    "uploaded_at": d["uploaded_at"].isoformat()
                    if hasattr(d["uploaded_at"], "isoformat")
                    else d["uploaded_at"],
                    "status": d["status"],
                    "extracted_claims_count": d["extracted_claims_count"],
                }
                for d in sorted(documents, key=lambda d: (str(d["uploaded_at"]), d["id"]))
            ],
        }
    )


def build_dossier(
    project: ProjectRow,
    *,
    data_dir: Path,
    documents: list[dict[str, Any]] | None = None,
    claims: list[dict[str, Any]] | None = None,
    ingestions: list[dict[str, Any]] | None = None,
) -> bytes:
    """The dossier ZIP for ``project`` as bytes. Same inputs always give the same bytes.

    ``documents`` (``projects.documents.document_dict`` items) adds ``documents-manifest.json``
    when non-empty; ``claims`` (``claims_service.report_items``) adds ``claims.json`` and
    ``ingestions`` (``ingestion.report_item``) adds ``observation-ingestions.json``.
    """
    docs = documents or []
    claim_items = claims or []
    ingestion_items = ingestions or []
    readiness = views.build_readiness(project, DOSSIER_LEVEL, data_dir)
    inventory = views.build_inventory(project, DOSSIER_LEVEL, data_dir, docs)
    assessment = build_project_assessment(project, data_dir=data_dir)
    assessment_view = views.build_assessment(assessment, project, DOSSIER_LEVEL)
    observations, obs_meta = _observations_csv(project, data_dir)
    climate, climate_meta = _climate_csv(project, data_dir)
    simulated = assessment_view.data_mode == "simulated"
    provenance = {
        "project": {
            "id": project.id,
            "slug": project.slug,
            "name": project.name,
            "case_id": project.case_id,
            "treatment_start_year": project.treatment_start_year,
            "boundary_sha256": project.boundary_sha256,
        },
        "data_mode": assessment_view.data_mode,
        "engine_version": ENGINE_VERSION,
        "observations": obs_meta,
        "climate": climate_meta,
    }
    files: dict[str, bytes] = {
        "README.md": _readme(
            project, assessment, simulated, bool(docs), bool(claim_items), bool(ingestion_items)
        ),
        "assessment.json": _json(assessment_view.model_dump(mode="json")),
        "climate.csv": climate,
        "evidence-inventory.json": _json(inventory.model_dump(mode="json")),
        "observations.csv": observations,
        "provenance.json": _json(provenance),
        "readiness.json": _json(readiness.model_dump(mode="json")),
    }
    names = list(CONTENT_FILES)
    if docs:
        files[DOCUMENTS_MANIFEST] = _documents_manifest(docs)
        names = sorted([*names, DOCUMENTS_MANIFEST])
    if claim_items:
        files[CLAIMS_FILE] = _json(
            {
                "note": (
                    "Claims are what someone said, not findings. Each outcome compares the claim "
                    "with the evidence on file; UNVERIFIED means the evidence needed is missing or "
                    "of a kind that cannot establish it, not that the claim is false."
                ),
                "claims": claim_items,
            }
        )
        names = sorted([*names, CLAIMS_FILE])
    if ingestion_items:
        files[INGESTIONS_FILE] = _json({"requests": ingestion_items})
        names = sorted([*names, INGESTIONS_FILE])
    files[MANIFEST] = _json(
        {
            "algorithm": "sha256",
            "files": [
                {"path": name, "sha256": hashlib.sha256(files[name]).hexdigest()} for name in names
            ],
        }
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in (*names, MANIFEST):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
    return out.getvalue()
