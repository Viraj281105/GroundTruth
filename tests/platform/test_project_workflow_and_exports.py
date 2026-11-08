"""Tests for restoration project AOI validation, synthetic labelling, and CSV/PDF exports."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from groundtruth.platform.api.exports import build_case_bundle, router
from groundtruth.platform.cases.creator import validate_project_aoi
from groundtruth.platform.reports.exporters import (
    CSV_COLUMNS,
    export_bundle_csv,
    export_bundle_pdf,
)


def test_validate_project_aoi_accepts_valid_geometries() -> None:
    valid_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [28.5, -17.5],
                [29.2, -17.5],
                [29.2, -18.1],
                [28.5, -18.1],
                [28.5, -17.5],
            ]
        ],
    }
    assert validate_project_aoi(valid_polygon) == valid_polygon

    valid_multipolygon = {
        "type": "MultiPolygon",
        "coordinates": [valid_polygon["coordinates"]],
    }
    assert validate_project_aoi(valid_multipolygon) == valid_multipolygon

    valid_feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": "Test AOI"},
                "geometry": valid_multipolygon,
            }
        ],
    }
    assert validate_project_aoi(valid_feature_collection) == valid_feature_collection


def test_validate_project_aoi_rejects_unclosed_ring() -> None:
    unclosed = {
        "type": "Polygon",
        "coordinates": [
            [
                [28.5, -17.5],
                [29.2, -17.5],
                [29.2, -18.1],
                [28.5, -18.1],
            ]
        ],
    }
    with pytest.raises(ValueError, match="not closed"):
        validate_project_aoi(unclosed)


def test_validate_project_aoi_rejects_out_of_bounds_coordinates() -> None:
    bad_lon = {
        "type": "Polygon",
        "coordinates": [
            [
                [195.0, -17.5],
                [196.0, -17.5],
                [196.0, -18.1],
                [195.0, -17.5],
            ]
        ],
    }
    with pytest.raises(ValueError, match="Longitude"):
        validate_project_aoi(bad_lon)

    bad_lat = {
        "type": "Polygon",
        "coordinates": [
            [
                [28.5, -95.0],
                [29.2, -95.0],
                [29.2, -18.1],
                [28.5, -95.0],
            ]
        ],
    }
    with pytest.raises(ValueError, match="Latitude"):
        validate_project_aoi(bad_lat)


def test_validate_project_aoi_rejects_degenerate_zero_area_polygon() -> None:
    collinear = {
        "type": "Polygon",
        "coordinates": [
            [
                [28.5, -17.5],
                [29.0, -17.5],
                [29.2, -17.5],
                [28.5, -17.5],
            ]
        ],
    }
    with pytest.raises(ValueError, match="zero-area"):
        validate_project_aoi(collinear)


def test_validate_project_aoi_rejects_empty_features() -> None:
    empty_fc = {"type": "FeatureCollection", "features": []}
    with pytest.raises(ValueError, match="non-empty 'features'"):
        validate_project_aoi(empty_fc)


def test_export_bundle_csv_headers_and_parseable_rows() -> None:
    bundle = build_case_bundle("kariba-redd", seed=20260101)
    csv_text = export_bundle_csv(bundle)

    lines = csv_text.splitlines()
    comment_lines = [line for line in lines if line.startswith("#")]
    data_lines = [line for line in lines if not line.startswith("#")]

    joined_comments = "\n".join(comment_lines)
    assert "# case_id: kariba-redd" in joined_comments
    assert "# is_simulated: True" in joined_comments
    assert "# data_origin: SYNTHETIC_SIMULATION" in joined_comments
    assert "# biomass_calibration_status: NOT_CALIBRATED" in joined_comments

    reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
    assert tuple(reader.fieldnames or ()) == CSV_COLUMNS

    rows = list(reader)
    assert len(rows) == len(bundle.items)
    for row, item in zip(rows, bundle.items, strict=True):
        assert row["id"] == item.id
        assert row["label"] == item.label
        assert row["value"] == item.rendered_value()
        assert row["provenance_fingerprint"] == item.provenance.fingerprint()
        assert len(row["provenance_fingerprint"]) == 16


def test_export_bundle_pdf_structure_and_content() -> None:
    bundle = build_case_bundle("kariba-redd", seed=20260101)
    pdf_bytes = export_bundle_pdf(bundle)

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
    assert b"\nxref\n" in pdf_bytes
    assert b"\ntrailer\n" in pdf_bytes
    assert b"\nstartxref\n" in pdf_bytes

    decoded = pdf_bytes.decode("utf-8", errors="replace")
    assert "GroundTruth Verification Screening Report" in decoded
    assert "kariba-redd" in decoded
    assert "SIMULATED / SYNTHETIC DATA RUN" in decoded
    assert "NOT CALIBRATED" in decoded
    if bundle.verdict is not None:
        assert bundle.verdict.label.value in decoded
        for caveat in bundle.verdict.caveats:
            # Verify first words of each caveat appear in the wrapped PDF text
            prefix = " ".join(caveat.split()[:4])
            assert prefix in decoded


def test_fastapi_export_endpoints() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    csv_resp = client.get("/cases/kariba-redd/export/csv")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert (
        csv_resp.headers["content-disposition"]
        == 'attachment; filename="kariba-redd-evidence.csv"'
    )
    assert csv_resp.headers["x-groundtruth-data-mode"] == "simulated"
    assert "# data_origin: SYNTHETIC_SIMULATION" in csv_resp.text

    pdf_resp = client.get("/cases/kariba-redd/export/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert (
        pdf_resp.headers["content-disposition"]
        == 'attachment; filename="kariba-redd-report.pdf"'
    )
    assert pdf_resp.headers["x-groundtruth-data-mode"] == "simulated"
    assert pdf_resp.content.startswith(b"%PDF-1.4")
    assert pdf_resp.content.rstrip().endswith(b"%%EOF")

    missing_resp = client.get("/cases/nonexistent-case-xyz/export/csv")
    assert missing_resp.status_code == 404
