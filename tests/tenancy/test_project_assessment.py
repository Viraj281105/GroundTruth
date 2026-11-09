"""Task 8A (platform half): the adapter that feeds real artifacts to the assessment engine."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from groundtruth.data_access.aoi_pipeline import AnnualObservationRecord
from groundtruth.platform.projects import assessment as adapter
from groundtruth.platform.projects.assessment import (
    build_project_assessment,
    coverage_by_year,
    dedupe_years,
)
from groundtruth.platform.projects.data import ObservationsResult, load_observations
from groundtruth.platform.store.models import ProjectRow

REPO = Path(__file__).resolve().parents[2]
REAL_DATA = REPO / "data"
REAL_STAC = REAL_DATA / "processed" / "stac_cache"
REAL_CLIMATE = REAL_DATA / "processed" / "climate_cache" / "kariba_chirps_climate.json"
KARIBA_BOUNDARY = REPO / "cases" / "boundaries" / "kariba-redd.geojson"
ABSENT = Path("/nonexistent-data-dir")


def _project(
    case_id: str | None = "kariba-redd",
    *,
    boundary: Path | None = None,
    data_mode: str = "observed",
) -> ProjectRow:
    return ProjectRow(
        id=str(uuid.uuid4()),
        slug=f"p-{uuid.uuid4().hex[:8]}",
        organization_id=str(uuid.uuid4()),
        case_id=case_id,
        name="Test project",
        country="ZZ",
        ecosystem="forest",
        intervention="restoration",
        treatment_start_year=2015,
        boundary_path=str(boundary) if boundary else None,
        boundary_sha256=hashlib.sha256(boundary.read_bytes()).hexdigest() if boundary else None,
        data_mode=data_mode,
        created_at=datetime.now(UTC),
    )


def _rec(year: int, n_valid: int | None, clear: float = 0.9) -> AnnualObservationRecord:
    return AnnualObservationRecord(
        year=year,
        indicator="ndvi",
        value=0.4 + year * 0.0001 * (n_valid or 1),
        n_valid_observations=1,
        clear_pixel_fraction=clear,
        n_scenes=1,
        scene_ids=("s",),
        acquisition_dates=(f"{year}-07-01",),
        sensor="sentinel2",
        scenes_sha256="a" * 64,
        n_valid_pixels=n_valid,
    )


# --- coverage (ruling 1) ----------------------------------------------------------------------


def test_coverage_from_valid_pixels_and_resolution() -> None:
    # A 2 km x 2 km boundary (about 4 km2); 100 valid pixels of 100 m = 1 km2 -> 25%.
    deg = 2000.0 / 111_320.0
    boundary = Polygon(
        [(30.0, -16.0), (30.0 + deg, -16.0), (30.0 + deg, -16.0 + deg), (30.0, -16.0 + deg)]
    )
    area_km2 = adapter.boundary_area_m2(boundary) / 1e6
    cov = coverage_by_year(boundary, 100.0, [_rec(2020, 100), _rec(2021, 200)])
    assert cov[2020] == pytest.approx(100 * 0.01 / area_km2 * 100.0, rel=1e-9)
    assert cov[2020] == pytest.approx(25.0, rel=0.06)  # equal-area vs naive km/deg
    assert cov[2021] == pytest.approx(50.0, rel=0.06)


def test_missing_resolution_or_pixels_means_unknown_coverage() -> None:
    boundary = Polygon([(30.0, -16.0), (30.1, -16.0), (30.1, -15.9), (30.0, -15.9)])
    assert coverage_by_year(boundary, None, [_rec(2020, 100)]) == {}
    assert coverage_by_year(boundary, 100.0, [_rec(2020, None)]) == {}
    assert adapter.grid_resolution_m({}) is None
    assert adapter.grid_resolution_m({"raster_grid": {"resolution_m": 100.0}}) == 100.0
    assert adapter.grid_resolution_m({"scenes_metadata": [{"resolution_m": 10.0}]}) == 10.0


def test_unreadable_boundary_means_unknown_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    real_assess = adapter.assess

    class _Bundle:
        bbox = (0.0, 0.0, 1.0, 1.0)
        records = tuple(_rec(y, 100) for y in (2018, 2019, 2020))

    def spy(inputs):  # type: ignore[no-untyped-def]
        seen["coverage"] = dict(inputs.coverage_pct)
        return real_assess(inputs)

    monkeypatch.setattr(adapter, "assess", spy)
    monkeypatch.setattr(
        adapter,
        "load_observations",
        lambda project, ind, *, data_dir=None: ObservationsResult("available", None, _Bundle()),  # type: ignore[arg-type]
    )
    project = _project("no-such-case")
    project.boundary_path = "/does/not/exist.geojson"
    build_project_assessment(project, data_dir=ABSENT)
    assert seen["coverage"] == {}


# --- duplicate years (ruling 2) ---------------------------------------------------------------


def test_duplicate_years_keep_most_valid_pixels() -> None:
    kept = dedupe_years([_rec(2020, 5), _rec(2020, 50), _rec(2020, 7), _rec(2019, None)])
    assert [(r.year, r.n_valid_pixels) for r in kept] == [(2019, None), (2020, 50)]


def test_adapter_survives_duplicate_year_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Bundle:
        bbox = (0.0, 0.0, 1.0, 1.0)
        records = tuple(_rec(y, 100) for y in (2018, 2019, 2019, 2020, 2021))

    monkeypatch.setattr(
        adapter,
        "load_observations",
        lambda project, ind, *, data_dir=None: ObservationsResult("available", None, _Bundle()),  # type: ignore[arg-type]
    )
    result = build_project_assessment(_project("dup"), data_dir=ABSENT)
    assert 0 <= result.level <= 5


# --- unavailable data never raises -------------------------------------------------------------


def test_project_without_data_is_level_0_with_reasons(tmp_path: Path) -> None:
    for project in (_project(None), _project("unknown-case")):
        result = build_project_assessment(project, data_dir=tmp_path)
        assert result.level == 0
        assert result.level_name == "Not assessable"
        assert result.dimensions
        assert result.attribution.verdict == "Inconclusive"
        assert all(d.finding for d in result.dimensions)
    assert not (tmp_path / "processed").exists()


def test_simulated_project_is_labelled_and_never_fabricated(tmp_path: Path) -> None:
    result = build_project_assessment(_project(None, data_mode="simulated"), data_dir=tmp_path)
    assert result.data_mode == "simulated"
    assert result.simulated_banner
    assert result.level == 0


def test_corrupt_cache_still_yields_assessment(tmp_path: Path) -> None:
    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    (cache / "kariba-redd__ndvi.json").write_text("{oops", encoding="utf-8")
    climate = tmp_path / "processed" / "climate_cache"
    climate.mkdir(parents=True)
    (climate / "kariba_chirps_climate.json").write_text("not json", encoding="utf-8")
    result = build_project_assessment(_project(), data_dir=tmp_path)
    assert result.level == 0
    assert result.dimensions


def test_tampered_copy_of_real_cache_still_yields_assessment(tmp_path: Path) -> None:
    src = REAL_STAC / "kariba-redd__ndvi.json"
    if not src.exists():
        pytest.skip("real Sentinel-2 cache is git-ignored and absent here")
    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["records"][0]["scene_ids"] = ["tampered"]
    (cache / "kariba-redd__ndvi.json").write_text(json.dumps(raw), encoding="utf-8")
    result = build_project_assessment(_project(boundary=KARIBA_BOUNDARY), data_dir=tmp_path)
    assert result.level == 0  # the provenance check rejects the tampered bundle
    assert result.dimensions and all(d.finding for d in result.dimensions)


# --- Kariba (real data) ------------------------------------------------------------------------


def _require_kariba() -> Path:
    if not (REAL_STAC / "kariba-redd__ndvi.json").exists() or not REAL_CLIMATE.exists():
        pytest.skip("real Kariba caches (git-ignored) are absent here")
    return REAL_DATA


def test_kariba_assessment_level_2() -> None:
    data_dir = _require_kariba()
    result = build_project_assessment(_project(boundary=KARIBA_BOUNDARY), data_dir=data_dir)

    assert result.level == 2
    dims = list(result.dimensions)
    assert len({d.id for d in dims}) == len(dims)
    for idx, limitation in (
        (0, "weak_statistical_power"),
        (1, "missing_data"),
        (5, "missing_data"),
    ):
        assert dims[idx].status == "Insufficient evidence", dims[idx].id
        assert dims[idx].limitation == limitation, dims[idx].id
    climate_dim = dims[2]
    assert climate_dim.known and climate_dim.facts.get("per_year")
    assert result.attribution.verdict == "Inconclusive"
    assert result.attribution.limitation == "missing_data"
    ids = {r.id for r in result.recommendations}
    assert {"acquire_more_observations", "acquire_reference_series"} <= ids
    for rec in result.recommendations:
        assert rec.rationale.strip() and rec.evidence_refs, rec.id
    blob = repr(result).lower()
    for word in ("carbon", "biomass", "tco2"):
        assert word not in blob


def test_kariba_coverage_is_partial_and_flags_boundary_review() -> None:
    data_dir = _require_kariba()
    project = _project(boundary=KARIBA_BOUNDARY)
    bundle = load_observations(project, "ndvi", data_dir=data_dir).bundle
    assert bundle is not None
    boundary = adapter._read_boundary(project)
    assert boundary is not None
    res = adapter.grid_resolution_m(bundle.provenance.parameters)
    cov = coverage_by_year(boundary, res, dedupe_years(bundle.records))
    assert cov and all(28.0 <= v <= 29.0 for v in cov.values()), cov
    result = build_project_assessment(project, data_dir=data_dir)
    ids = {r.id for r in result.recommendations}
    assert "review_boundary_or_period" in ids  # coverage below 50%


def test_kariba_missing_climate_degrades_to_level_1(tmp_path: Path) -> None:
    _require_kariba()
    shutil.copytree(REAL_STAC, tmp_path / "processed" / "stac_cache")
    cdir = tmp_path / "processed" / "climate_cache"
    cdir.mkdir(parents=True)
    (cdir / REAL_CLIMATE.name).write_text("{}", encoding="utf-8")
    result = build_project_assessment(_project(boundary=KARIBA_BOUNDARY), data_dir=tmp_path)
    assert result.level == 1
