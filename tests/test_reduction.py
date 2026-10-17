"""The Earth-observation reduction methodology (issue #1, engine half)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from groundtruth.contracts.errors import EstimationError
from groundtruth.contracts.request import AnalysisWindow
from groundtruth.contracts.types import Indicator, TimeSeries
from groundtruth.engine.observation.alignment import pre_period_coverage
from groundtruth.engine.observation.indices import evi
from groundtruth.engine.observation.reduction import (
    SENSORS,
    qa_pixel_mask,
    reduce_period,
    reduction_spec,
    sensors_for_year,
    to_reflectance,
)
from groundtruth.engine.run import describe_engine

S2 = SENSORS["sentinel2"]
L8 = SENSORS["landsat8"]


def _landsat_dn(rho: float) -> float:
    return (rho + 0.2) / 0.0000275


class TestReflectance:
    def test_sentinel2_digital_numbers_scale_to_reflectance(self):
        assert to_reflectance(np.array([5000.0, 10000.0]), S2) == pytest.approx([0.5, 1.0])

    def test_landsat_collection2_scale_and_offset(self):
        dn = np.array([_landsat_dn(0.3), _landsat_dn(0.05)])
        assert to_reflectance(dn, L8) == pytest.approx([0.3, 0.05])

    def test_physically_impossible_reflectance_is_masked(self):
        # Landsat DN 0 is fill: 0 * scale - 0.2 = -0.2.
        out = to_reflectance(np.array([0.0, 50000.0]), L8)
        assert np.isnan(out).all()

    def test_evi_on_digital_numbers_would_be_wrong(self):
        """The +1 in EVI's denominator assumes reflectance, not DN."""
        nir, red, blue = 0.35, 0.08, 0.04
        on_reflectance = float(evi(np.array(nir), np.array(red), np.array(blue)))
        on_dn = float(evi(np.array(nir * 1e4), np.array(red * 1e4), np.array(blue * 1e4)))
        expected = 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)
        assert on_reflectance == pytest.approx(expected)
        assert on_dn != pytest.approx(expected, rel=0.01)


class TestQualityMasks:
    @pytest.mark.parametrize(
        ("qa", "usable"),
        [
            (0b0000000, True),  # clear
            (0b1000000, True),  # bit 6 (clear flag) set: not an invalid bit
            (0b0000001, False),  # fill
            (0b0000010, False),  # dilated cloud
            (0b0001000, False),  # cloud
            (0b0010000, False),  # cloud shadow
            (0b0100000, False),  # snow
        ],
    )
    def test_landsat_qa_pixel_bits(self, qa, usable):
        assert bool(qa_pixel_mask(np.array([qa]))[0]) is usable

    def test_radiometric_saturation_is_unusable(self):
        mask = qa_pixel_mask(np.array([0, 0]), radsat=np.array([0, 4]))
        assert mask.tolist() == [True, False]


def _chip(n_scenes: int, nir: float, red: float) -> dict[str, np.ndarray]:
    shape = (n_scenes, 2, 2)
    return {"nir": np.full(shape, nir * 1e4), "red": np.full(shape, red * 1e4)}


class TestReducePeriod:
    def test_recovers_a_known_ndvi_target_through_cloud(self):
        spec = reduction_spec(Indicator.NDVI, "sentinel2")
        bands = _chip(5, nir=0.40, red=0.05)
        scl = np.full((5, 2, 2), 4)  # vegetation
        # Two scenes are bright cloud over the whole chip: near-zero NDVI.
        bands["nir"][[1, 3]] = 0.62e4
        bands["red"][[1, 3]] = 0.60e4
        scl[[1, 3]] = 9
        zone = np.ones((2, 2), dtype=bool)

        result = reduce_period(spec, bands, scl, zone)
        assert result.value == pytest.approx((0.40 - 0.05) / (0.40 + 0.05))
        assert result.n_valid_observations == 3
        assert result.clear_pixel_fraction == 1.0
        assert result.n_scenes == 5

    def test_the_median_absorbs_a_cloudy_minority_but_not_a_majority(self):
        spec = reduction_spec(Indicator.NDVI, "sentinel2")
        zone = np.ones((2, 2), dtype=bool)
        scl = np.full((5, 2, 2), 4)  # cloud never flagged
        target = 0.35 / 0.45

        minority = _chip(5, nir=0.40, red=0.05)
        minority["nir"][[1, 3]] = 0.62e4
        minority["red"][[1, 3]] = 0.60e4
        assert reduce_period(spec, minority, scl, zone).value == pytest.approx(target)

        majority = _chip(5, nir=0.40, red=0.05)
        majority["nir"][[0, 1, 3]] = 0.62e4
        majority["red"][[0, 1, 3]] = 0.60e4
        assert reduce_period(spec, majority, scl, zone).value < 0.1

    def test_index_is_taken_per_scene_before_the_median(self):
        """A band-first composite pairs red and NIR from different dates."""
        spec = reduction_spec(Indicator.NDVI, "sentinel2")
        nir = np.array([0.20, 0.30, 0.50]).reshape(3, 1, 1) * 1e4
        red = np.array([0.02, 0.15, 0.10]).reshape(3, 1, 1) * 1e4
        scl = np.full((3, 1, 1), 4)
        result = reduce_period(spec, {"nir": nir, "red": red}, scl, np.ones((1, 1), dtype=bool))

        per_scene = (nir - red) / (nir + red)
        assert result.value == pytest.approx(float(np.median(per_scene)))
        band_first = (np.median(nir) - np.median(red)) / (np.median(nir) + np.median(red))
        assert result.value != pytest.approx(float(band_first))

    def test_a_fully_clouded_pixel_leaves_the_zone_mean_and_lowers_coverage(self):
        spec = reduction_spec(Indicator.NDVI, "sentinel2")
        bands = _chip(4, nir=0.40, red=0.05)
        scl = np.full((4, 2, 2), 4)
        scl[:, 0, 0] = 8  # one pixel never clear
        bands["nir"][:, 0, 0] = 0.6e4
        bands["red"][:, 0, 0] = 0.6e4
        result = reduce_period(spec, bands, scl, np.ones((2, 2), dtype=bool))
        assert result.value == pytest.approx(0.35 / 0.45)
        assert result.clear_pixel_fraction == 0.75

    def test_a_year_with_no_clear_pixel_is_reported_not_filled(self):
        spec = reduction_spec(Indicator.NDVI, "landsat8")
        bands = {
            "nir": np.full((2, 2, 2), _landsat_dn(0.4)),
            "red": np.full((2, 2, 2), _landsat_dn(0.05)),
        }
        qa = np.full((2, 2, 2), 0b0001000)  # all cloud
        result = reduce_period(spec, bands, qa, np.ones((2, 2), dtype=bool))
        assert np.isnan(result.value)
        assert result.n_valid_observations == 0
        assert result.clear_pixel_fraction == 0.0

    def test_landsat_chain_recovers_a_known_target(self):
        spec = reduction_spec(Indicator.NBR, "landsat8")
        bands = {
            "nir": np.full((3, 1, 1), _landsat_dn(0.30)),
            "swir2": np.full((3, 1, 1), _landsat_dn(0.10)),
        }
        qa = np.zeros((3, 1, 1), dtype=int)
        result = reduce_period(spec, bands, qa, np.ones((1, 1), dtype=bool))
        assert result.value == pytest.approx(0.20 / 0.40)
        assert result.n_valid_observations == 3

    def test_missing_bands_are_refused(self):
        spec = reduction_spec(Indicator.EVI, "sentinel2")
        with pytest.raises(EstimationError):
            reduce_period(spec, _chip(1, 0.4, 0.05), np.full((1, 2, 2), 4), np.ones((2, 2), bool))


class TestSpec:
    def test_kariba_pre_period_years_need_landsat_5_or_7(self):
        assert sensors_for_year(2005) == ("landsat7", "landsat5")
        assert "sentinel2" not in sensors_for_year(2010)
        assert {"sentinel2", "landsat8"} <= set(sensors_for_year(2020))

    def test_nbr_uses_swir2_on_every_sensor(self):
        for name in SENSORS:
            bands = reduction_spec(Indicator.NBR, name).as_dict()["bands"]
            assert bands["swir2"] in {"B12", "SR_B7"}

    def test_non_spectral_indicators_are_not_reduced_from_scenes(self):
        with pytest.raises(EstimationError):
            reduction_spec(Indicator.FOREST_AREA_HA, "sentinel2")

    def test_the_spec_is_published_through_describe_engine_as_plain_data(self):
        reduction = describe_engine()["reduction"]
        json.dumps(reduction)  # must be JSON-safe for the platform
        assert reduction["scale_m"] == 30
        s2_ndvi = next(
            s for s in reduction["specs"] if s["sensor"] == "sentinel2" and s["indicator"] == "ndvi"
        )
        assert s2_ndvi["collection"] == "COPERNICUS/S2_SR_HARMONIZED"
        assert s2_ndvi["reflectance"] == {"scale": 1e-4, "offset": 0.0, "valid_range": [0.0, 1.0]}
        assert s2_ndvi["mask"]["invalid_classes"] == [0, 1, 3, 8, 9, 10, 11]
        assert s2_ndvi["composite"] == "per-scene-index/annual-median"
        assert s2_ndvi["observation_count"] == "zonal-median-of-per-pixel-clear-scene-count"
        assert describe_engine()["implemented"]["cross_sensor_calibration"] is False


class TestPrePeriodCoverage:
    WINDOW = AnalysisWindow(pre_start=2001, pre_end=2004, post_start=2005, post_end=2006)

    def _series(self, uid: str, counts: tuple[int, ...] | None) -> TimeSeries:
        periods = tuple(range(2001, 2007))
        return TimeSeries(
            unit_id=uid,
            indicator=Indicator.NDVI,
            periods=periods,
            values=tuple(0.5 for _ in periods),
            n_valid_observations=counts,
        )

    def test_a_unit_is_as_well_observed_as_its_worst_pre_year(self):
        coverage = pre_period_coverage(
            self.WINDOW,
            {
                "a": self._series("a", (12, 9, 2, 14, 0, 0)),
                "b": self._series("b", (5, 5, 5, 5, 1, 1)),
            },
        )
        # Post-period counts (0 and 1) do not enter the pre-period rule.
        assert coverage == {"a": 2, "b": 5}

    def test_any_unit_without_counts_disables_the_rule_entirely(self):
        coverage = pre_period_coverage(
            self.WINDOW,
            {"a": self._series("a", (5, 5, 5, 5, 5, 5)), "b": self._series("b", None)},
        )
        assert coverage is None


def test_a_sparse_pre_year_excludes_the_donor_at_matching():
    from groundtruth.contracts.ports import DataAccess, ObservationSpec
    from groundtruth.engine import run_analysis
    from groundtruth.platform.cases.registry import get_case
    from groundtruth.platform.datasets.access import synthetic_access

    request = get_case("kariba-redd").to_request(seed=20260101)
    access = synthetic_access(request, true_effect=0.06)
    inner = access.observations
    sparse_units: list[str] = []

    class SparseFirstDonors:
        def series(self, spec: ObservationSpec) -> TimeSeries:
            s = inner.series(spec)
            if spec.unit.unit_id != request.project.unit_id and len(sparse_units) < 3:
                sparse_units.append(spec.unit.unit_id)
                counts = list(s.n_valid_observations or ())
                counts[2] = 2  # a cloud-starved 2003
                return s.model_copy(update={"n_valid_observations": tuple(counts)})
            return s

        def dataset(self, indicator):  # type: ignore[no-untyped-def]
            return inner.dataset(indicator)

        def provenance(self, spec):  # type: ignore[no-untyped-def]
            return inner.provenance(spec)

    result = run_analysis(
        request,
        DataAccess(
            observations=SparseFirstDonors(), covariates=access.covariates, donors=access.donors
        ),
    )
    assert result.status.value == "completed"
    assert result.bundle is not None
    assert result.bundle.require("matching.n_candidates_excluded").value >= 3
    assert any("candidate regions were excluded" in w for w in result.bundle.warnings)
    assert not any("could not be applied" in w for w in result.bundle.warnings)
