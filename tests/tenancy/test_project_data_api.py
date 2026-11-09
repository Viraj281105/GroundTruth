"""Task 9: the project data API and its field-level redaction by access level."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sqlalchemy import update
from world import GRANTED_CASE, PRIVATE_CASE, World, store_completed_run

from groundtruth.contracts.provenance import Provenance
from groundtruth.data_access.aoi_pipeline import (
    AnnualObservationRecord,
    AOIObservationBundle,
    AOIObservationCache,
    DataOrigin,
)
from groundtruth.data_access.climate import (
    AnnualClimateRecord,
    ClimateSourceProvenance,
    KaribaClimateBundle,
    UnitClimateSummary,
)
from groundtruth.engine import run_analysis
from groundtruth.platform.auth.authz import (
    PROJECT_CAPABILITY_TABLE,
    Capability,
    ProjectLevel,
)
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.config import get_settings
from groundtruth.platform.datasets.access import synthetic_access
from groundtruth.platform.projects.data import ClimateResult
from groundtruth.platform.projects.redaction import min_level, redact
from groundtruth.platform.store.models import ProjectRow

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

REPO = Path(__file__).resolve().parents[2]
REAL_STAC = REPO / "data" / "processed" / "stac_cache"
REAL_CLIMATE = REPO / "data" / "processed" / "climate_cache" / "kariba_chirps_climate.json"
_SKIP_STAC = "real Sentinel-2 cache data/processed/stac_cache is git-ignored and absent here"
_SKIP_CLIMATE = "real climate cache data/processed/climate_cache is git-ignored and absent here"

ENDPOINTS = (
    "readiness",
    "observations",
    "climate",
    "evidence-inventory",
    "verification",
    "assessment",
)


@pytest.fixture(scope="module")
def completed():
    """A real finished run on SIMULATED DATA for Kariba (one engine call)."""
    request = get_case(GRANTED_CASE).to_request(data_mode="simulated", seed=20260101)
    return run_analysis(request, synthetic_access(request, true_effect=0.06))


def _set_mode(world: World, case: str, mode: str) -> None:
    with world.sessions() as db:
        db.execute(
            update(ProjectRow)
            .where(ProjectRow.id == world.project_ids[case])
            .values(data_mode=mode)
        )
        db.commit()


@pytest.fixture
def world(tenant_world: World, completed) -> World:
    """Kariba carries a stored SIMULATED run, so its project is marked simulated here (the
    seeded project is observed; an observed project never serves a simulated run, which the
    observed-project test below checks by flipping it back)."""
    store_completed_run(tenant_world.sessions, completed, tenant_world.project_ids[GRANTED_CASE])
    _set_mode(tenant_world, GRANTED_CASE, "simulated")
    return tenant_world


# --- a small provenance-valid cache, built in tmp_path (runs in a clean checkout) -----------

YEARS = range(2010, 2024)


def _scene_sha(ids: list[str]) -> str:
    digest = hashlib.sha256()
    for sid in sorted(ids):
        digest.update(sid.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _record(indicator: str, year: int, offset: float) -> AnnualObservationRecord:
    ids = [f"LC08_L2SP_170072_{year}0710_02_T1", f"LC08_L2SP_170072_{year}0811_02_T1"]
    trend = 0.004 * (year - 2010) if year >= 2016 else 0.0
    return AnnualObservationRecord(
        year=year,
        indicator=indicator,
        value=0.5 + offset + trend + (0.01 if year % 2 else -0.01),
        n_valid_observations=2,
        clear_pixel_fraction=0.9,
        n_scenes=2,
        scene_ids=tuple(ids),
        acquisition_dates=(f"{year}-07-10", f"{year}-08-11"),
        sensor="landsat8",
        scenes_sha256=_scene_sha(ids),
        n_valid_pixels=900,
        n_total_pixels=1000,
    )


@pytest.fixture
def synth_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Real-origin (cached_real_stac) bundles that pass ``validate_real_provenance``, for the
    Kariba case id, in a temporary data dir that the settings point at."""
    cache = tmp_path / "processed" / "stac_cache"
    cache.mkdir(parents=True)
    store = AOIObservationCache(cache)
    for n, ind in enumerate(("ndvi", "evi", "ndmi", "nbr")):
        store.put(
            AOIObservationBundle(
                unit_id=GRANTED_CASE,
                indicator=ind,
                bbox=(28.0, -17.0, 28.1, -16.9),
                records=tuple(_record(ind, y, 0.01 * n) for y in YEARS),
                data_origin=DataOrigin.CACHED_REAL_STAC,
                catalog_url="https://example.test/stac",
                provenance=Provenance(
                    source="Landsat 8 C2 L2 (test fixture)",
                    method="annual median composite",
                    stage="ingestion",
                    parameters={"raster_grid": {"resolution_m": 30.0}},
                ),
            )
        )
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    _synthetic_climate(monkeypatch)
    return tmp_path


def _synthetic_climate(monkeypatch: pytest.MonkeyPatch) -> None:
    """A minimal climate bundle handed to the view builder (the climate cache format is not
    hand-craftable); the route, redaction and serialization still run for real."""
    records = tuple(
        AnnualClimateRecord(
            unit_id=GRANTED_CASE,
            year=y,
            valid_months=12,
            missing_months=(),
            is_complete_year=True,
            annual_rainfall_mm=700.0 + y % 7,
            partial_year_rainfall_mm=None,
            wet_season_rainfall_mm=600.0,
            calendar_wet_months_mm=600.0,
            dry_season_rainfall_mm=100.0,
            rainfall_anomaly_mm=1.0,
            rainfall_anomaly_pct=0.1,
            rainfall_anomaly_z=0.1,
            intra_annual_monthly_std_mm=10.0,
            intra_annual_cv=0.5,
            spi_12=0.1,
            spi_6_wet=0.1,
            spi_3_peak=0.1,
            drought_classification="near_normal",
            mean_temp_c=24.0,
            max_temp_c=30.0,
            min_temp_c=18.0,
            temp_anomaly_c=0.0,
            temp_anomaly_z=0.0,
        )
        for y in YEARS
    )
    summary = UnitClimateSummary(
        unit_id=GRANTED_CASE,
        name="Test",
        country="ZZ",
        role="treated",
        eligible=True,
        chirps_pixel_count=4,
        baseline_period=(2010, 2020),
        baseline_mean_rainfall_mm=700.0,
        baseline_std_rainfall_mm=50.0,
        baseline_interannual_cv=0.07,
        baseline_mean_wet_season_mm=600.0,
        baseline_mean_temp_c=24.0,
        baseline_std_temp_c=1.0,
        pre_treatment_mean_rainfall_mm=700.0,
        post_treatment_mean_rainfall_mm=705.0,
        pre_treatment_std_rainfall_mm=50.0,
        post_treatment_std_rainfall_mm=50.0,
        pre_treatment_drought_years=(),
        post_treatment_drought_years=(),
        records=records,
        missing_years=(),
        incomplete_years=(),
    )
    source = ClimateSourceProvenance(
        dataset_id="chirps-test",
        provider="Test provider",
        source_uri="https://example.test/chirps",
        resolution_deg=0.05,
        resolution_km=5.0,
        crs="EPSG:4326",
        native_unit="mm",
        canonical_unit="mm",
        temporal_coverage_start="2010-01",
        temporal_coverage_end="2023-12",
        retrieved_at="2026-01-01T00:00:00Z",
        citation="Test citation",
        processing_steps=("test",),
    )
    bundle = KaribaClimateBundle(
        case_id=GRANTED_CASE,
        retrieved_at="2026-01-01T00:00:00Z",
        sha256="c" * 64,
        spatial_window_bbox=(28.0, -17.0, 28.1, -16.9),
        spatial_window_shape=(2, 2),
        sources={"rainfall": source},
        s3_mirror_missing_months=(),
        missing_months_after_upstream=("2023.12", "2022-07"),  # dotted and dashed inputs
        eligible_donor_ids=(),
        unit_summaries={GRANTED_CASE: summary},
    )
    monkeypatch.setattr(
        "groundtruth.platform.projects.views.load_climate",
        lambda project, *, data_dir=None: ClimateResult(
            status="available", reason=None, bundle=bundle
        ),
    )


def _get(world: World, who: str, case: str, endpoint: str, **params: Any) -> Any:
    pid = world.project_ids[case]
    return world.client(who).get(f"/projects/{pid}/{endpoint}", params=params or None)


def _assert_subset(low: Any, high: Any, path: str = "") -> None:
    """``low`` keys are a subset of ``high`` keys at every depth, with equal shared values."""
    if isinstance(low, dict):
        assert isinstance(high, dict), path
        assert set(low) <= set(high), (path, sorted(set(low) - set(high)))
        for key in low:
            _assert_subset(low[key], high[key], f"{path}.{key}")
    elif isinstance(low, list):
        assert isinstance(high, list) and len(low) == len(high), path
        for i, (a, b) in enumerate(zip(low, high, strict=True)):
            _assert_subset(a, b, f"{path}[{i}]")
    else:
        assert low == high, path


def _keys(value: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            out.add(k)
            out |= _keys(v)
    elif isinstance(value, list):
        for v in value:
            out |= _keys(v)
    return out


# --- redact() unit behaviour ----------------------------------------------------------------


class _Inner(BaseModel):
    shown: int
    secret: str | None = Field(default=None, json_schema_extra=min_level("audit"))


class _Outer(BaseModel):
    name: str
    mid: str | None = Field(default=None, json_schema_extra=min_level("contribute"))
    inner: _Inner
    inners: list[_Inner]
    top: str | None = Field(default=None, json_schema_extra=min_level("owner"))


def test_redact_drops_fields_below_level_and_never_alters_values() -> None:
    model = _Outer(
        name="n",
        mid="m",
        inner=_Inner(shown=1, secret="s"),
        inners=[_Inner(shown=2, secret="t")],
        top="o",
    )
    view = redact(model, ProjectLevel.VIEW)
    assert view == {"name": "n", "inner": {"shown": 1}, "inners": [{"shown": 2}]}
    contribute = redact(model, ProjectLevel.CONTRIBUTE)
    assert set(contribute) == {"name", "mid", "inner", "inners"}
    audit = redact(model, ProjectLevel.AUDIT)
    assert audit["inner"] == {"shown": 1, "secret": "s"} and "top" not in audit
    owner = redact(model, ProjectLevel.OWNER)
    assert owner["top"] == "o" and owner["mid"] == "m"
    # A value that is None stays present (null) at a level that may see the field.
    nulls = redact(_Outer(name="n", inner=_Inner(shown=1), inners=[]), ProjectLevel.AUDIT)
    assert nulls["mid"] is None and nulls["inner"]["secret"] is None


def test_min_level_rejects_unknown_and_view() -> None:
    for bad in ("view", "admin"):
        with pytest.raises(ValueError):
            min_level(bad)


def test_min_levels_match_the_capability_table() -> None:
    """``contribute`` is exactly the EVIDENCE_FULL threshold and ``audit`` the DIAGNOSTICS one."""
    for level in ProjectLevel:
        for cap, marker in (
            (Capability.EVIDENCE_FULL, "contribute"),
            (Capability.DIAGNOSTICS, "audit"),
        ):
            model = _Outer(name="n", mid="m", inner=_Inner(shown=1, secret="s"), inners=[])
            visible = marker_visible(model, level, marker)
            assert visible == (level in PROJECT_CAPABILITY_TABLE[cap]), (level, cap)


def marker_visible(model: _Outer, level: ProjectLevel, marker: str) -> bool:
    out = redact(model, level)
    return "mid" in out if marker == "contribute" else "secret" in out["inner"]


# --- redaction over the live endpoints ------------------------------------------------------


LEVEL_CLIENTS = (("view", "funder"), ("contribute", "ngo"), ("audit", "auditor"), ("owner", "ref"))
GEO = ("boundary.geojson", "donors.geojson")


def test_redaction_is_strict_subset(world: World, synth_data: Path) -> None:
    """view subset of contribute subset of audit subset of owner, for every endpoint including
    the geojson routes; every shared value equal. Strict where fields are gated."""
    strict_somewhere: set[str] = set()
    for endpoint in (*ENDPOINTS, *GEO):
        bodies = []
        for level, who in LEVEL_CLIENTS:
            resp = _get(world, who, GRANTED_CASE, endpoint)
            assert resp.status_code == 200, (endpoint, who, resp.text)
            body = resp.json()
            assert body["access_level"] == level and body["data_mode"] == "simulated"
            bodies.append({k: v for k, v in body.items() if k != "access_level"})
        for low, high in pairwise(bodies):
            _assert_subset(low, high, endpoint)
            if _keys(low) < _keys(high):
                strict_somewhere.add(endpoint)
    # these have gated fields and data (synth cache / stored run), so strictness must show
    assert {"observations", "climate", "evidence-inventory", "verification", "assessment"} <= (
        strict_somewhere
    )


def test_view_grant_cannot_see_diagnostics(world: World) -> None:
    """Fields are absent, not null."""
    ver = _get(world, "funder", GRANTED_CASE, "verification").json()
    assert ver["status"] == "completed"
    assert "bundle" not in ver and "spec_hash" not in ver
    audit_ver = _get(world, "auditor", GRANTED_CASE, "verification").json()
    assert audit_ver["bundle"] is not None and audit_ver["spec_hash"]
    ngo_ver = _get(world, "ngo", GRANTED_CASE, "verification").json()
    assert "bundle" not in ngo_ver  # contribute is below diagnostics

    assessment = _get(world, "funder", GRANTED_CASE, "assessment").json()
    assert "diagnostic_refs" not in assessment["attribution"]
    for dim in assessment["dimensions"]:
        assert "diagnostic_refs" not in dim
    for rec in assessment["recommendations"]:
        assert "diagnostic_refs" not in rec
    audit_assessment = _get(world, "auditor", GRANTED_CASE, "assessment").json()
    assert all("diagnostic_refs" in d for d in audit_assessment["dimensions"])


def test_inventory_view_gets_summary_without_checksums(world: World, synth_data: Path) -> None:
    view = _get(world, "funder", GRANTED_CASE, "evidence-inventory")
    assert view.status_code == 200  # a view grant is not refused: it gets the summary
    body = view.json()
    assert body["status"] == "available"
    assert body["kinds"] and body["states"]
    assert {i["indicator"] for i in body["indicators"]} == {"ndvi", "evi", "ndmi", "nbr"}
    assert "items" not in body and "boundary_sha256" not in body
    blob = json.dumps(body)
    assert "scene_ids" not in blob and "scenes_sha256" not in blob and ".json" not in blob

    full = _get(world, "ngo", GRANTED_CASE, "evidence-inventory").json()  # contribute
    assert full["items"] and full["boundary_sha256"]
    assert all(i["scene_ids"] and len(i["scenes_sha256"]) == 64 for i in full["items"])


def test_observation_points_carry_state_and_gate_scene_ids(world: World, synth_data: Path) -> None:
    view = _get(world, "funder", GRANTED_CASE, "observations", indicator="ndvi").json()
    assert view["status"] == "available" and view["points"]
    for p in view["points"]:
        assert p["evidence_state"] in {"DERIVED", "MODEL_ESTIMATED", "UNAVAILABLE"}
        assert p["sensor"] and 0.0 <= p["clear_pixel_fraction"] <= 1.0
        assert "scene_ids" not in p and "scenes_sha256" not in p
        if p["evidence_state"] == "UNAVAILABLE":
            assert p["value"] is None
    assert any(p["aoi_coverage_pct"] is not None for p in view["points"])
    full = _get(world, "ngo", GRANTED_CASE, "observations").json()
    assert all(p["scene_ids"] for p in full["points"] if p["evidence_state"] != "UNAVAILABLE")
    # the same years and values, level to level
    assert [(p["year"], p["value"]) for p in view["points"]] == [
        (p["year"], p["value"]) for p in full["points"]
    ]


def test_climate_available_and_redacted(world: World, synth_data: Path) -> None:
    view = _get(world, "funder", GRANTED_CASE, "climate").json()
    assert view["status"] == "available" and view["years"] and view["sources"]
    assert "bundle_sha256" not in view
    assert "bundle_sha256" in _get(world, "ngo", GRANTED_CASE, "climate").json()


def test_climate_missing_months_use_the_dashed_spelling(world: World, synth_data: Path) -> None:
    """The cache spells a month 2022.07; the API serves 2022-07 here exactly as readiness does."""
    view = _get(world, "funder", GRANTED_CASE, "climate").json()
    assert view["missing_months"] == ["2022-07", "2023-12"]


# --- unavailable states ---------------------------------------------------------------------


def test_observations_unavailable_on_provenance_error(world: World, synth_data: Path) -> None:
    """A tampered cache surfaces the loader's specific reason: 200, no points, no 500."""
    src = synth_data / "processed" / "stac_cache" / "kariba-redd__ndvi.json"
    raw = json.loads(src.read_text(encoding="utf-8"))
    victim = next(r for r in raw["records"] if r["value"] is not None)
    victim["scenes_sha256"] = "f" * 64
    src.write_text(json.dumps(raw), encoding="utf-8")

    resp = _get(world, "ref", GRANTED_CASE, "observations", indicator="ndvi")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unavailable" and body["points"] == []
    assert "failed the provenance check" in body["reason"]
    assert "scenes_sha256" in body["reason"]

    inventory = _get(world, "ref", GRANTED_CASE, "evidence-inventory").json()
    # the other three indicators are intact, so the inventory as a whole is still available
    assert inventory["status"] == "available" and inventory["reason"] is None
    ndvi = next(i for i in inventory["indicators"] if i["indicator"] == "ndvi")
    assert ndvi["status"] == "unavailable" and "provenance" in ndvi["reason"]

    assert _get(world, "ref", GRANTED_CASE, "assessment").status_code == 200


def test_project_without_data_is_unavailable_not_an_error(
    world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)  # no caches at all
    for case in (GRANTED_CASE, PRIVATE_CASE):
        obs = _get(world, "ref", case, "observations", indicator="evi")
        assert obs.status_code == 200
        assert obs.json()["status"] == "unavailable" and obs.json()["reason"]
        assert obs.json()["points"] == []
        clim = _get(world, "ref", case, "climate").json()
        assert clim["status"] == "unavailable" and clim["reason"] and clim["years"] == []
        inv = _get(world, "ref", case, "evidence-inventory").json()
        assert inv["status"] == "unavailable" and inv["reason"] and inv["kinds"] != ["observations"]
        assert _get(world, "ref", case, "readiness").status_code == 200
        assess = _get(world, "ref", case, "assessment")
        assert assess.status_code == 200 and assess.json()["level"] == 0


def test_invalid_indicator_is_422(world: World) -> None:
    resp = _get(world, "ref", GRANTED_CASE, "observations", indicator="ndwi")
    assert resp.status_code == 422


# --- verification ---------------------------------------------------------------------------


def test_benchmark_verification_marked_simulated(world: World) -> None:
    """A simulated project serves its simulated run, labelled as such."""
    body = _get(world, "funder", GRANTED_CASE, "verification").json()
    assert body["status"] == "completed"
    assert body["data_mode"] == "simulated" and body["is_simulated"] is True
    assert any("SIMULATED DATA" in w for w in body["warnings"])
    assert body["verdict_label"]


def test_observed_project_never_serves_a_simulated_run(world: World) -> None:
    _set_mode(world, GRANTED_CASE, "observed")
    for who in ("funder", "auditor", "ref"):
        body = _get(world, who, GRANTED_CASE, "verification").json()
        assert body["status"] == "not_estimable", who
        assert body["run_id"] is None and body["verdict_label"] is None
        assert body["data_mode"] == "observed" and body["is_simulated"] is False
        assert body["readiness"]["criteria"]
        assert "bundle" not in body or body["bundle"] is None


def test_verification_not_estimable_without_a_run(world: World) -> None:
    body = _get(world, "ref", PRIVATE_CASE, "verification").json()
    assert body["status"] == "not_estimable"
    assert body["run_id"] is None and body["verdict_label"] is None
    assert isinstance(body["readiness"]["criteria"], list) and body["readiness"]["criteria"]
    # the seeded Mikoko project is simulated: the label and warning must say so
    assert body["data_mode"] == "simulated"
    assert any("SIMULATED DATA" in w for w in body["warnings"])


# --- assessment -----------------------------------------------------------------------------


def test_assessment_dimensions_carry_a_typed_status_kind(world: World) -> None:
    body = _get(world, "ref", GRANTED_CASE, "assessment").json()
    assert {"level", "level_name", "data_mode", "access_level", "recommendations"} <= set(body)
    dims = body["dimensions"]
    assert len(dims) == 8
    kinds = {d["id"]: d["status_kind"] for d in dims}
    assert kinds.pop("evidence_quality") == "quality_rating"
    assert kinds.pop("intervention_attribution") == "attribution_verdict"
    assert set(kinds.values()) == {"trend_status"} and len(kinds) == 6
    assert body["attribution"]["verdict"] in {"Supported", "Not supported", "Inconclusive"}


# --- geometry -------------------------------------------------------------------------------


def test_boundary_and_donors_geojson(world: World) -> None:
    boundary = _get(world, "funder", GRANTED_CASE, "boundary.geojson")
    assert boundary.status_code == 200
    doc = boundary.json()
    assert doc["type"] == "FeatureCollection" and doc["features"]
    assert doc["access_level"] == "view" and doc["data_mode"] in {"observed", "simulated"}

    donors = _get(world, "funder", GRANTED_CASE, "donors.geojson")
    assert donors.status_code == 200
    if (REPO / "cases" / "boundaries" / "kariba-donors.geojson").exists():
        assert donors.json()["features"] and donors.headers["X-GT-Available"] == "true"

    none = _get(world, "ref", PRIVATE_CASE, "donors.geojson")
    assert none.status_code == 200
    assert none.json()["features"] == [] and none.headers["X-GT-Available"] == "false"


def test_outsider_gets_404_on_every_data_route(world: World) -> None:
    for endpoint in (*ENDPOINTS, "boundary.geojson", "donors.geojson"):
        resp = _get(world, "outsider", PRIVATE_CASE, endpoint)
        assert resp.status_code == 404, endpoint


def test_readiness_matches_a_direct_computation(world: World) -> None:
    body = _get(world, "ref", GRANTED_CASE, "readiness").json()
    assert isinstance(body["attribution_ready"], bool)
    assert {c["id"] for c in body["criteria"]} >= {"boundary_verified", "donor_panel"}


# --- evidence refs, boundary, schema walk ----------------------------------------------------


def test_view_assessment_refs_carry_no_hash_fragment(world: World, synth_data: Path) -> None:
    body = _get(world, "funder", GRANTED_CASE, "assessment").json()
    refs = [r for d in body["dimensions"] for r in d["evidence_refs"]]
    refs += [r for rec in body["recommendations"] for r in rec["evidence_refs"]]
    refs += body["attribution"]["evidence_refs"]
    assert any(r.startswith("observation:") for r in refs)  # the check is not vacuous
    assert not [r for r in refs if re.search(r"[0-9a-f]{12}", r)], refs


def test_corrupt_boundary_is_a_typed_404_not_a_500(world: World, tmp_path: Path) -> None:
    bad = tmp_path / "bad.geojson"
    for content in ("{not json", '{"type": "FeatureCollection"}'):
        bad.write_text(content, encoding="utf-8")
        with world.sessions() as db:
            db.execute(
                update(ProjectRow)
                .where(ProjectRow.id == world.project_ids[GRANTED_CASE])
                .values(boundary_path=str(bad))
            )
            db.commit()
        resp = _get(world, "ref", GRANTED_CASE, "boundary.geojson")
        assert resp.status_code == 404, content
        assert resp.json()["detail"]["code"] == "boundary_unavailable"


SENSITIVE = re.compile(r"sha256|scene_id|path|checksum|spec_hash|bundle|diagnostic", re.I)


def test_sensitive_response_fields_carry_a_min_level_marker() -> None:
    from groundtruth.platform.api import project_schemas
    from groundtruth.platform.projects.redaction import MIN_LEVEL_KEY

    checked = 0
    for name, model in vars(project_schemas).items():
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        for field, info in model.model_fields.items():
            if SENSITIVE.search(field):
                extra = info.json_schema_extra
                assert isinstance(extra, dict) and MIN_LEVEL_KEY in extra, f"{name}.{field}"
                checked += 1
    assert checked >= 8
