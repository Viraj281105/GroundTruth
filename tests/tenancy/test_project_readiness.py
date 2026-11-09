"""Task 8: project readiness computed from real artifacts (no hand-typed numbers)."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from groundtruth.contracts.provenance import Provenance
from groundtruth.data_access.aoi_pipeline import (
    AnnualObservationRecord,
    AOIObservationBundle,
    AOIObservationCache,
    DataOrigin,
)
from groundtruth.engine.causal.readiness import assess_causal_readiness
from groundtruth.platform.config import get_settings
from groundtruth.platform.projects import readiness as readiness_module
from groundtruth.platform.projects.data import ClimateResult
from groundtruth.platform.projects.readiness import (
    CriterionView,
    ProjectReadiness,
    compute_project_readiness,
)
from groundtruth.platform.store.models import ProjectRow

REPO = Path(__file__).resolve().parents[2]
REAL_DATA = REPO / "data"
REAL_STAC = REAL_DATA / "processed" / "stac_cache"
REAL_CLIMATE = REAL_DATA / "processed" / "climate_cache" / "kariba_chirps_climate.json"
SRC = REPO / "packages" / "groundtruth" / "src" / "groundtruth"

CRITERION_IDS = [
    "boundary_verified",
    "observation_years",
    "pre_treatment_observations",
    "climate_coverage",
    "donor_panel",
    "sensor_continuity",
]


# --- fixtures and builders -------------------------------------------------------------------


def _project(
    *,
    case_id: str | None = "test-case",
    start: int = 2015,
    boundary_path: str | None = None,
    boundary_sha256: str | None = None,
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
        treatment_start_year=start,
        boundary_path=boundary_path,
        boundary_sha256=boundary_sha256,
        data_mode="observed",
        created_at=datetime.now(UTC),
    )


def _ids_sha(ids: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for sid in sorted(ids):
        digest.update(sid.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _record(
    year: int, sensor: str = "sentinel2", *, empty: bool = False
) -> AnnualObservationRecord:
    if empty:
        return AnnualObservationRecord(
            year=year,
            indicator="ndvi",
            value=float("nan"),
            n_valid_observations=0,
            clear_pixel_fraction=0.0,
            n_scenes=0,
            scene_ids=(),
            acquisition_dates=(),
            sensor=sensor,
            scenes_sha256=_ids_sha(()),
        )
    if sensor.startswith("landsat"):
        ids: tuple[str, ...] = (f"LC08_L2SP_170072_{year}0710_02_T1",)
        dates: tuple[str, ...] = (f"{year}-07-10",)
    else:
        ids = (f"S2A_MSIL2A_{year}0710T074609_R135_T36LTH_{year}0711T054025",)
        dates = (f"{year}-07-10",)
    return AnnualObservationRecord(
        year=year,
        indicator="ndvi",
        value=0.4 + 0.001 * (year % 7),
        n_valid_observations=1,
        clear_pixel_fraction=0.97,
        n_scenes=1,
        scene_ids=ids,
        acquisition_dates=dates,
        sensor=sensor,
        scenes_sha256=_ids_sha(ids),
        n_valid_pixels=970,
        n_total_pixels=1000,
        aoi_coverage_pct=97.0,
    )


def _write_obs(
    data_dir: Path, unit_id: str, years: list[int], *, sensors: dict[int, str] | None = None
) -> Path:
    cache = AOIObservationCache(data_dir / "processed" / "stac_cache")
    sensors = sensors or {}
    bundle = AOIObservationBundle(
        unit_id=unit_id,
        indicator="ndvi",
        bbox=(27.6, -17.7, 31.1, -15.6),
        records=tuple(_record(y, sensors.get(y, "sentinel2")) for y in years),
        data_origin=DataOrigin.REAL_STAC,
        catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
        provenance=Provenance.observed(source="sentinel-2-l2a", stage="geospatial"),
    )
    return cache.put(bundle)


def _by_id(result: ProjectReadiness) -> dict[str, CriterionView]:
    return {c.id: c for c in result.criteria}


@pytest.fixture
def cases_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated cases directory, so donor-screening files are crafted per test."""
    path = tmp_path / "cases"
    (path / "boundaries").mkdir(parents=True)
    monkeypatch.setattr(get_settings(), "cases_dir", path)
    return path


def _write_boundary(cases_dir: Path, *, content: bytes = b'{"type":"FeatureCollection"}') -> tuple:
    file = cases_dir / "boundaries" / "p.geojson"
    file.write_bytes(content)
    return str(file), hashlib.sha256(content).hexdigest()


def _write_donors(cases_dir: Path, case_id: str, n_eligible: int) -> list[str]:
    """Donor screening file: ``n_eligible`` eligible donors plus one excluded host district."""
    features = []
    unit_ids = []
    for i in range(n_eligible):
        uid = f"donor-{i:02d}"
        unit_ids.append(uid)
        features.append(
            {
                "type": "Feature",
                "geometry": None,
                "properties": {
                    "unit_id": uid,
                    "case_id": case_id,
                    "eligible_for_donor_pool": True,
                    "overlaps_project_boundary": False,
                    "within_10km_leakage_belt": False,
                    "distance_to_project_km": 25.0 + i,
                },
            }
        )
    features.append(
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "unit_id": "host-district",
                "case_id": case_id,
                "eligible_for_donor_pool": False,
                "overlaps_project_boundary": True,
                "within_10km_leakage_belt": False,
                "distance_to_project_km": 0.0,
            },
        }
    )
    payload = {"type": "FeatureCollection", "features": features}
    (cases_dir / "boundaries" / f"{case_id}-donors.geojson").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return unit_ids


def _stub_climate(
    monkeypatch: pytest.MonkeyPatch, missing: tuple[str, ...] = (), available: bool = True
) -> None:
    bundle = SimpleNamespace(
        missing_months_after_upstream=missing,
        s3_mirror_missing_months=missing,
        sources={},
    )
    result = ClimateResult(
        status="available" if available else "unavailable",
        reason=None if available else "No climate series has been ingested for this project",
        bundle=bundle if available else None,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(readiness_module, "load_climate", lambda project, *, data_dir=None: result)


# --- the criteria set ------------------------------------------------------------------------


def test_no_boundary_is_no_evidence(tmp_path: Path, cases_dir: Path) -> None:
    result = compute_project_readiness(_project(case_id=None), data_dir=tmp_path)
    assert isinstance(result, ProjectReadiness)
    assert [c.id for c in result.criteria] == CRITERION_IDS
    views = _by_id(result)
    assert views["boundary_verified"].status == "not_met"
    assert views["boundary_verified"].evidence_needed
    for cid in CRITERION_IDS[1:]:
        assert views[cid].status == "unavailable", cid
        assert views[cid].evidence_needed, cid
    assert result.attribution_ready is False
    # Nothing was written while computing: the cache directories stay absent.
    assert not (tmp_path / "processed").exists()


def test_boundary_only(tmp_path: Path, cases_dir: Path) -> None:
    path, digest = _write_boundary(cases_dir)
    project = _project(case_id=None, boundary_path=path, boundary_sha256=digest)
    views = _by_id(compute_project_readiness(project, data_dir=tmp_path))
    assert views["boundary_verified"].status == "met"
    assert views["boundary_verified"].observed_value is True
    assert all(views[c].status == "unavailable" for c in CRITERION_IDS[1:])

    mismatched = _project(case_id=None, boundary_path=path, boundary_sha256="0" * 64)
    bad = _by_id(compute_project_readiness(mismatched, data_dir=tmp_path))["boundary_verified"]
    assert bad.status == "not_met"
    assert "sha-256" in bad.evidence_needed.lower()

    missing = _project(case_id=None, boundary_path=str(cases_dir / "nope.geojson"))
    gone = _by_id(compute_project_readiness(missing, data_dir=tmp_path))["boundary_verified"]
    assert gone.status == "not_met"

    unrecorded = _project(case_id=None, boundary_path=path, boundary_sha256=None)
    assert (
        _by_id(compute_project_readiness(unrecorded, data_dir=tmp_path))["boundary_verified"].status
        == "not_met"
    )


def test_boundary_relative_path_resolves_against_repo_root(tmp_path: Path, cases_dir: Path) -> None:
    """The seed stores ``cases/boundaries/x.geojson``: relative to the directory above cases."""
    content = b'{"type":"FeatureCollection","features":[]}'
    (cases_dir / "boundaries" / "rel.geojson").write_bytes(content)
    project = _project(
        case_id=None,
        boundary_path="cases/boundaries/rel.geojson",
        boundary_sha256=hashlib.sha256(content).hexdigest(),
    )
    views = _by_id(compute_project_readiness(project, data_dir=tmp_path))
    assert views["boundary_verified"].status == "met"


def test_monitoring_with_post_only_series(
    tmp_path: Path, cases_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_obs(tmp_path, "test-case", [2021, 2022, 2023])
    _stub_climate(monkeypatch, available=False)
    views = _by_id(compute_project_readiness(_project(start=2015), data_dir=tmp_path))

    obs = views["observation_years"]
    assert obs.status == "not_met"
    assert obs.observed_value == 3
    pre = views["pre_treatment_observations"]
    assert pre.status == "not_met"
    assert pre.observed_value == 0
    assert pre.required == 5
    assert "2021" in pre.evidence_needed and "2015" in pre.evidence_needed
    assert views["sensor_continuity"].status == "met"
    assert views["sensor_continuity"].observed_value == ["sentinel2"]
    assert views["donor_panel"].status == "not_met"
    assert views["climate_coverage"].status == "unavailable"


def test_pre_treatment_criterion_flips_when_cache_removed(tmp_path: Path, cases_dir: Path) -> None:
    cache_file = _write_obs(tmp_path, "test-case", list(range(2008, 2023)))
    project = _project(start=2015)

    present = _by_id(compute_project_readiness(project, data_dir=tmp_path))
    assert present["pre_treatment_observations"].status == "met"
    assert present["pre_treatment_observations"].observed_value == 7
    assert present["observation_years"].status == "met"
    assert present["sensor_continuity"].status == "met"

    cache_file.unlink()
    gone = _by_id(compute_project_readiness(project, data_dir=tmp_path))
    for cid in ("observation_years", "pre_treatment_observations", "sensor_continuity"):
        assert gone[cid].status == "unavailable", cid


def test_empty_years_do_not_count_as_observed(tmp_path: Path, cases_dir: Path) -> None:
    cache = AOIObservationCache(tmp_path / "processed" / "stac_cache")
    records = tuple(_record(y, empty=(y % 2 == 0)) for y in range(2010, 2020))
    cache.put(
        AOIObservationBundle(
            unit_id="test-case",
            indicator="ndvi",
            bbox=(0.0, 0.0, 1.0, 1.0),
            records=records,
            data_origin=DataOrigin.REAL_STAC,
            catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
            provenance=Provenance.observed(source="sentinel-2-l2a", stage="geospatial"),
        )
    )
    views = _by_id(compute_project_readiness(_project(start=2015), data_dir=tmp_path))
    assert views["observation_years"].observed_value == 5  # 2011,13,15,17,19
    assert views["pre_treatment_observations"].observed_value == 2  # 2011, 2013


def test_sensor_discontinuity_is_not_met_until_validated(tmp_path: Path, cases_dir: Path) -> None:
    _write_obs(
        tmp_path,
        "test-case",
        list(range(2016, 2024)),
        sensors=dict.fromkeys(range(2016, 2020), "landsat8"),
    )
    sensor = _by_id(compute_project_readiness(_project(start=2020), data_dir=tmp_path))[
        "sensor_continuity"
    ]
    assert sensor.status == "not_met"
    assert sensor.observed_value == ["landsat8", "sentinel2"]
    assert "harmoni" in sensor.evidence_needed.lower()


# --- climate ---------------------------------------------------------------------------------


def test_climate_missing_months_reported_with_stub(
    tmp_path: Path, cases_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_climate(monkeypatch, missing=("2022.07", "2023.12"))
    view = _by_id(compute_project_readiness(_project(), data_dir=tmp_path))["climate_coverage"]
    assert view.status == "not_met"
    assert view.observed_value == ["2022-07", "2023-12"]
    assert "2022-07" in view.evidence_needed and "2023-12" in view.evidence_needed

    _stub_climate(monkeypatch, missing=())
    complete = _by_id(compute_project_readiness(_project(), data_dir=tmp_path))
    assert complete["climate_coverage"].status == "met"
    assert complete["climate_coverage"].observed_value == []


def test_climate_missing_months_reported(tmp_path: Path, cases_dir: Path) -> None:
    """The real Kariba climate cache reports its two missing months (copy; skip if absent)."""
    if not REAL_CLIMATE.exists():
        pytest.skip("real climate cache data/processed/climate_cache is git-ignored and absent")
    dest = tmp_path / "processed" / "climate_cache"
    dest.mkdir(parents=True)
    shutil.copy(REAL_CLIMATE, dest / REAL_CLIMATE.name)
    view = _by_id(compute_project_readiness(_project(case_id="kariba-redd"), data_dir=tmp_path))[
        "climate_coverage"
    ]
    assert view.status == "not_met"
    assert view.observed_value == ["2022-07", "2023-12"]


# --- donor panel and attribution readiness ---------------------------------------------------


def test_attribution_ready_only_when_every_criterion_is_met(
    tmp_path: Path, cases_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    years = list(range(2008, 2023))
    _write_obs(tmp_path, "test-case", years)
    donors = _write_donors(cases_dir, "test-case", 16)
    for uid in donors:
        _write_obs(tmp_path, uid, years)
    path, digest = _write_boundary(cases_dir)
    _stub_climate(monkeypatch, missing=())
    project = _project(start=2015, boundary_path=path, boundary_sha256=digest)

    ready = compute_project_readiness(project, data_dir=tmp_path)
    assert {c.id: c.status for c in ready.criteria} == dict.fromkeys(CRITERION_IDS, "met")
    assert ready.attribution_ready is True
    assert _by_id(ready)["donor_panel"].observed_value == 16

    # The excluded host district never counts, even when it has a series.
    _write_obs(tmp_path, "host-district", years)
    assert (
        _by_id(compute_project_readiness(project, data_dir=tmp_path))["donor_panel"].observed_value
        == 16
    )

    # Removing donor caches flips the criterion and the overall verdict.
    for uid in donors[:3]:
        (tmp_path / "processed" / "stac_cache" / f"{uid}__ndvi.json").unlink()
    degraded = compute_project_readiness(project, data_dir=tmp_path)
    panel = _by_id(degraded)["donor_panel"]
    assert panel.status == "not_met"
    assert panel.observed_value == 13
    assert degraded.attribution_ready is False


def test_donors_must_cover_the_projects_observed_years(tmp_path: Path, cases_dir: Path) -> None:
    years = list(range(2008, 2023))
    _write_obs(tmp_path, "test-case", years)
    donors = _write_donors(cases_dir, "test-case", 16)
    for uid in donors:
        _write_obs(tmp_path, uid, years[:-2])  # donors miss the last two years
    panel = _by_id(compute_project_readiness(_project(start=2015), data_dir=tmp_path))[
        "donor_panel"
    ]
    assert panel.status == "not_met"
    assert panel.observed_value == 0
    assert "16" in panel.evidence_needed


def test_donor_panel_without_observations_is_unavailable(tmp_path: Path, cases_dir: Path) -> None:
    _write_donors(cases_dir, "test-case", 16)
    panel = _by_id(compute_project_readiness(_project(), data_dir=tmp_path))["donor_panel"]
    assert panel.status == "unavailable"  # the project's own years are unknown


def test_corrupt_donor_screening_file_makes_panel_unavailable(
    tmp_path: Path, cases_dir: Path
) -> None:
    _write_obs(tmp_path, "test-case", list(range(2008, 2023)))
    (cases_dir / "boundaries" / "broken-donors.geojson").write_text("{nope", encoding="utf-8")
    panel = _by_id(compute_project_readiness(_project(start=2015), data_dir=tmp_path))[
        "donor_panel"
    ]
    assert panel.status == "unavailable"
    assert panel.evidence_needed


def test_all_empty_years_are_not_observations(tmp_path: Path, cases_dir: Path) -> None:
    cache = AOIObservationCache(tmp_path / "processed" / "stac_cache")
    cache.put(
        AOIObservationBundle(
            unit_id="test-case",
            indicator="ndvi",
            bbox=(0.0, 0.0, 1.0, 1.0),
            records=tuple(_record(y, empty=True) for y in range(2010, 2020)),
            data_origin=DataOrigin.REAL_STAC,
            catalog_url="https://planetarycomputer.microsoft.com/api/stac/v1",
            provenance=Provenance.observed(source="sentinel-2-l2a", stage="geospatial"),
        )
    )
    _write_donors(cases_dir, "test-case", 2)
    result = compute_project_readiness(_project(start=2015), data_dir=tmp_path)
    views = _by_id(result)
    assert views["observation_years"].observed_value == 0
    assert views["pre_treatment_observations"].status == "not_met"
    assert views["donor_panel"].status == "not_met"
    assert result.attribution_ready is False


# --- degradation -----------------------------------------------------------------------------


def test_readiness_handles_corrupt_cache(tmp_path: Path, cases_dir: Path) -> None:
    stac = tmp_path / "processed" / "stac_cache"
    stac.mkdir(parents=True)
    (stac / "test-case__ndvi.json").write_text("{not json", encoding="utf-8")
    climate = tmp_path / "processed" / "climate_cache"
    climate.mkdir(parents=True)
    (climate / "kariba_chirps_climate.json").write_text("{oops", encoding="utf-8")
    (cases_dir / "boundaries" / "broken-donors.geojson").write_text("{nope", encoding="utf-8")

    result = compute_project_readiness(_project(case_id="test-case"), data_dir=tmp_path)
    views = _by_id(result)
    for cid in ("observation_years", "pre_treatment_observations", "sensor_continuity"):
        assert views[cid].status == "unavailable", cid
    assert views["climate_coverage"].status == "unavailable"
    assert views["donor_panel"].status == "unavailable"
    assert result.attribution_ready is False

    kariba = compute_project_readiness(_project(case_id="kariba-redd"), data_dir=tmp_path)
    assert _by_id(kariba)["climate_coverage"].status == "unavailable"


# --- the engine keeps its logic and gains evidence_needed -------------------------------------


def test_engine_criteria_carry_evidence_needed_without_changing_logic() -> None:
    report = assess_causal_readiness(
        case_id="c",
        unit_id="u",
        pre_treatment_years=3,
        post_treatment_years=5,
        usable_donors_count=20,
        aoi_coverage_fraction=0.95,
        donor_pool_independence=True,
        spillover_buffer_km=25.0,
    )
    criteria = {c.criterion_id: c for c in report.criteria}
    assert criteria["pre_treatment_duration"].passed is False
    assert criteria["pre_treatment_duration"].evidence_needed
    assert criteria["donor_pool_size"].passed is True
    assert criteria["donor_pool_size"].evidence_needed == ""
    assert "evidence_needed" in report.to_dict()["criteria"][0]


# --- real Kariba -----------------------------------------------------------------------------


def test_kariba_real_not_attribution_ready() -> None:
    if not (REAL_STAC / "kariba-redd__ndvi.json").exists():
        pytest.skip("real Sentinel-2 cache data/processed/stac_cache is git-ignored and absent")
    project = _project(
        case_id="kariba-redd",
        start=2011,
        boundary_path="cases/boundaries/kariba-redd.geojson",
        boundary_sha256=hashlib.sha256(
            (REPO / "cases" / "boundaries" / "kariba-redd.geojson").read_bytes()
        ).hexdigest(),
    )
    result = compute_project_readiness(project, data_dir=REAL_DATA)
    views = _by_id(result)
    assert result.attribution_ready is False
    assert views["boundary_verified"].status == "met"
    assert views["pre_treatment_observations"].status == "not_met"
    assert views["pre_treatment_observations"].observed_value == 0
    assert views["donor_panel"].status == "not_met"
    assert views["donor_panel"].observed_value == 0
    assert "37" in views["donor_panel"].evidence_needed
    assert views["observation_years"].status == "not_met"
    if REAL_CLIMATE.exists():
        assert views["climate_coverage"].observed_value == ["2022-07", "2023-12"]


# --- no hand-typed numbers -------------------------------------------------------------------


def _literal_kwarg_calls(paths: list[Path], callee: str = "assess_causal_readiness") -> list[str]:
    """``file:line kwarg`` for every ``callee(...)`` call passing a numeric/bool literal kwarg.

    Generic over ``paths`` (files or directories searched recursively) so other packages can be
    added as their callers are migrated to derived inputs.
    """
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    offences: list[str] = []
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != callee:
                continue
            for kw in node.keywords:
                value = kw.value
                if isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub | ast.UAdd):
                    value = value.operand
                if isinstance(value, ast.Constant) and isinstance(value.value, int | float):
                    shown = file.relative_to(SRC) if file.is_relative_to(SRC) else file.name
                    offences.append(f"{shown}:{node.lineno} {kw.arg}")
    return offences


def test_literal_scan_detects_literals(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("assess_causal_readiness(pre_treatment_years=11, donors=-3.5, ok=x)\n")
    good = tmp_path / "good.py"
    good.write_text("assess_causal_readiness(pre_treatment_years=n)\n")
    assert _literal_kwarg_calls([bad]) == ["bad.py:1 pre_treatment_years", "bad.py:1 donors"]
    assert _literal_kwarg_calls([good]) == []


def test_no_caller_passes_literals() -> None:
    """Callers inside ``platform/projects`` derive every readiness input from artifacts."""
    assert _literal_kwarg_calls([SRC / "platform" / "projects"]) == []
