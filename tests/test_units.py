"""ADR-011 unit construction: geometry, eligibility rules, ladder, manifest.

These tests are deterministic and offline by construction. The masking provider
is the one piece that needs Earth Engine, and the tests that exercise the rules
supply measured facts directly — which is the same thing a real provider will
hand the rules layer, without pretending to have measured anything.

The fakes here are test doubles for the *provider*, never substitutes for a real
donor pool: no test asserts a scientific result, and the production path is
asserted to refuse when the provider is unavailable.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from groundtruth.contracts.errors import DataUnavailableError, DonorPoolError
from groundtruth.platform.units import (
    LADDER,
    Adr011Thresholds,
    DistrictFacts,
    EarthEngineUnitConstruction,
    ExclusionCategory,
    MissingRunParameterError,
    RunParameters,
    build_manifest,
    climb_ladder,
    evaluate_district,
    generate_unit_set,
    load_registry_boundary,
    screen_rung,
)
from groundtruth.platform.units.geodesic import (
    describe_multipolygon,
    intersection_area_km2,
    is_closed,
    is_counter_clockwise,
    polygon_area_m2,
    ring_area_m2,
    self_intersections,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
KARIBA_BOUNDARY = REPO_ROOT / "cases" / "boundaries" / "kariba-redd.geojson"


def _square(lon0: float, lat0: float, side_deg: float) -> list[tuple[float, float]]:
    """A counter-clockwise closed square ring."""
    return [
        (lon0, lat0),
        (lon0 + side_deg, lat0),
        (lon0 + side_deg, lat0 + side_deg),
        (lon0, lat0 + side_deg),
        (lon0, lat0),
    ]


def _parameters(**overrides) -> RunParameters:
    """A fully pinned parameter set, as a real run would have to supply."""
    payload = {
        "projection": "EPSG:102022",
        "raster_scale_m": 30.0,
        "raster_reducer": "mean",
        "simplification_max_error_m": 1.0,
        "ecoregion_names": {
            "rung1": ("Southern Miombo woodlands",),
            "rung2": ("Southern Miombo woodlands", "Eastern Miombo woodlands"),
            "rung3": ("Southern Miombo woodlands", "Eastern Miombo woodlands"),
        },
        "wdpa_release": "WDPA_Sep2026",
        "carbon_registry_snapshot_date": "2026-09-20",
        "pool_size": 80,
        "min_donors": 40,
        "max_donors": 50,
    }
    payload.update(overrides)
    return RunParameters(**payload)


def _facts(unit_id: str, **overrides) -> DistrictFacts:
    payload = {
        "unit_id": unit_id,
        "adm2_code": unit_id.split(":")[-1],
        "country": "ZWE",
        "eligible_area_km2": 6000.0,
        "forest_share_in_target_ecoregions": 0.8,
        "intersects_leakage_belt": False,
        "contains_registered_project_without_geometry": False,
    }
    payload.update(overrides)
    return DistrictFacts(**payload)


class TestGeodesicArea:
    """Area has to be right, because the band and the floor are defined on it."""

    def test_a_one_degree_square_at_the_equator(self):
        """~111.3 km x 110.6 km, within the method's stated tolerance."""
        area_km2 = abs(ring_area_m2(_square(0.0, 0.0, 1.0))) / 1e6
        assert 12_000 < area_km2 < 12_500

    def test_area_shrinks_with_latitude(self):
        """A degree of longitude is shorter near the poles."""
        equator = abs(ring_area_m2(_square(0.0, 0.0, 1.0)))
        high = abs(ring_area_m2(_square(0.0, 60.0, 1.0)))
        assert high < equator / 1.8

    def test_orientation_is_signed(self):
        ring = _square(30.0, -17.0, 0.5)
        assert is_counter_clockwise(ring)
        assert not is_counter_clockwise(list(reversed(ring)))

    def test_a_hole_is_subtracted(self):
        outer = _square(30.0, -17.0, 1.0)
        inner = list(reversed(_square(30.25, -16.75, 0.5)))
        with_hole = polygon_area_m2([outer, inner])
        without = polygon_area_m2([outer])
        assert with_hole < without
        assert math.isclose(without - with_hole, abs(ring_area_m2(inner)), rel_tol=1e-9)

    def test_area_is_translation_stable_along_a_parallel(self):
        """Determinism: the same shape at the same latitude has the same area."""
        a = abs(ring_area_m2(_square(20.0, -17.0, 0.4)))
        b = abs(ring_area_m2(_square(31.0, -17.0, 0.4)))
        assert math.isclose(a, b, rel_tol=1e-9)


class TestGeometryValidity:
    def test_a_closed_ring_is_recognised(self):
        assert is_closed(_square(0.0, 0.0, 1.0))
        assert not is_closed(_square(0.0, 0.0, 1.0)[:-1])

    def test_a_simple_ring_has_no_self_intersections(self):
        assert self_intersections(_square(0.0, 0.0, 1.0)) == []

    def test_a_bowtie_is_caught(self):
        bowtie = [(0.0, 0.0), (1.0, 1.0), (1.0, 0.0), (0.0, 1.0), (0.0, 0.0)]
        assert self_intersections(bowtie)

    def test_disjoint_rings_do_not_intersect(self):
        assert intersection_area_km2(_square(0.0, 0.0, 1.0), _square(5.0, 5.0, 1.0)) == 0.0

    def test_overlap_area_converges(self):
        """Half-overlapping unit squares share about half of one square."""
        a = _square(0.0, 0.0, 1.0)
        b = _square(0.5, 0.0, 1.0)
        coarse = intersection_area_km2(a, b, bands=500)
        fine = intersection_area_km2(a, b, bands=4000)
        assert math.isclose(coarse, fine, rel_tol=1e-3)
        assert 6_000 < fine < 6_300

    def test_report_counts_parts_and_overlaps(self):
        multipolygon = [[_square(0.0, 0.0, 1.0)], [_square(0.5, 0.0, 1.0)]]
        report = describe_multipolygon(multipolygon, overlap_bands=1000)
        assert report.parts == 2
        assert report.holes == 0
        assert report.unclosed_rings == ()
        assert report.self_intersecting_rings == ()
        assert len(report.overlaps) == 1
        assert report.union_area_km2 < report.sum_of_parts_km2


@pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="Kariba boundary not obtained (#2)")
class TestKaribaBoundary:
    """The committed registry artifact, checked against its own provenance record."""

    @pytest.fixture(scope="class")
    @classmethod
    def boundary(cls):
        return load_registry_boundary(KARIBA_BOUNDARY)

    def test_it_loads_as_one_feature(self, boundary):
        assert boundary.case_id == "kariba-redd"
        assert boundary.geometry["type"] == "MultiPolygon"
        assert boundary.report.parts == 5

    def test_geometry_is_valid(self, boundary):
        assert boundary.report.is_valid
        assert boundary.report.unclosed_rings == ()
        assert boundary.report.self_intersecting_rings == ()
        assert boundary.report.out_of_range_vertices == 0

    def test_exterior_rings_follow_rfc_7946(self, boundary):
        assert boundary.report.clockwise_exterior_rings == ()

    def test_the_known_part_overlap_is_still_there(self, boundary):
        """Parts 1 and 5 are adjacent parcels sharing a digitised sliver.

        The artifact is never repaired, so this is a property of the data and
        the test exists to notice if someone quietly dissolves it.
        """
        assert len(boundary.report.overlaps) == 1
        overlap = boundary.report.overlaps[0]
        assert (overlap.part_a, overlap.part_b) == (1, 5)
        assert 0.27 < overlap.area_km2 < 0.31

    def test_union_area_matches_the_documented_boundary_area(self, boundary):
        """The project description states 1,077,930 ha for the RDC boundaries."""
        assert math.isclose(boundary.boundary_area_ha, 1_072_638, rel_tol=0.01)
        assert abs(boundary.boundary_area_ha - 1_077_930) / 1_077_930 < 0.01

    def test_the_provenance_record_agrees_with_the_geometry(self, boundary):
        provenance = json.loads(
            (KARIBA_BOUNDARY.parent / "kariba-redd.provenance.json").read_text(encoding="utf-8")
        )
        assert provenance["artifact_facts"]["parts"] == boundary.report.parts
        assert provenance["source"]["sha256"]
        recorded = provenance["validation"]["part_overlap"]["intersection_area_km2"]
        assert math.isclose(recorded, boundary.report.overlaps[0].area_km2, rel_tol=0.05)

    def test_the_unit_ref_carries_boundary_not_eligible_area(self, boundary):
        """Masking has not happened yet, so this must not look like an eligible area."""
        ref = boundary.as_unit_ref()
        assert ref.unit_id == "kariba-redd"
        assert ref.area_ha == pytest.approx(boundary.boundary_area_ha)

    def test_a_missing_boundary_refuses(self, tmp_path):
        with pytest.raises(DataUnavailableError, match="issue #2"):
            load_registry_boundary(tmp_path / "nope.geojson")


class TestEligibilityRules:
    """ADR-011's admission rules, one at a time."""

    thresholds = Adr011Thresholds()
    project_area = 5000.0

    def test_a_comparable_district_is_eligible(self):
        assert (
            evaluate_district(
                _facts("gaul2015:1"),
                project_eligible_area_km2=self.project_area,
                thresholds=self.thresholds,
            )
            is None
        )

    def test_an_emptied_district_is_excluded_first(self):
        outcome = evaluate_district(
            _facts("gaul2015:2", eligible_area_km2=0.0, intersects_leakage_belt=True),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert outcome is not None
        assert outcome.category is ExclusionCategory.EMPTY_AFTER_MASK

    def test_leakage_belt_exclusion(self):
        outcome = evaluate_district(
            _facts("gaul2015:3", intersects_leakage_belt=True),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert outcome is not None
        assert outcome.category is ExclusionCategory.LEAKAGE_BELT
        assert "10 km leakage belt" in outcome.reason

    def test_a_carbon_project_without_geometry_excludes_the_district(self):
        outcome = evaluate_district(
            _facts("gaul2015:4", contains_registered_project_without_geometry=True),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert outcome is not None
        assert outcome.category is ExclusionCategory.CARBON_PROJECT

    @pytest.mark.parametrize(
        ("share", "excluded"),
        [(0.49, True), (0.50, False), (0.51, False)],
    )
    def test_the_ecoregion_rule_is_a_half_share(self, share, excluded):
        outcome = evaluate_district(
            _facts("gaul2015:5", forest_share_in_target_ecoregions=share),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert (outcome is not None) is excluded
        if outcome:
            assert outcome.category is ExclusionCategory.ECOREGION_SHARE

    def test_the_absolute_floor_fires_below_500_km2(self):
        outcome = evaluate_district(
            _facts("gaul2015:6", eligible_area_km2=499.0),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert outcome is not None
        assert outcome.category is ExclusionCategory.AREA_FLOOR

    @pytest.mark.parametrize(
        ("area", "excluded"),
        [(1666.0, True), (1667.0, False), (15_000.0, False), (15_001.0, True)],
    )
    def test_the_area_band_is_a_third_to_three_times(self, area, excluded):
        outcome = evaluate_district(
            _facts("gaul2015:7", eligible_area_km2=area),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert (outcome is not None) is excluded
        if outcome:
            assert outcome.category is ExclusionCategory.AREA_BAND

    def test_the_band_is_derived_from_the_eligible_area(self):
        """A band from an unmeasured project area would admit everything."""
        with pytest.raises(ValueError, match="measured eligible area"):
            self.thresholds.area_band_km2(0.0)

    def test_screening_is_order_independent(self):
        districts = [_facts(f"gaul2015:{i}") for i in (3, 1, 2)]
        forward = screen_rung(
            1, districts, project_eligible_area_km2=self.project_area, thresholds=self.thresholds
        )
        backward = screen_rung(
            1,
            list(reversed(districts)),
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        assert [u.unit_id for u in forward.eligible] == [u.unit_id for u in backward.eligible]

    def test_every_category_appears_in_the_counts(self):
        screening = screen_rung(
            1,
            [_facts("gaul2015:8", intersects_leakage_belt=True)],
            project_eligible_area_km2=self.project_area,
            thresholds=self.thresholds,
        )
        counts = screening.counts_by_category()
        assert set(counts) == {c.value for c in ExclusionCategory}
        assert counts[ExclusionCategory.LEAKAGE_BELT.value] == 1
        assert counts[ExclusionCategory.AREA_BAND.value] == 0


class TestRunParameters:
    """The open-parameter gate refuses rather than guessing."""

    def test_a_complete_set_validates(self):
        _parameters().validate()

    @pytest.mark.parametrize(
        "override",
        [
            {"projection": ""},
            {"raster_scale_m": 0.0},
            {"raster_reducer": ""},
            {"wdpa_release": ""},
            {"carbon_registry_snapshot_date": ""},
            {"pool_size": 0},
            {"min_donors": 0},
        ],
    )
    def test_a_missing_parameter_is_refused(self, override):
        with pytest.raises(MissingRunParameterError):
            _parameters(**override).validate()

    def test_max_donors_below_min_is_refused(self):
        with pytest.raises(MissingRunParameterError):
            _parameters(min_donors=50, max_donors=40).validate()

    def test_an_unpinned_rung_is_refused(self):
        params = _parameters(ecoregion_names={"rung1": ("Southern Miombo woodlands",)})
        with pytest.raises(MissingRunParameterError, match="rung2"):
            params.validate()


class TestLadder:
    """The stopping rule, which is where a post-hoc choice would hide."""

    def _climb(self, per_rung, parameters=None):
        """Climb with scripted (eligible, admitted) counts per rung."""
        params = parameters or _parameters()
        seen: list[int] = []

        def screen(rung):
            seen.append(rung.number)
            eligible, _ = per_rung[rung.number - 1]
            return screen_rung(
                rung.number,
                [_facts(f"gaul2015:{rung.number}-{i}") for i in range(eligible)],
                project_eligible_area_km2=5000.0,
                thresholds=Adr011Thresholds(),
            )

        def admitted(rung, screening):
            return per_rung[rung.number - 1][1]

        return climb_ladder(screen=screen, count_admitted=admitted, parameters=params), seen

    def test_it_stops_at_the_first_rung_satisfying_both_conditions(self):
        outcome, seen = self._climb([(80, 40), (200, 100), (300, 150)])
        assert outcome.rung_used == 1
        assert seen == [1]
        assert len(outcome.records) == 1

    def test_enough_candidates_but_too_few_donors_still_advances(self):
        """The defect the ADR review closed: two counts, one rule."""
        outcome, seen = self._climb([(84, 14), (120, 46), (300, 150)])
        assert outcome.rung_used == 2
        assert seen == [1, 2]

    def test_enough_donors_but_too_few_candidates_still_advances(self):
        outcome, _ = self._climb([(40, 40), (120, 46), (300, 150)])
        assert outcome.rung_used == 2

    def test_every_rung_climbed_is_recorded_including_the_ones_passed(self):
        outcome, _ = self._climb([(10, 2), (40, 20), (200, 90)])
        assert [r.rung for r in outcome.records] == [1, 2, 3]
        assert [r.eligible_candidates for r in outcome.records] == [10, 40, 200]
        assert [r.admitted_donors for r in outcome.records] == [2, 20, 90]
        assert [r.satisfied_stopping_rule for r in outcome.records] == [False, False, True]

    def test_exhausting_the_ladder_refuses(self):
        with pytest.raises(DonorPoolError, match="ladder was exhausted"):
            self._climb([(10, 2), (20, 5), (30, 9)])

    def test_the_refusal_names_both_counts(self):
        with pytest.raises(DonorPoolError) as excinfo:
            self._climb([(10, 2), (20, 5), (30, 9)])
        message = str(excinfo.value)
        assert "30 eligible candidates" in message
        assert "9 admitted donors" in message

    def test_the_ladder_is_the_adr_ladder(self):
        assert [r.number for r in LADDER] == [1, 2, 3]
        assert LADDER[0].countries == ("ZWE", "ZMB", "MOZ")
        assert LADDER[2].countries == ("ZWE", "ZMB", "MOZ", "MWI", "TZA")

    def test_parameters_are_validated_before_any_screening(self):
        """An incomplete gate must fail before a count can be seen."""
        screened = []

        def screen(rung):
            screened.append(rung.number)
            raise AssertionError("must not be reached")

        with pytest.raises(MissingRunParameterError):
            climb_ladder(
                screen=screen,
                count_admitted=lambda rung, screening: 0,
                parameters=_parameters(projection=""),
            )
        assert screened == []


class TestManifest:
    def _manifest(self, **overrides):
        boundary = load_registry_boundary(KARIBA_BOUNDARY)
        payload = {
            "boundary": boundary,
            "treated_eligible_area_km2": 5000.0,
            "thresholds": Adr011Thresholds(),
            "parameters": _parameters(),
            "dataset_refs": EarthEngineUnitConstruction().dataset_refs(_parameters()),
            "rung_records": (),
            "rung_used": 1,
            "units": (_facts("gaul2015:40765"),),
            "exclusions": (),
            "engine_version": "0.3.0",
            "git_sha": "abc123",
        }
        payload.update(overrides)
        return build_manifest(**payload)

    @pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="boundary not obtained (#2)")
    def test_the_hash_ignores_only_the_timestamp(self):
        first, second = self._manifest(), self._manifest()
        assert first.content_hash == second.content_hash

    @pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="boundary not obtained (#2)")
    def test_the_hash_changes_with_a_threshold(self):
        changed = self._manifest(thresholds=Adr011Thresholds(min_eligible_area_km2=400.0))
        assert changed.content_hash != self._manifest().content_hash

    @pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="boundary not obtained (#2)")
    def test_it_pins_itself_as_a_dataset_ref(self):
        manifest = self._manifest()
        ref = manifest.as_dataset_ref()
        assert ref.version == manifest.content_hash
        assert not ref.is_synthetic

    @pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="boundary not obtained (#2)")
    def test_it_records_the_boundary_geometry_defect(self):
        notes = " ".join(self._manifest().geometry_notes)
        assert "overlapping part pair" in notes

    @pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="boundary not obtained (#2)")
    def test_it_writes_deterministic_json(self, tmp_path):
        manifest = self._manifest()
        path = manifest.write(tmp_path)
        written = path.read_text(encoding="utf-8")
        assert written == manifest.to_json()
        assert written == manifest.write(tmp_path).read_text(encoding="utf-8")
        assert json.loads(written)["adr"] == "ADR-011"


class TestGenerationRefusesWithoutRealData:
    """The property that matters most: no fabricated pool, ever."""

    @pytest.mark.skipif(not KARIBA_BOUNDARY.exists(), reason="boundary not obtained (#2)")
    def test_the_earth_engine_provider_refuses(self):
        with pytest.raises(DataUnavailableError, match="not implemented"):
            generate_unit_set(
                boundary_path=KARIBA_BOUNDARY,
                service=EarthEngineUnitConstruction(),
                parameters=_parameters(),
                count_admitted=lambda rung, screening: 0,
            )

    def test_the_refusal_names_the_blocking_issues(self):
        service = EarthEngineUnitConstruction()
        with pytest.raises(DataUnavailableError) as excinfo:
            service.districts_for_rung(
                LADDER[0],
                None,  # type: ignore[arg-type]
                parameters=_parameters(),
                thresholds=Adr011Thresholds(),
            )
        assert "#23" in str(excinfo.value)

    def test_dataset_refs_are_declarable_without_running(self):
        refs = EarthEngineUnitConstruction().dataset_refs(_parameters())
        assets = {r.asset for r in refs if r.asset}
        assert "FAO/GAUL/2015/level2" in assets
        assert any("treecover2000" in a for a in assets)
        assert not any(r.is_synthetic for r in refs)

    def test_an_unpinned_wdpa_release_is_visible_not_invented(self):
        refs = EarthEngineUnitConstruction().dataset_refs(_parameters(wdpa_release="x"))
        wdpa = next(r for r in refs if r.dataset_id == "wdpa")
        assert wdpa.version == "x"
