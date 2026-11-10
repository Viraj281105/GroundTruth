"""Covariates and ADR-011 unit construction (#23), without a network.

A fake backend stands in for Earth Engine, and a recording stand-in for the ``ee``
module runs the real graph code, so the calls it makes can be checked. What Earth
Engine does with those calls is left to ``test_covariates_network.py``.

These tests exercise plumbing. No value here describes a real place: every number
comes from the fake (R6).
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import json
import logging
import pathlib
import sys
from dataclasses import replace
from typing import Any

import pytest
import yaml
from pydantic import SecretStr

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.contracts.ports import CovariateAccess
from groundtruth.contracts.request import UnitRef
from groundtruth.engine.features import COVARIATE_TRANSFORMS
from groundtruth.engine.matching.donors import DEFAULT_COVARIATES, MatchingConfig, match_donors
from groundtruth.platform.cases.registry import get_case, load_case
from groundtruth.platform.config import Settings
from groundtruth.platform.datasets.access import earth_engine_access
from groundtruth.platform.datasets.cache import ReductionCache
from groundtruth.platform.datasets.covariates import (
    COVARIATE_KEYS,
    CovariateQuery,
    EarthEngineCovariateAccess,
    RoadSource,
    covariate_datasets,
    covariate_definition,
)
from groundtruth.platform.datasets.ee_mask import (
    MASK_MEMBER,
    adr011_mask,
    protected_areas,
    split_unit_geometry,
    unit_geometry,
)
from groundtruth.platform.datasets.ee_units import EarthEngineUnitApiBackend, MaskQuery
from groundtruth.platform.datasets.session import EarthEngineSession
from groundtruth.platform.units import (
    LADDER,
    Adr011Thresholds,
    EarthEngineUnitConstruction,
    MissingRunParameterError,
    RunParameters,
    evaluate_district,
    generation_blockers,
    load_carbon_snapshot,
    load_registry_boundary,
    load_run_settings,
    run_settings_path,
)
from groundtruth.platform.units.manifest import REFERENCE_PERIODS
from groundtruth.platform.units.provider import build_mask_recipe
from groundtruth.platform.units.run_settings import ENGINE_TRANSFORMS_CAPABILITY, RunSettings

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "packages/groundtruth/src/groundtruth"
KARIBA_BOUNDARY = REPO / "cases/boundaries/kariba-redd.geojson"
SHA = "a" * 64

KEY_JSON = json.dumps(
    {
        "type": "service_account",
        "project_id": "gt-test-project",
        "private_key": "-----BEGIN PRIVATE KEY-----\nSENTINELKEYBODY0123456789\n-----END PRIVATE KEY-----\n",
        "client_email": "sentinel@gt-test-project.iam.gserviceaccount.com",
    }
)

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[28.0, -17.0], [28.1, -17.0], [28.1, -16.9], [28.0, -16.9], [28.0, -17.0]]],
}

ROAD = RoadSource(
    source="groads-v1",
    asset="projects/gt-test-project/assets/groads_v1",
    source_sha256=SHA,
    upload_date="2026-11-05",
    distance_scale_m=100.0,
    search_radius_km=50.0,
)


def _parameters(**overrides: Any) -> RunParameters:
    fields: dict[str, Any] = {
        "projection": "EPSG:FAKE",
        "raster_scale_m": 30.0,
        "raster_reducer": "nearest",
        "simplification_max_error_m": 10.0,
        "ecoregion_names": {
            "rung1": ("Fake A",),
            "rung2": ("Fake A", "Fake B"),
            "rung3": ("Fake A", "Fake B"),
        },
        "wdpa_release": "202610",
        "carbon_registry_snapshot_date": "2026-11-01",
        "pool_size": 2,
        "min_donors": 2,
        "max_donors": 50,
    }
    fields.update(overrides)
    return RunParameters(**fields)


def _recipe(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "parameters": _parameters(),
        "thresholds": Adr011Thresholds(),
        "ecoregion_names": ("Fake A",),
        "carbon_projects": (),
    }
    fields.update(overrides)
    return build_mask_recipe(**fields)


def _masked_unit(unit_id: str = "gaul2015:1", area_ha: float | None = 500_000.0) -> UnitRef:
    return UnitRef(unit_id=unit_id, geometry=unit_geometry(SQUARE, _recipe()), area_ha=area_ha)


class FakeBackend:
    """Earth Engine as scripted data. Records every call it receives."""

    def __init__(
        self,
        *,
        districts: dict[str, dict[str, Any]] | None = None,
        covariates: dict[str, Any] | None = None,
        in_belt: tuple[str, ...] = (),
        statuses: tuple[str, ...] = ("Designated", "Established", "Inscribed", "Proposed"),
        failures: dict[str, list[BaseException]] | None = None,
    ) -> None:
        self.districts = districts or {}
        self.covariate_values = covariates or {}
        self.in_belt = in_belt
        self.statuses = statuses
        self.failures = {k: list(v) for k, v in (failures or {}).items()}
        self.calls: list[str] = []
        self.queries: list[Any] = []
        self._current: dict[str, Any] = {}

    def _record(self, name: str) -> None:
        self.calls.append(name)
        queue = self.failures.get(name)
        if queue:
            raise queue.pop(0)

    def count(self, name: str) -> int:
        return self.calls.count(name)

    def initialize(self, key: Any, project: str) -> None:
        self._record("initialize")

    def list_ecoregion_names(self, asset: str, bounds: Any) -> list[str]:
        self._record("list_ecoregion_names")
        return ["Fake A", "Fake B"]

    def list_wdpa_releases(self, folder: str) -> list[str]:
        self._record("list_wdpa_releases")
        return ["WCMC/WDPA/202610"]

    def list_wdpa_statuses(self, asset: str, bounds: Any) -> list[str]:
        self._record("list_wdpa_statuses")
        return list(self.statuses)

    def list_admin_countries(self, asset: str, bounds: Any) -> list[str]:
        self._record("list_admin_countries")
        return ["Zambia", "Zimbabwe"]

    def list_worldpop_countries(self, asset: str, year: int, bounds: Any) -> list[str]:
        self._record("list_worldpop_countries")
        return ["ZMB", "ZWE"]

    def list_districts(self, asset: str, adm0_names: Any) -> list[dict[str, Any]]:
        self._record("list_districts")
        rows = [
            {"adm2_code": int(c), "adm0_name": d.get("country", "Zimbabwe")}
            for c, d in self.districts.items()
        ]
        rows.extend(
            {"adm2_code": 9000 + i, "adm0_name": n}
            for i, n in enumerate(adm0_names)
            if n not in {r["adm0_name"] for r in rows}
        )
        for row in rows:
            self.districts.setdefault(str(row["adm2_code"]), {"forest": 0, "in_ecoregions": 0})
        return rows

    def district_outline(self, asset: str, code: Any) -> dict[str, Any]:
        self._record("district_outline")
        return {**SQUARE, "code_marker": str(code)}

    def leakage_belt(
        self, boundary: Any, radius_m: float, max_error_m: float, crs: str
    ) -> dict[str, Any]:
        self._record("leakage_belt")
        self.queries.append(("belt", radius_m, max_error_m, crs))
        return dict(SQUARE)

    def districts_in_belt(self, asset: str, adm0_names: Any, belt: Any) -> list[str]:
        self._record("districts_in_belt")
        return list(self.in_belt)

    def _district_for(self, query: MaskQuery) -> dict[str, Any]:
        code = query.outline.get("code_marker")
        if code is None:
            return {"forest": 1000, "in_ecoregions": 1000, "eligible": 500_000, "protected": 0}
        return self.districts[str(code)]

    def measure_forest(self, query: MaskQuery) -> dict[str, Any]:
        self._record("measure_forest")
        district = self._district_for(query)
        return {"forest": district["forest"], "forest_in_ecoregions": district["in_ecoregions"]}

    def measure_mask(self, query: MaskQuery) -> dict[str, Any]:
        self._record("measure_mask")
        district = self._district_for(query)
        return {"eligible": district["eligible"], "protected_overlap": district.get("protected", 0)}

    def count_fragments(self, query: MaskQuery) -> int:
        self._record("count_fragments")
        return 7

    def reduce_covariate(self, query: CovariateQuery) -> dict[str, Any]:
        self._record("reduce_covariate")
        self.queries.append(query)
        key = query.covariate["key"]
        return {"value": self.covariate_values.get(key, 10.0), "unreachable_pixels": 0}


def _session(backend: Any, credentials: str | None = KEY_JSON) -> EarthEngineSession:
    return EarthEngineSession(
        credentials=SecretStr(credentials) if credentials else None,
        project=None,
        backend=backend,
        sleep=lambda s: None,
    )


def _covariate_service(
    backend: FakeBackend, *, cache: ReductionCache | None = None
) -> EarthEngineCovariateAccess:
    return EarthEngineCovariateAccess(
        session=_session(backend),
        backend=backend,
        road=ROAD,
        mask_rule="fraction-weighted",
        cache=cache,
    )


# --------------------------------------------------------------------------


class TestCaseDonorSettings:
    """V8: the loader used to read only donor_pool_size."""

    def test_the_kariba_case_pins_all_three(self):
        case = get_case("kariba-redd")
        assert (case.donor_pool_size, case.min_donors, case.max_donors) == (80, 30, 50)

    def test_they_reach_the_request(self):
        donors = get_case("kariba-redd").to_request().donors
        assert (donors.pool_size, donors.min_donors, donors.max_donors) == (80, 30, 50)

    def test_an_explicit_floor_still_overrides_the_case(self):
        donors = get_case("kariba-redd").to_request(min_donors=10).donors
        assert (donors.min_donors, donors.max_donors) == (10, 50)

    def test_the_cap_rises_to_meet_a_higher_floor(self):
        donors = get_case("kariba-redd").to_request(min_donors=60).donors
        assert (donors.min_donors, donors.max_donors) == (60, 60)

    def test_a_case_without_them_keeps_the_contract_defaults(self, tmp_path):
        payload = yaml.safe_load((REPO / "cases/kariba-redd.yaml").read_text(encoding="utf-8"))
        del payload["analysis"]["min_donors"], payload["analysis"]["max_donors"]
        path = tmp_path / "kariba-redd.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        case = load_case(path)
        assert case.min_donors is None and case.max_donors is None
        assert (case.to_request().donors.min_donors, case.to_request().donors.max_donors) == (
            10,
            50,
        )

    def test_the_committed_comment_states_the_p_value_floor(self):
        text = (REPO / "cases/kariba-redd.yaml").read_text(encoding="utf-8")
        assert "0.032 at J=30" in text
        assert "5x the treated unit" in text


class TestNamesAgreeWithTheEngine:
    """C4: the service must return exactly what the engine expects, under those names."""

    def test_the_covariate_keys_are_the_engines(self):
        assert COVARIATE_KEYS == DEFAULT_COVARIATES
        assert set(COVARIATE_KEYS) == set(COVARIATE_TRANSFORMS)

    def test_the_service_implements_the_port(self):
        assert isinstance(_covariate_service(FakeBackend()), CovariateAccess)


class TestDefinitions:
    """V1-V4, agreed with Viraj (C4), 2026-11-05."""

    def test_rainfall_is_the_mean_annual_total_over_2001_to_2010(self):
        d = covariate_definition("rainfall_mm", ROAD)
        assert d["asset"] == "UCSB-CHG/CHIRPS/DAILY"
        assert (d["first_year"], d["last_year"]) == (2001, 2010)
        assert d["kind"] == "mean-annual-total" and d["statistic"] == "mean"

    def test_slope_is_per_pixel_then_mean(self):
        d = covariate_definition("slope_deg", ROAD)
        assert d["kind"] == "slope" and d["statistic"] == "mean"

    def test_population_is_worldpop_2000_summed(self):
        d = covariate_definition("population_density", ROAD)
        assert d["asset"] == "WorldPop/GP/100m/pop"
        assert d["year"] == 2000 and d["statistic"] == "sum"

    def test_an_unknown_covariate_raises(self):
        with pytest.raises(DataUnavailableError, match="no covariate service"):
            covariate_definition("soil_type", ROAD)


class TestPinning:
    def test_every_covariate_has_a_ref_with_a_reference_epoch(self):
        refs = covariate_datasets(ROAD)
        assert set(refs) == set(COVARIATE_KEYS)
        for ref in refs.values():
            assert ";ref=" in ref.version, ref
            assert not ref.is_synthetic
            assert ref.dataset_id in REFERENCE_PERIODS

    def test_reference_year_is_separate_from_release(self):
        refs = covariate_datasets(ROAD)
        assert refs["rainfall_mm"].version == "2.0-final;ref=2001-2010"
        assert refs["elevation_m"].version == "v3;ref=2000-02"
        assert refs["population_density"].version == "gp-100m;ref=2000"

    def test_groads_is_pinned_by_asset_hash_and_upload_date(self):
        ref = covariate_datasets(ROAD)["road_distance_km"]
        assert ref.dataset_id == "groads-v1"
        assert ref.asset == ROAD.asset
        assert ref.version == f"v1+sha256:{SHA};uploaded=2026-11-05;ref=1980-2010"

    def test_the_osm_fallback_is_named_as_what_it_is(self):
        ref = covariate_datasets(replace(ROAD, source="osm-current"))["road_distance_km"]
        assert ref.dataset_id == "osm-roads"
        assert ref.version.endswith(";ref=present")

    def test_an_unknown_road_source_is_refused(self):
        with pytest.raises(ConfigurationError, match="unknown road source"):
            replace(ROAD, source="whatever")

    def test_mask_inputs_carry_a_reference_epoch(self):
        refs = {r.dataset_id: r for r in EarthEngineUnitConstruction().dataset_refs(_parameters())}
        assert refs["hansen-gfc"].version == "2023-v1.11;ref=2000"
        assert refs["jrc-global-surface-water"].version == "1.4;ref=1984-2021"
        assert refs["wdpa"].asset == "WCMC/WDPA/202610/polygons"
        assert "current" not in str(refs["wdpa"].asset)

    def test_every_input_has_a_reference_period_in_the_manifest(self):
        for key in (
            "chirps-daily",
            "srtm-gl1",
            "groads-v1",
            "osm-roads",
            "worldpop-gp-100m",
            "hansen-gfc",
        ):
            assert key in REFERENCE_PERIODS


class TestCovariateService:
    def test_it_returns_raw_values_for_exactly_the_keys_asked(self):
        backend = FakeBackend(covariates={"elevation_m": 812.5, "road_distance_km": 3.25})
        values = _covariate_service(backend).covariates(
            _masked_unit(), ("elevation_m", "road_distance_km")
        )
        # Raw: a log1p here would change 3.25, and the transform belongs to the engine.
        assert values == {"elevation_m": 812.5, "road_distance_km": 3.25}

    def test_population_density_is_the_sum_over_the_eligible_area(self):
        backend = FakeBackend(covariates={"population_density": 100_000.0})
        values = _covariate_service(backend).covariates(
            _masked_unit(area_ha=500_000.0), ("population_density",)
        )
        assert values["population_density"] == pytest.approx(20.0)  # 100,000 people over 5,000 km²

    def test_population_density_needs_an_eligible_area(self):
        with pytest.raises(DataUnavailableError, match="no eligible area"):
            _covariate_service(FakeBackend()).covariates(
                _masked_unit(area_ha=None), ("population_density",)
            )

    def test_a_bare_outline_is_refused(self):
        unit = UnitRef(unit_id="x", geometry=SQUARE)
        with pytest.raises(DataUnavailableError, match="no ADR-011 mask recipe"):
            _covariate_service(FakeBackend()).covariates(unit, ("elevation_m",))

    def test_no_geometry_is_refused(self):
        with pytest.raises(DataUnavailableError, match="no geometry"):
            _covariate_service(FakeBackend()).covariates(UnitRef(unit_id="x"), ("elevation_m",))

    def test_a_missing_value_raises_rather_than_dropping_the_key(self):
        """match_donors silently drops a candidate with a missing covariate."""
        backend = FakeBackend(covariates={"rainfall_mm": None})
        with pytest.raises(DataUnavailableError, match="never filled"):
            _covariate_service(backend).covariates(_masked_unit(), ("rainfall_mm",))

    def test_a_negative_distance_is_refused(self):
        backend = FakeBackend(covariates={"road_distance_km": -1.0})
        with pytest.raises(DataUnavailableError, match="negative"):
            _covariate_service(backend).covariates(_masked_unit(), ("road_distance_km",))

    def test_pixels_beyond_the_search_radius_refuse_rather_than_bias_the_mean(self):
        class Beyond(FakeBackend):
            def reduce_covariate(self, query: CovariateQuery) -> dict[str, Any]:
                return {"value": 4.0, "unreachable_pixels": 12.0}

        with pytest.raises(DataUnavailableError, match="search radius"):
            _covariate_service(Beyond()).covariates(_masked_unit(), ("road_distance_km",))

    def test_the_mask_rule_has_no_default(self):
        with pytest.raises(ConfigurationError, match="native-scale mask rule"):
            EarthEngineCovariateAccess(
                session=_session(FakeBackend()), backend=FakeBackend(), road=ROAD, mask_rule=""
            )

    def test_failures_retry_then_raise_data_unavailable(self):
        backend = FakeBackend(failures={"reduce_covariate": [ConnectionError("reset")] * 10})
        with pytest.raises(DataUnavailableError, match="after 4 attempts"):
            _covariate_service(backend).covariates(_masked_unit(), ("elevation_m",))
        assert backend.count("reduce_covariate") == 4

    def test_a_cache_hit_needs_no_earth_engine(self, tmp_path):
        cache = ReductionCache(tmp_path)
        first = _covariate_service(FakeBackend(), cache=cache).covariates(
            _masked_unit(), COVARIATE_KEYS
        )
        backend = FakeBackend()
        service = EarthEngineCovariateAccess(
            session=_session(backend, credentials=None),
            backend=backend,
            road=ROAD,
            mask_rule="fraction-weighted",
            cache=cache,
        )
        assert service.covariates(_masked_unit(), COVARIATE_KEYS) == first
        assert backend.calls == []

    def test_a_different_mask_or_road_or_rule_misses_the_cache(self, tmp_path):
        cache = ReductionCache(tmp_path)
        unit = _masked_unit()
        _covariate_service(FakeBackend(), cache=cache).covariates(unit, ("road_distance_km",))

        other = UnitRef(
            unit_id=unit.unit_id,
            geometry=unit_geometry(SQUARE, _recipe(ecoregion_names=("Fake B",))),
            area_ha=unit.area_ha,
        )
        backend = FakeBackend()
        _covariate_service(backend, cache=cache).covariates(other, ("road_distance_km",))
        assert backend.count("reduce_covariate") == 1

        moved = FakeBackend()
        EarthEngineCovariateAccess(
            session=_session(moved),
            backend=moved,
            road=replace(ROAD, source_sha256="b" * 64),
            mask_rule="fraction-weighted",
            cache=cache,
        ).covariates(unit, ("road_distance_km",))
        assert moved.count("reduce_covariate") == 1

        rule = FakeBackend()
        EarthEngineCovariateAccess(
            session=_session(rule), backend=rule, road=ROAD, mask_rule="pixel-centre", cache=cache
        ).covariates(unit, ("road_distance_km",))
        assert rule.count("reduce_covariate") == 1


class TestMaskRecipe:
    def test_erosion_is_a_circular_kernel_of_ten_pixels(self):
        erosion = _recipe()["erosion"]
        assert erosion == {"radius_m": 300.0, "radius_pixels": 10, "kernel": "circle"}

    def test_a_scale_that_does_not_divide_the_buffer_is_refused(self):
        with pytest.raises(DataUnavailableError, match="whole number"):
            _recipe(parameters=_parameters(raster_scale_m=7.0))

    def test_it_uses_the_dated_wdpa_snapshot_and_adr_thresholds(self):
        recipe = _recipe()
        assert recipe["protected_areas"]["asset"] == "WCMC/WDPA/202610/polygons"
        assert recipe["baseline_forest"]["min_percent"] == 30.0
        assert recipe["permanent_water"]["min_percent"] == 90.0

    def test_adopted_is_not_in_the_subtracted_statuses(self):
        """V7: the literal reading of ADR-011."""
        statuses = _recipe()["protected_areas"]["status_values"]
        assert set(statuses) == {"Designated", "Inscribed", "Established"}
        assert not {"Adopted", "Proposed", "Not Reported"} & set(statuses)

    def test_the_recipe_travels_inside_the_geometry_and_splits_back_out(self):
        recipe = _recipe()
        geometry = unit_geometry(SQUARE, recipe)
        assert geometry[MASK_MEMBER] == recipe
        outline, found = split_unit_geometry(geometry)
        assert outline == SQUARE and found == recipe
        assert split_unit_geometry(SQUARE) == (SQUARE, None)

    def test_a_contract_unit_can_carry_it(self):
        unit = _masked_unit()
        restored = UnitRef.model_validate_json(unit.model_dump_json())
        assert restored.geometry == unit.geometry


# --- a recording stand-in for the ``ee`` module -----------------------------------


class Node:
    """Any Earth Engine object: every attribute is a call that records itself."""

    def __init__(self, log: list[tuple[str, tuple, dict]], name: str = "ee") -> None:
        self._log = log
        self._name = name

    def __getattr__(self, attr: str) -> Node:
        return Node(self._log, f"{self._name}.{attr}")

    def __call__(self, *args: Any, **kwargs: Any) -> Node:
        method = self._name.rsplit(".", 1)[-1]
        self._log.append((method, args, kwargs))
        return Node(self._log, "ee")

    def getInfo(self) -> dict[str, Any]:  # noqa: N802
        self._log.append(("getInfo", (), {}))
        return {"value": {"v": 1.0}, "unreachable_pixels": {"v": 0}}


def calls(log: list[tuple[str, tuple, dict]], name: str) -> list[tuple[tuple, dict]]:
    return [(args, kwargs) for method, args, kwargs in log if method == name]


class TestEarthEngineGraph:
    """The real translation code, run against the recorder."""

    def _mask_log(self, **recipe: Any) -> list[tuple[str, tuple, dict]]:
        log: list[tuple[str, tuple, dict]] = []
        ee = Node(log)
        adr011_mask(ee, ee.Geometry(SQUARE), _recipe(**recipe))
        return log

    def test_wdpa_is_filtered_to_2000_or_earlier_including_zero(self):
        log: list[tuple[str, tuple, dict]] = []
        ee = Node(log)
        protected_areas(ee, _recipe()["protected_areas"])
        # lte 2000 is what keeps STATUS_YR = 0, which means unknown and is subtracted.
        assert (("STATUS_YR", 2000), {}) in calls(log, "lte")
        assert (("STATUS", ["Designated", "Inscribed", "Established"]), {}) in calls(log, "inList")
        assert not calls(log, "gt") and not calls(log, "neq")

    def test_the_dated_snapshot_is_what_is_read(self):
        log = self._mask_log()
        assert (("WCMC/WDPA/202610/polygons",), {}) in calls(log, "FeatureCollection")

    def test_thresholds_reach_the_rasters(self):
        log = self._mask_log()
        assert ((30.0,), {}) in calls(log, "gte")
        assert ((90.0,), {}) in calls(log, "gte")

    def test_outside_the_district_is_zero_before_the_erosion(self):
        """V6: otherwise district edges would not erode."""
        log = self._mask_log()
        order = [method for method, _, _ in log]
        focal = order.index("focalMin")
        assert "paint" in order[:focal] and "unmask" in order[:focal]
        assert ((0,), {}) in calls(log, "unmask")
        assert order.index("focalMin") > max(i for i, m in enumerate(order) if m == "And")

    def test_erosion_uses_the_pinned_kernel(self):
        log = self._mask_log()
        assert calls(log, "focalMin") == [
            ((), {"radius": 10, "kernelType": "circle", "units": "pixels"})
        ]

    def test_it_runs_on_the_pinned_grid(self):
        log = self._mask_log()
        assert calls(log, "reproject")
        for _, kwargs in calls(log, "reproject"):
            assert kwargs == {"crs": "EPSG:FAKE", "scale": 30.0}

    def test_an_unknown_recipe_is_refused(self):
        from groundtruth.platform.datasets.resilience import PermanentError

        with pytest.raises(PermanentError, match="unknown unit mask recipe"):
            ee = Node([])
            adr011_mask(ee, ee.Geometry(SQUARE), {"kind": "other", "version": 1})

    def _backend(self) -> tuple[EarthEngineUnitApiBackend, list[tuple[str, tuple, dict]]]:
        log: list[tuple[str, tuple, dict]] = []
        backend = EarthEngineUnitApiBackend()
        backend._ee = Node(log)
        return backend, log

    def _covariate(
        self, key: str, rule: str = "fraction-weighted"
    ) -> list[tuple[str, tuple, dict]]:
        backend, log = self._backend()
        backend.reduce_covariate(
            CovariateQuery(
                outline=SQUARE,
                recipe=_recipe(),
                covariate=covariate_definition(key, ROAD),
                mask_rule=rule,
            )
        )
        return log

    @pytest.mark.parametrize("key", COVARIATE_KEYS)
    def test_every_covariate_is_masked_and_never_best_effort(self, key):
        log = self._covariate(key)
        assert calls(log, "updateMask")
        for _, kwargs in calls(log, "reduceRegion"):
            assert kwargs["bestEffort"] is False

    def test_rainfall_is_summed_over_the_window_and_divided_by_ten_years(self):
        log = self._covariate("rainfall_mm")
        assert (("2001-01-01", "2011-01-01"), {}) in calls(log, "filterDate")
        assert ((10,), {}) in calls(log, "divide")
        # Native scale: reduced in the dataset's own projection, not on the 30 m grid.
        assert "scale" not in calls(log, "reduceRegion")[0][1]

    def test_slope_comes_from_the_terrain_algorithm(self):
        assert calls(self._covariate("slope_deg"), "slope")

    def test_population_selects_the_year_2000_and_sums(self):
        log = self._covariate("population_density")
        assert (("year", 2000), {}) in calls(log, "eq")
        assert calls(log, "sum") and calls(log, "mosaic")

    def test_road_distance_uses_the_required_settings_and_counts_the_unreachable(self):
        log = self._covariate("road_distance_km")
        assert ((), {"searchRadius": 50_000.0, "maxError": 100.0}) in calls(log, "distance")
        assert ((1000.0,), {}) in calls(log, "divide")
        assert ((-1,), {}) in calls(log, "unmask")  # the count of pixels beyond the radius

    def test_the_fraction_rule_resamples_and_the_centre_rule_does_not(self):
        assert calls(self._covariate("rainfall_mm"), "reduceResolution")
        assert not calls(self._covariate("rainfall_mm", "pixel-centre"), "reduceResolution")

    def test_listings_ask_for_names_and_never_a_count(self):
        backend, log = self._backend()
        names = ("list_ecoregion_names", "list_wdpa_statuses", "list_admin_countries")
        for name in names:
            getattr(backend, name)("asset", (21.0, -27.5, 41.5, -0.5))
        assert calls(log, "distinct") and not calls(log, "size")

    def test_a_masked_observation_applies_the_mask_to_value_and_count(self):
        from groundtruth.platform.datasets.earthengine import YearQuery

        backend, log = self._backend()
        backend.reduce(
            YearQuery(
                collection="LANDSAT/LE07/C02/T1_L2",
                year=2005,
                geometry=unit_geometry(SQUARE, _recipe()),
                reduction=_landsat7_ndvi(),
                snapshot_micros=1,
                scale_m=30,
            )
        )
        assert len(calls(log, "updateMask")) >= 2
        assert calls(log, "focalMin")

    def test_a_plain_observation_applies_no_mask(self):
        from groundtruth.platform.datasets.earthengine import YearQuery

        backend, log = self._backend()
        backend.reduce(
            YearQuery(
                collection="LANDSAT/LE07/C02/T1_L2",
                year=2005,
                geometry=SQUARE,
                reduction=_landsat7_ndvi(),
                snapshot_micros=1,
                scale_m=30,
            )
        )
        assert not calls(log, "focalMin")


def _landsat7_ndvi() -> dict[str, Any]:
    from groundtruth.engine import describe_engine

    return next(
        s
        for s in describe_engine()["reduction"]["specs"]
        if s["sensor"] == "landsat7" and s["indicator"] == "ndvi"
    )


# --- unit construction -------------------------------------------------------------


def _snapshot(tmp_path: pathlib.Path, **overrides: Any) -> pathlib.Path:
    payload: dict[str, Any] = {
        "snapshot_date": "2026-11-01",
        "source_uri": "https://example.invalid/test-only",
        "source_file_sha256": SHA,
        "projects": [
            {"project_id": "VCS 902", "name": "Kariba", "geometry_path": str(KARIBA_BOUNDARY)},
            {"project_id": "TEST 1", "name": "No geometry", "geometry_path": None},
        ],
        "excluded_districts": [{"unit_id": "gaul2015:40", "project_id": "TEST 1"}],
    }
    payload.update(overrides)
    path = tmp_path / "snapshot.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _provider(
    backend: FakeBackend, tmp_path: pathlib.Path, *, cache: ReductionCache | None = None
) -> EarthEngineUnitConstruction:
    return EarthEngineUnitConstruction(
        session=_session(backend),
        backend=backend,
        cache=cache,
        carbon_projects=load_carbon_snapshot(_snapshot(tmp_path)),
        case_registry_id="VCS 902",
        treated_ecoregion_key="rung1",
    )


# 500,000 pixels x 900 m² = 450 km². The fake treated unit is that size, so the area
# band runs 150-1350 km² and the floor of 500 km² is what screens small districts.
GOOD = {"forest": 2_000_000, "in_ecoregions": 2_000_000, "eligible": 1_000_000}


@functools.lru_cache(maxsize=1)
def _boundary():
    # Loading runs the overlap check, which is slow, and the result never changes here.
    return load_registry_boundary(KARIBA_BOUNDARY)


class TestUnitConstruction:
    def _facts(self, backend: FakeBackend, tmp_path: pathlib.Path, **kwargs: Any):
        facts = _provider(backend, tmp_path, **kwargs).districts_for_rung(
            LADDER[0], _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
        )
        return {f.adm2_code: f for f in facts}

    def test_area_is_pixels_times_pixel_area(self, tmp_path):
        backend = FakeBackend(districts={"10": GOOD})
        facts = self._facts(backend, tmp_path)["10"]
        assert facts.eligible_pixels == 1_000_000
        assert facts.eligible_area_km2 == pytest.approx(900.0)
        assert facts.unit_id == "gaul2015:10"
        assert facts.forest_share_in_target_ecoregions == 1.0

    def test_an_eligible_district_carries_outline_recipe_and_fragments(self, tmp_path):
        facts = self._facts(FakeBackend(districts={"10": GOOD}), tmp_path)["10"]
        assert facts.fragments == 7
        assert MASK_MEMBER in facts.geometry
        assert facts.geometry_hash

    def test_the_geometry_hash_changes_with_the_pixel_count(self, tmp_path):
        a = self._facts(FakeBackend(districts={"10": GOOD}), tmp_path)["10"]
        b = self._facts(FakeBackend(districts={"10": {**GOOD, "eligible": 1_000_001}}), tmp_path)[
            "10"
        ]
        assert a.geometry_hash != b.geometry_hash

    def test_no_forest_in_a_target_ecoregion_skips_the_erosion(self, tmp_path):
        backend = FakeBackend(districts={"10": {"forest": 100, "in_ecoregions": 0}})
        facts = self._facts(backend, tmp_path)["10"]
        assert facts.eligible_area_km2 == 0 and facts.geometry is None
        # Only the treated unit is measured by measure_mask here.
        assert backend.count("measure_mask") == 1

    def test_a_district_with_no_forest_has_a_zero_share_not_an_error(self, tmp_path):
        facts = self._facts(
            FakeBackend(districts={"10": {"forest": 0, "in_ecoregions": 0}}), tmp_path
        )["10"]
        assert facts.forest_share_in_target_ecoregions == 0.0

    def test_belt_and_carbon_flags_come_from_their_sources(self, tmp_path):
        backend = FakeBackend(districts={"10": GOOD, "20": GOOD}, in_belt=("20",))
        facts = self._facts(backend, tmp_path)
        assert not facts["10"].intersects_leakage_belt and facts["20"].intersects_leakage_belt

    def test_fragments_are_counted_only_for_units_that_stay(self, tmp_path):
        backend = FakeBackend(districts={"10": GOOD, "20": GOOD}, in_belt=("20",))
        self._facts(backend, tmp_path)
        assert backend.count("count_fragments") == 1

    def test_every_measurement_is_cached_per_district(self, tmp_path):
        cache = ReductionCache(tmp_path / "cache")
        self._facts(FakeBackend(districts={"10": GOOD}), tmp_path, cache=cache)
        again = FakeBackend(districts={"10": GOOD})
        self._facts(again, tmp_path, cache=cache)
        assert again.count("measure_forest") == 0
        assert again.count("measure_mask") == 0
        assert again.count("count_fragments") == 0

    def test_a_failure_raises_with_nothing_partial_and_nothing_cached(self, tmp_path):
        cache = ReductionCache(tmp_path / "cache")
        backend = FakeBackend(
            districts={"10": GOOD},
            failures={
                "measure_forest": [type("EEException", (Exception,), {})("Computation timed out.")]
            },
        )
        with pytest.raises(DataUnavailableError, match="Computation timed out"):
            self._facts(backend, tmp_path, cache=cache)
        assert backend.count("measure_forest") == 1

    def test_a_country_with_no_districts_refuses(self, tmp_path):
        class Empty(FakeBackend):
            def list_districts(self, asset: str, adm0_names: Any) -> list[dict[str, Any]]:
                return []

        with pytest.raises(DataUnavailableError, match="silently shrink"):
            self._facts(Empty(), tmp_path)

    def test_treated_unit_uses_the_same_mask_minus_itself(self, tmp_path):
        provider = _provider(FakeBackend(), tmp_path)
        unit = provider.treated_unit(
            _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
        )
        recipe = unit.geometry[MASK_MEMBER]
        assert unit.unit_id == "kariba-redd"
        # VCS 902 is the case under test: subtracting it would empty the treated unit.
        assert recipe["carbon_projects"] == []
        assert unit.attributes["eligible_area_km2"] == pytest.approx(450.0)

    def test_donors_are_masked_by_every_registered_project(self, tmp_path):
        backend = FakeBackend(districts={"10": GOOD})
        facts = self._facts(backend, tmp_path)["10"]
        assert len(facts.geometry[MASK_MEMBER]["carbon_projects"]) == 1

    def test_the_treated_unit_needs_its_rung_named(self, tmp_path):
        backend = FakeBackend()
        provider = EarthEngineUnitConstruction(
            session=_session(backend),
            backend=backend,
            carbon_projects=load_carbon_snapshot(_snapshot(tmp_path)),
            case_registry_id="VCS 902",
        )
        with pytest.raises(DataUnavailableError, match="treated_ecoregion_rung"):
            provider.treated_unit(
                _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
            )

    def test_the_belt_is_buffered_from_the_unmasked_boundary_by_ten_km(self, tmp_path):
        backend = FakeBackend()
        digest = _provider(backend, tmp_path).leakage_belt_hash(
            _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
        )
        assert digest
        assert ("belt", 10_000.0, 10.0, "EPSG:FAKE") in backend.queries

    def test_a_status_case_mismatch_refuses_rather_than_subtracting_nothing(self, tmp_path):
        """The filter matches exact strings; lowercase in the asset would match nothing."""
        backend = FakeBackend(statuses=("designated", "established"), districts={"10": GOOD})
        with pytest.raises(DataUnavailableError, match="Nothing would be subtracted"):
            self._facts(backend, tmp_path)
        assert backend.count("measure_forest") == 0

    def test_without_a_session_it_refuses(self):
        with pytest.raises(DataUnavailableError, match="without an Earth Engine session"):
            EarthEngineUnitConstruction().treated_unit(
                _boundary(),
                parameters=_parameters(),
                thresholds=Adr011Thresholds(),
            )


class TestProtectedAreasNeverReachAdmitted:
    """Acceptance: WDPA units never appear in pool.admitted, through the real rules and matching."""

    def _admitted(self, districts: dict[str, dict[str, Any]], tmp_path: pathlib.Path) -> set[str]:
        backend = FakeBackend(districts=districts)
        facts = _provider(backend, tmp_path).districts_for_rung(
            LADDER[0], _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
        )
        survivors = [
            f
            for f in facts
            if evaluate_district(f, project_eligible_area_km2=450.0, thresholds=Adr011Thresholds())
            is None
        ]
        covariates = dict.fromkeys(COVARIATE_KEYS, 1.0)
        pool = match_donors(
            "kariba-redd",
            covariates,
            {
                f.unit_id: {k: v + i * 0.01 for k, v in covariates.items()}
                for i, f in enumerate(survivors)
            },
            MatchingConfig(min_donors=0),
        )
        return {m.unit_id for m in pool.admitted}

    def test_a_wholly_protected_district_never_becomes_a_candidate(self, tmp_path):
        # The mask subtracts every protected pixel, so a wholly protected district has none.
        protected = {"forest": 2_000_000, "in_ecoregions": 2_000_000, "eligible": 0}
        admitted = self._admitted({"10": GOOD, "20": GOOD, "30": protected}, tmp_path)
        assert admitted == {"gaul2015:10", "gaul2015:20"}

    def test_protected_pixels_left_inside_a_unit_stop_the_run(self, tmp_path):
        leaking = {**GOOD, "protected": 1}
        with pytest.raises(DataUnavailableError, match="protected pixels"):
            self._admitted({"10": leaking}, tmp_path)

    def test_the_treated_unit_is_held_to_the_same_guard(self, tmp_path):
        class Leaking(FakeBackend):
            def measure_mask(self, query: MaskQuery) -> dict[str, Any]:
                return {"eligible": 10, "protected_overlap": 3}

        with pytest.raises(DataUnavailableError, match="protected pixels"):
            _provider(Leaking(), tmp_path).treated_unit(
                _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
            )


class TestTimingTrial:
    def test_it_reports_seconds_only_and_logs_no_count(self, tmp_path, caplog):
        caplog.set_level(logging.DEBUG)
        ticks = iter(range(100))
        backend = FakeBackend(districts={"10": GOOD})
        provider = EarthEngineUnitConstruction(
            session=_session(backend),
            backend=backend,
            carbon_projects=load_carbon_snapshot(_snapshot(tmp_path)),
            clock=lambda: float(next(ticks)),
        )
        seconds = provider.timing_trial(
            LADDER[0],
            _boundary(),
            parameters=_parameters(),
            thresholds=Adr011Thresholds(),
            covariates=_covariate_service(FakeBackend()),
        )
        assert set(seconds) == {
            "outline",
            "forest",
            "mask",
            "fragments",
            *(f"covariate:{k}" for k in COVARIATE_KEYS),
        }
        assert all(isinstance(v, float) for v in seconds.values())
        assert "1000000" not in caplog.text and "900" not in caplog.text

    def test_it_measures_real_cost_rather_than_reading_the_cache(self, tmp_path):
        backend = FakeBackend(districts={"10": GOOD})
        provider = _provider(backend, tmp_path, cache=ReductionCache(tmp_path / "cache"))
        for _ in range(2):
            provider.timing_trial(
                LADDER[0], _boundary(), parameters=_parameters(), thresholds=Adr011Thresholds()
            )
        assert backend.count("measure_mask") == 2


class TestCarbonSnapshot:
    def test_a_complete_file_loads(self, tmp_path):
        snapshot = load_carbon_snapshot(_snapshot(tmp_path))
        assert snapshot.snapshot_date == "2026-11-01"
        assert snapshot.excluded_districts == ("gaul2015:40",)
        assert len(snapshot.recipe_entries()) == 1
        assert snapshot.recipe_entries(exclude="VCS 902") == []
        assert len(snapshot.content_sha256) == 64

    def test_a_missing_file_refuses_and_points_to_the_format(self, tmp_path):
        with pytest.raises(DataUnavailableError, match=r"cases/carbon_projects/README\.md"):
            load_carbon_snapshot(tmp_path / "nope.yaml")

    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            ({"snapshot_date": "soon"}, "YYYY-MM-DD"),
            ({"source_file_sha256": "abc"}, "64 hex"),
            ({"source_uri": ""}, "source_uri"),
            ({"projects": []}, "projects"),
            ({"excluded_districts": [{"unit_id": "Binga", "project_id": "x"}]}, "gaul2015"),
        ],
    )
    def test_a_malformed_file_refuses(self, tmp_path, overrides, match):
        with pytest.raises(DataUnavailableError, match=match):
            load_carbon_snapshot(_snapshot(tmp_path, **overrides))

    def test_no_snapshot_file_is_committed_with_invented_data(self):
        """B3: the real file is obtained separately (R6)."""
        folder = REPO / "cases/carbon_projects"
        assert (folder / "README.md").exists()
        for path in folder.glob("*.yaml"):
            assert yaml.safe_load(path.read_text(encoding="utf-8"))["source_file_sha256"] != SHA


# --- the gate ----------------------------------------------------------------------


def _settings_file(tmp_path: pathlib.Path, **overrides: Any) -> RunSettings:
    payload: dict[str, Any] = {
        "case_id": "kariba-redd",
        "projection": "EPSG:FAKE",
        "raster_scale_m": 30,
        "raster_reducer": "nearest",
        "simplification_max_error_m": 10,
        "ecoregion_names": {
            "rung1": ["Fake A"],
            "rung2": ["Fake A", "Fake B"],
            "rung3": ["Fake A", "Fake B"],
        },
        "treated_ecoregion_rung": "rung1",
        "wdpa_release": "202610",
        "carbon_project_snapshot": str(_snapshot(tmp_path)),
        "road_source": "groads-v1",
        "road_asset": ROAD.asset,
        "road_source_sha256": SHA,
        "road_upload_date": "2026-11-05",
        "road_distance_scale_m": 100,
        "road_search_radius_km": 50,
        "native_scale_mask_rule": "fraction-weighted",
        "engine_transforms_confirmed": True,
    }
    payload.update(overrides)
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return load_run_settings(path)


def _blockers(settings: RunSettings, **overrides: Any) -> list[str]:
    fields: dict[str, Any] = {
        "case": get_case("kariba-redd"),
        "engine": {"implemented": {}},
        "earth_engine_key_set": True,
        "sensor": "landsat7",
    }
    fields.update(overrides)
    return [b.name for b in generation_blockers(settings, **fields)]


class TestGenerationGate:
    def test_a_complete_file_has_no_blockers(self, tmp_path):
        assert _blockers(_settings_file(tmp_path)) == []

    @pytest.mark.parametrize(
        "name",
        [
            "projection",
            "raster_scale_m",
            "raster_reducer",
            "simplification_max_error_m",
            "treated_ecoregion_rung",
            "wdpa_release",
            "carbon_project_snapshot",
            "road_source",
            "road_asset",
            "road_source_sha256",
            "road_upload_date",
            "road_distance_scale_m",
            "road_search_radius_km",
            "native_scale_mask_rule",
        ],
    )
    def test_every_required_setting_blocks_when_unset(self, tmp_path, name):
        assert name in _blockers(_settings_file(tmp_path, **{name: None}))

    @pytest.mark.parametrize("rung", ["rung1", "rung2", "rung3"])
    def test_each_rung_needs_literal_names(self, tmp_path, rung):
        names = {"rung1": ["A"], "rung2": ["A"], "rung3": ["A"], rung: None}
        assert f"ecoregion_names.{rung}" in _blockers(
            _settings_file(tmp_path, ecoregion_names=names)
        )

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("wdpa_release", "current"),
            ("road_source", "somewhere"),
            ("road_source_sha256", "abc"),
            ("road_upload_date", "yesterday"),
            ("native_scale_mask_rule", "whatever"),
            ("raster_reducer", "mean"),
            ("road_search_radius_km", -1),
            ("treated_ecoregion_rung", "rung9"),
        ],
    )
    def test_an_invalid_value_blocks(self, tmp_path, name, value):
        assert name in _blockers(_settings_file(tmp_path, **{name: value}))

    def test_a_missing_key_blocks_without_trying_to_read_it(self, tmp_path):
        assert "GEE_SERVICE_ACCOUNT_JSON" in _blockers(
            _settings_file(tmp_path), earth_engine_key_set=False
        )

    def test_an_unset_sensor_blocks(self, tmp_path):
        assert "EARTH_ENGINE_SENSOR" in _blockers(_settings_file(tmp_path), sensor=None)

    def test_a_missing_snapshot_file_blocks(self, tmp_path):
        settings = _settings_file(tmp_path, carbon_project_snapshot=str(tmp_path / "no.yaml"))
        assert "carbon_project_snapshot" in _blockers(settings)

    def test_the_osm_fallback_needs_its_reason_recorded(self, tmp_path):
        """V1: not a silent alternative."""
        settings = _settings_file(tmp_path, road_source="osm-current", road_fallback_reason=None)
        assert "road_fallback_reason" in _blockers(settings)
        settings = _settings_file(
            tmp_path, road_source="osm-current", road_fallback_reason="upload refused"
        )
        assert _blockers(settings) == []

    def test_parameters_refuse_to_guess(self, tmp_path):
        settings = _settings_file(tmp_path, projection=None)
        snapshot = load_carbon_snapshot(_snapshot(tmp_path))
        with pytest.raises(ConfigurationError, match="projection"):
            settings.parameters(get_case("kariba-redd"), snapshot)

    def test_parameters_take_the_donor_counts_from_the_case(self, tmp_path):
        snapshot = load_carbon_snapshot(_snapshot(tmp_path))
        parameters = _settings_file(tmp_path).parameters(get_case("kariba-redd"), snapshot)
        assert (parameters.pool_size, parameters.min_donors, parameters.max_donors) == (80, 30, 50)
        assert parameters.excluded_carbon_project_districts == ("gaul2015:40",)
        assert parameters.carbon_registry_snapshot_date == "2026-11-01"


class TestEngineTransformsGuard:
    """V9(a): the ladder must not match on a different scale than the run."""

    def test_it_blocks_while_the_engine_does_not_report_them(self, tmp_path):
        settings = _settings_file(tmp_path, engine_transforms_confirmed=None)
        assert "engine_transforms_confirmed" in _blockers(settings)

    def test_the_engine_reporting_them_clears_it(self, tmp_path):
        settings = _settings_file(tmp_path, engine_transforms_confirmed=None)
        engine = {"implemented": {ENGINE_TRANSFORMS_CAPABILITY: True}}
        assert _blockers(settings, engine=engine) == []

    def test_an_explicit_confirmation_clears_it(self, tmp_path):
        assert _blockers(_settings_file(tmp_path, engine_transforms_confirmed=True)) == []

    def test_false_does_not_count_as_confirmed(self, tmp_path):
        settings = _settings_file(tmp_path, engine_transforms_confirmed=False)
        assert "engine_transforms_confirmed" in _blockers(settings)

    def test_the_guard_reads_where_the_real_engine_reports_capabilities(self):
        from groundtruth.engine import describe_engine

        assert isinstance(describe_engine()["implemented"], dict)


class TestCommittedRunSettings:
    def _raw(self) -> dict[str, Any]:
        return dict(load_run_settings(run_settings_path("kariba-redd")).raw)

    def test_the_agreed_values_are_recorded(self):
        raw = self._raw()
        assert raw["raster_scale_m"] == 30
        assert raw["road_source"] == "groads-v1"

    def test_the_decisions_are_attributed(self):
        text = run_settings_path("kariba-redd").read_text(encoding="utf-8")
        assert "agreed with Viraj (C4), 2026-11-05" in text

    def test_it_never_names_a_moving_wdpa_asset(self):
        assert self._raw()["wdpa_release"] != "current"


# --- the generation script ---------------------------------------------------------


def _load_script() -> Any:
    path = REPO / "experiments/kariba_benchmark/generate_unit_set.py"
    spec = importlib.util.spec_from_file_location("generate_unit_set_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Observing(FakeBackend):
    """The fake, plus a clear pre-period for every candidate."""

    def list_scenes(self, query: Any) -> dict[str, Any]:
        self._record("list_scenes")
        return {"n_available": 3, "ids": ["a", "b", "c"], "versions": [1, 2, 3]}

    def reduce(self, query: Any) -> dict[str, Any]:
        self._record("reduce")
        self.queries.append(("reduce", query.year))
        return {"mean": {"index": 0.4}, "histogram": {"count": {"5": 100}}}


def _app_settings(tmp_path: pathlib.Path, **overrides: Any) -> Settings:
    fields: dict[str, Any] = {
        "gee_service_account_json": KEY_JSON,
        "earth_engine_sensor": "landsat7",
        "earth_engine_max_requests_per_minute": 10**9,  # fakes need no real waiting
        "data_dir": tmp_path / "data",
        "_env_file": None,
    }
    fields.update(overrides)
    return Settings(**fields)


class TestGenerationScript:
    def _districts(self, n: int = 90) -> dict[str, dict[str, Any]]:
        return {str(100 + i): dict(GOOD) for i in range(n)}

    def test_it_refuses_before_contacting_anything(self, tmp_path):
        script = _load_script()
        backend = Observing()
        settings = _settings_file(tmp_path, projection=None)
        with pytest.raises(script.GenerationBlockedError) as caught:
            script.generate(
                get_case("kariba-redd"),
                settings,
                _app_settings(tmp_path),
                backend=backend,
                engine={"implemented": {}},
            )
        assert "projection" in [b.name for b in caught.value.blockers]
        assert backend.calls == []

    def test_main_prints_every_blocker_and_exits_2(self, capsys, monkeypatch, tmp_path):
        """A setting nobody decided stops the run, however complete the rest of the file is."""
        script = _load_script()
        unset = _settings_file(tmp_path, projection=None)
        monkeypatch.setattr(script, "get_settings", lambda: _app_settings(tmp_path))
        monkeypatch.setattr(script, "load_run_settings", lambda path: unset)
        assert script.main(["--case", "kariba-redd"]) == 2
        out = capsys.readouterr().out
        assert "REFUSED" in out and "Nothing was fetched" in out
        assert "projection" in out

    def test_a_full_run_on_fakes_climbs_and_builds_the_manifest(self, tmp_path):
        script = _load_script()
        backend = Observing(districts=self._districts())
        unit_set = script.generate(
            get_case("kariba-redd"),
            _settings_file(tmp_path),
            _app_settings(tmp_path),
            backend=backend,
            engine={"implemented": {}},
        )
        assert unit_set.rung_used == 1
        assert len(unit_set.candidates) >= 80

        manifest = unit_set.manifest
        assert manifest.belt_geometry_hash
        assert manifest.run_settings_sha256 and manifest.carbon_snapshot_sha256
        assert manifest.boundary_source_uri and manifest.boundary_retrieved_at
        assert manifest.leakage_belt_km == 10.0
        assert {r["dataset_id"] for r in manifest.covariate_refs} == {
            "chirps-daily",
            "srtm-gl1",
            "groads-v1",
            "worldpop-gp-100m",
        }
        decisions = " ".join(manifest.pinned_decisions)
        assert "Adopted: not subtracted" in decisions
        assert "agreed with Viraj (C4), 2026-11-05" in decisions
        for name in ("chirps-daily", "worldpop-gp-100m", "groads-v1"):
            assert name in manifest.dataset_reference_periods
        assert manifest.rung_records[0]["admitted_donors"] == 50
        assert manifest.as_dataset_ref().version == manifest.content_hash

        # Every candidate can be observed and measured: it carries outline and recipe.
        unit = unit_set.candidate_unit_refs()[0]
        assert MASK_MEMBER in unit.geometry and unit.area_ha
        assert MASK_MEMBER in unit_set.treated_unit.geometry

    def test_only_the_pre_period_is_observed_before_the_pool_is_fixed(self, tmp_path):
        script = _load_script()
        backend = Observing(districts=self._districts())
        script.generate(
            get_case("kariba-redd"),
            _settings_file(tmp_path),
            _app_settings(tmp_path),
            backend=backend,
            engine={"implemented": {}},
        )
        years = {q[1] for q in backend.queries if isinstance(q, tuple) and q[0] == "reduce"}
        assert years == set(range(2001, 2011))

    def test_a_shortfall_climbs_and_then_refuses(self, tmp_path):
        from groundtruth.contracts.errors import DonorPoolError

        script = _load_script()
        backend = Observing(districts=self._districts(5))
        with pytest.raises(DonorPoolError, match="ladder was exhausted"):
            script.generate(
                get_case("kariba-redd"),
                _settings_file(tmp_path),
                _app_settings(tmp_path),
                backend=backend,
                engine={"implemented": {}},
            )

    def test_the_timing_trial_is_not_blocked_by_the_engine_guard(self, tmp_path):
        script = _load_script()
        seconds = script.timing_trial(
            get_case("kariba-redd"),
            _settings_file(tmp_path, engine_transforms_confirmed=None),
            _app_settings(tmp_path),
            backend=Observing(districts=self._districts(1)),
            engine={"implemented": {}},
        )
        assert "mask" in seconds

    def test_the_listing_needs_only_the_key(self, tmp_path):
        script = _load_script()
        listing = script.study_area_listing(_app_settings(tmp_path), backend=Observing())
        assert listing["eco_names"] == ["Fake A", "Fake B"]
        assert listing["worldpop_2000_countries"] == ["ZMB", "ZWE"]
        assert not any(isinstance(v, int) for values in listing.values() for v in values)


class TestNoFixtureFallback:
    PATH = (
        "platform/datasets/covariates.py",
        "platform/datasets/ee_units.py",
        "platform/datasets/ee_mask.py",
        "platform/datasets/session.py",
        "platform/units/provider.py",
        "platform/units/carbon_projects.py",
        "platform/units/run_settings.py",
    )

    def test_the_real_path_never_imports_the_synthetic_provider(self):
        for name in self.PATH:
            tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module, *(a.name for a in node.names)]
                elif isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                for module in modules:
                    assert "synthetic" not in module.lower(), f"{name} imports {module}"
                    assert "fixture" not in module.lower(), f"{name} imports {module}"

    def test_observed_analysis_runs_still_refuse(self):
        request = get_case("kariba-redd").to_request(data_mode="observed")
        with pytest.raises(DataUnavailableError, match="not implemented"):
            earth_engine_access(request)


class TestRunParametersGate:
    def test_the_existing_gate_still_refuses_incomplete_parameters(self):
        with pytest.raises(MissingRunParameterError):
            _parameters(projection="").validate()
