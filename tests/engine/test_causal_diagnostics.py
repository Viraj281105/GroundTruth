"""Tests for causal inference and donor eligibility diagnostics."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.contracts.errors import EstimationError, InsufficientDataError
from groundtruth.engine.causal.did import ParallelTrendsDiagnostic, check_parallel_trends
from groundtruth.engine.causal.synthetic_control import (
    CollinearityDiagnostic,
    diagnose_donor_collinearity,
    fit_synthetic_control,
)
from groundtruth.engine.matching.donors import validate_donor_eligibility


def test_effective_donor_count_and_uniform_degeneracy_on_50_donor_collinear_pool() -> None:
    """A 50-donor collinear fixture collapses FISTA to uniform w_j = 0.02 weights."""
    n_periods = 14
    n_pre_periods = 8
    n_donors = 50

    base_path = np.linspace(0.55, 0.62, n_periods) + 0.01 * np.sin(np.arange(n_periods))
    donor_matrix = np.tile(base_path[:, None], (1, n_donors))
    treated_series = base_path.copy()
    treated_series[n_pre_periods:] += 0.04
    donor_ids = tuple(f"zw-donor-{i:02d}" for i in range(n_donors))

    fit = fit_synthetic_control(
        treated_series=treated_series,
        donor_matrix=donor_matrix,
        donor_ids=donor_ids,
        n_pre_periods=n_pre_periods,
    )

    assert np.allclose(fit.weights, 0.02, atol=1e-6)
    assert fit.effective_donor_count == pytest.approx(50.0, rel=1e-4)
    assert fit.is_uniform_degenerate is True
    assert fit.weights_are_identified is False


def test_sparse_synthetic_control_is_not_uniform_degenerate() -> None:
    """When one donor uniquely tracks the treated unit, weights concentrate and are not degenerate."""
    rng = np.random.default_rng(42)
    n_periods = 16
    n_pre = 10
    n_donors = 6

    donor_matrix = rng.normal(loc=0.5, scale=0.08, size=(n_periods, n_donors))
    treated = donor_matrix[:, 0].copy()
    treated[n_pre:] += 0.05
    donor_ids = tuple(f"donor-{i}" for i in range(n_donors))

    fit = fit_synthetic_control(
        treated_series=treated,
        donor_matrix=donor_matrix,
        donor_ids=donor_ids,
        n_pre_periods=n_pre,
    )

    assert fit.is_uniform_degenerate is False
    assert 1.0 <= fit.effective_donor_count < 2.0


def test_diagnose_donor_collinearity_rank_deficient_and_collinear() -> None:
    """Collinearity diagnostic flags rank deficiency and near-duplicate donor trajectories."""
    base = np.linspace(0.4, 0.7, 8)
    collinear_donors = np.column_stack(
        [
            base,
            base + 1e-9 * np.arange(8),
            base * 1.05 + 0.02,
            np.sin(np.arange(8, dtype=float)),
        ]
    )

    diag = diagnose_donor_collinearity(collinear_donors)
    assert isinstance(diag, CollinearityDiagnostic)
    assert diag.n_periods == 8
    assert diag.n_Periods == 8
    assert diag.n_donors == 4
    assert diag.max_pairwise_correlation > 0.999
    assert diag.is_highly_collinear is True

    # Under-identified (more donors than pre-treatment periods: 6 periods < 12 donors)
    rng = np.random.default_rng(123)
    wide_donors = rng.normal(size=(6, 12))
    wide_diag = diagnose_donor_collinearity(wide_donors)
    assert wide_diag.rank <= 6
    assert wide_diag.is_rank_deficient is True
    assert wide_diag.is_highly_collinear is True

    # Well-conditioned orthogonal donor matrix
    orthogonal = np.eye(8, 3)
    orthogonal[:, 0] = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    orthogonal[:, 1] = np.array([1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0])
    orthogonal[:, 2] = np.array([1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0])
    ortho_diag = diagnose_donor_collinearity(orthogonal)
    assert ortho_diag.rank == 3
    assert ortho_diag.is_rank_deficient is False
    assert ortho_diag.max_pairwise_correlation == pytest.approx(0.0, abs=1e-9)
    assert ortho_diag.is_highly_collinear is False


def test_validate_donor_eligibility_catches_sutva_and_provenance_violations() -> None:
    """SUTVA helper rejects self-inclusion, Kariba host districts, leakage belt, and missing geometry."""
    project_id = "verra-902"
    host_districts = frozenset({"zw-hurungwe", "zw-binga", "zw-mbire"})
    leakage_belt = frozenset({"zw-kariba-leakage-1", "zw-nyaminyami"})
    candidates = (
        "verra-902",
        "zw-hurungwe",
        "zw-binga",
        "zw-mbire",
        "zw-kariba-leakage-1",
        "zw-gokwe-north",
        "zw-hwange",
    )
    geometries = {
        "zw-gokwe-north": {
            "type": "Polygon",
            "coordinates": [[[28.0, -17.0], [28.5, -17.0], [28.5, -17.5], [28.0, -17.0]]],
        },
        "zw-hwange": None,
    }

    exclusions = validate_donor_eligibility(
        project_unit_id=project_id,
        candidate_ids=candidates,
        excluded_unit_ids=leakage_belt,
        host_unit_ids=host_districts,
        donor_geometries=geometries,
        require_spatial_provenance=True,
    )

    assert (
        exclusions["verra-902"] == "candidate is the treated project unit itself (SUTVA violation)"
    )
    for host_id in ("zw-hurungwe", "zw-binga", "zw-mbire"):
        assert (
            exclusions[host_id]
            == "candidate is a host district overlapping the project area (SUTVA violation)"
        )
    assert (
        exclusions["zw-kariba-leakage-1"]
        == "inside project leakage belt (potential spillover contamination)"
    )
    assert exclusions["zw-hwange"] == "missing donor spatial boundary provenance"
    assert "zw-gokwe-north" not in exclusions


def test_check_parallel_trends_detects_divergence_vs_parallel() -> None:
    """Parallel-trends diagnostic passes when pre-trends move together and fails under divergence."""
    t = np.arange(8, dtype=float)
    donors_pre = np.column_stack(
        [
            0.50 + 0.01 * t,
            0.54 + 0.01 * t,
            0.48 + 0.01 * t,
        ]
    )
    # Parallel pre-trend (constant level offset of +0.05, zero differential slope)
    treated_parallel = 0.55 + 0.01 * t
    parallel_res = check_parallel_trends(treated_parallel, donors_pre, max_slope_per_period=0.005)
    assert isinstance(parallel_res, ParallelTrendsDiagnostic)
    assert parallel_res.differential_pre_slope == pytest.approx(0.0, abs=1e-12)
    assert parallel_res.pre_gap_sd == pytest.approx(0.0, abs=1e-12)
    assert parallel_res.passes is True

    # Diverging pre-trend (+0.025 per period steeper than donors)
    treated_diverging = 0.55 + 0.035 * t
    diverging_res = check_parallel_trends(treated_diverging, donors_pre, max_slope_per_period=0.01)
    assert diverging_res.differential_pre_slope == pytest.approx(0.025, abs=1e-9)
    assert diverging_res.pre_gap_sd > 0.05
    assert diverging_res.passes is False

    # Weighted control path check
    weights = np.array([0.5, 0.3, 0.2])
    weighted_res = check_parallel_trends(
        treated_parallel, donors_pre, weights=weights, max_slope_Per_period=0.005
    )
    assert weighted_res.passes is True


def test_diagnostic_validation_errors() -> None:
    """Invalid array shapes raise EstimationError or InsufficientDataError."""
    with pytest.raises(EstimationError):
        diagnose_donor_collinearity(np.ones(5))

    with pytest.raises(InsufficientDataError):
        check_parallel_trends(np.array([0.5]), np.array([[0.5]]))


def test_invalid_donor_geometries_crs_and_insufficient_provenance_rejected() -> None:
    """Reject unclosed rings, self-intersecting bowties, out-of-range WGS84 coords, bad CRS, and incomplete provenance."""
    geometries = {
        "valid-donor": {
            "type": "Feature",
            "properties": {
                "source_dataset_id": "ZWE-ADM2-62879985",
                "adm_level": "ADM2",
                "official_name": "Gokwe South",
                "shape_id": "62879985B62286453442238",
                "crs": "OGC:CRS84",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[28.5, -18.5], [29.0, -18.5], [29.0, -18.0], [28.5, -18.0], [28.5, -18.5]]
                ],
            },
        },
        "unclosed-ring": {
            "type": "Polygon",
            "coordinates": [[[28.0, -18.0], [28.5, -18.0], [28.5, -17.5], [28.0, -17.5]]],
        },
        "bowtie-self-intersecting": {
            "type": "Polygon",
            "coordinates": [
                [[28.0, -18.0], [28.5, -17.5], [28.5, -18.0], [28.0, -17.5], [28.0, -18.0]]
            ],
        },
        "out-of-range-wgs84": {
            "type": "Polygon",
            "coordinates": [
                [[295.0, -18.0], [296.0, -18.0], [296.0, -17.5], [295.0, -17.5], [295.0, -18.0]]
            ],
        },
        "wrong-crs": {
            "type": "Feature",
            "properties": {
                "source_dataset_id": "ZWE-ADM2-62879985",
                "adm_level": "ADM2",
                "official_name": "ProjectedUnit",
                "shape_id": "ID-1",
                "crs": "EPSG:3857",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[28.5, -18.5], [29.0, -18.5], [29.0, -18.0], [28.5, -18.0], [28.5, -18.5]]
                ],
            },
        },
        "incomplete-provenance": {
            "type": "Feature",
            "properties": {
                "source_dataset_id": "ZWE-ADM2-62879985",
                # missing adm_level, official_name, shape_id
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[29.5, -18.5], [30.0, -18.5], [30.0, -18.0], [29.5, -18.0], [29.5, -18.5]]
                ],
            },
        },
        "missing-boundary": None,
    }

    exclusions = validate_donor_eligibility(
        project_unit_id="kariba-redd",
        candidate_ids=tuple(geometries.keys()),
        donor_geometries=geometries,
        require_spatial_provenance=True,
    )

    assert "valid-donor" not in exclusions
    assert "unclosed polygon ring" in exclusions["unclosed-ring"]
    assert "self-intersecting" in exclusions["bowtie-self-intersecting"]
    assert "out of WGS84 range" in exclusions["out-of-range-wgs84"]
    assert "invalid donor CRS" in exclusions["wrong-crs"]
    assert "insufficient donor boundary provenance" in exclusions["incomplete-provenance"]
    assert exclusions["missing-boundary"] == "missing donor spatial boundary provenance"


def test_overlapping_and_duplicate_donor_boundaries_rejected() -> None:
    """Reject candidate donors whose polygons substantially overlap or duplicate another candidate."""
    poly_a = {
        "type": "Polygon",
        "coordinates": [
            [[29.0, -19.0], [29.5, -19.0], [29.5, -18.5], [29.0, -18.5], [29.0, -19.0]]
        ],
    }
    # Overlaps >50% of poly_a (~1,500 km2)
    poly_b_overlapping = {
        "type": "Polygon",
        "coordinates": [
            [[29.2, -19.0], [29.7, -19.0], [29.7, -18.5], [29.2, -18.5], [29.2, -19.0]]
        ],
    }
    poly_c_disjoint = {
        "type": "Polygon",
        "coordinates": [
            [[31.0, -19.0], [31.5, -19.0], [31.5, -18.5], [31.0, -18.5], [31.0, -19.0]]
        ],
    }

    exclusions = validate_donor_eligibility(
        project_unit_id="kariba-redd",
        candidate_ids=("donor-a", "donor-b-overlap", "donor-c-disjoint"),
        donor_geometries={
            "donor-a": poly_a,
            "donor-b-overlap": poly_b_overlapping,
            "donor-c-disjoint": poly_c_disjoint,
        },
        require_spatial_provenance=True,
        max_donor_overlap_km2=1.0,
    )

    assert "donor-a" not in exclusions
    assert "donor-c-disjoint" not in exclusions
    assert "donor-b-overlap" in exclusions
    assert "overlapping donor geometry with 'donor-a'" in exclusions["donor-b-overlap"]


def test_host_district_and_configurable_spatial_buffer_exclusions() -> None:
    """Verify geometric detection of host districts, boundary overlaps, and configurable buffers."""
    project_geom = {
        "type": "Polygon",
        "coordinates": [
            [[28.0, -17.0], [29.0, -17.0], [29.0, -16.0], [28.0, -16.0], [28.0, -17.0]]
        ],
    }
    donor_geoms = {
        # Overlaps project by ~5,500 km2 (>= 100 km2 host threshold)
        "host-district": {
            "type": "Polygon",
            "coordinates": [
                [[28.0, -17.0], [28.5, -17.0], [28.5, -16.0], [28.0, -16.0], [28.0, -17.0]]
            ],
        },
        # Overlaps project by a small ~24 km2 sliver (< 100 km2 host threshold, > 0.001 km2)
        "sliver-overlap-district": {
            "type": "Polygon",
            "coordinates": [
                [
                    [28.98, -16.95],
                    [29.30, -16.95],
                    [29.30, -16.85],
                    [28.98, -16.85],
                    [28.98, -16.95],
                ]
            ],
        },
        # ~5.5 km east of project boundary (inside 10 km buffer, outside 2 km buffer)
        "near-5km-district": {
            "type": "Polygon",
            "coordinates": [
                [
                    [29.05, -16.65],
                    [29.35, -16.65],
                    [29.35, -16.45],
                    [29.05, -16.45],
                    [29.05, -16.65],
                ]
            ],
        },
        # ~16 km east of project boundary (outside 10 km buffer, inside 25 km buffer)
        "mid-16km-district": {
            "type": "Polygon",
            "coordinates": [
                [
                    [29.15, -16.30],
                    [29.45, -16.30],
                    [29.45, -16.10],
                    [29.15, -16.10],
                    [29.15, -16.30],
                ]
            ],
        },
        # >100 km away
        "far-district": {
            "type": "Polygon",
            "coordinates": [
                [[30.5, -18.5], [31.0, -18.5], [31.0, -18.0], [30.5, -18.0], [30.5, -18.5]]
            ],
        },
    }

    exclusions_10km = validate_donor_eligibility(
        project_unit_id="kariba-redd",
        candidate_ids=tuple(donor_geoms.keys()),
        donor_geometries=donor_geoms,
        project_geometry=project_geom,
        spatial_buffer_km=10.0,
        require_spatial_provenance=True,
    )
    assert "host district overlapping the project area" in exclusions_10km["host-district"]
    assert "overlaps project area" in exclusions_10km["sliver-overlap-district"]
    assert "inside 10 km spatial exclusion buffer" in exclusions_10km["near-5km-district"]
    assert "mid-16km-district" not in exclusions_10km
    assert "far-district" not in exclusions_10km

    # Tightening buffer to 25 km excludes mid-16km-district while keeping far-district
    exclusions_25km = validate_donor_eligibility(
        project_unit_id="kariba-redd",
        candidate_ids=tuple(donor_geoms.keys()),
        donor_geometries=donor_geoms,
        project_geometry=project_geom,
        spatial_buffer_km=25.0,
        require_spatial_provenance=True,
    )
    assert "inside 25 km spatial exclusion buffer" in exclusions_25km["mid-16km-district"]
    assert "far-district" not in exclusions_25km


def test_insufficient_eligible_controls_raises_donor_pool_error() -> None:
    """When spatial/provenance exclusions leave fewer than min_donors, match_donors refuses."""
    from groundtruth.contracts.errors import DonorPoolError
    from groundtruth.engine.matching.donors import MatchingConfig, match_donors

    covs = {
        "rainfall_mm": 720.0,
        "elevation_m": 715.0,
        "slope_deg": 7.8,
        "road_distance_km": 18.5,
        "population_density": 22.0,
    }
    candidate_covs = {f"d-{i}": dict(covs) for i in range(8)}
    # Only 3 candidates have valid geometry; 5 have None
    geoms = {
        f"d-{i}": (
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [30.0 + i, -19.0],
                        [30.4 + i, -19.0],
                        [30.4 + i, -18.6],
                        [30.0 + i, -18.6],
                        [30.0 + i, -19.0],
                    ]
                ],
            }
            if i < 3
            else None
        )
        for i in range(8)
    }

    with pytest.raises(DonorPoolError, match="only 3 admissible donors"):
        match_donors(
            "kariba-redd",
            covs,
            candidate_covs,
            MatchingConfig(
                min_donors=5,
                donor_geometries=geoms,
                require_spatial_provenance=True,
            ),
        )


def test_kariba_authoritative_donor_boundaries_and_causal_reassessment() -> None:
    """Verify the 51 Kariba candidate districts against authoritative geoBoundaries ADM2 polygons and reassess SCM."""
    from groundtruth.contracts.ports import ObservationSpec
    from groundtruth.contracts.types import VerdictLabel
    from groundtruth.engine.assembler import AssemblyInputs, decide_verdict
    from groundtruth.engine.matching.donors import (
        MatchingConfig,
        assess_donor_spatial_eligibility,
        match_donors,
    )
    from groundtruth.engine.observation.alignment import align_panel, pre_period_coverage
    from groundtruth.engine.uncertainty.placebo import in_space_placebo
    from groundtruth.engine.uncertainty.robustness import leave_one_out
    from groundtruth.platform.cases.registry import get_case
    from groundtruth.platform.config import REPO_ROOT
    from groundtruth.platform.datasets.access import synthetic_fixture_access
    from groundtruth.platform.units import load_donor_boundaries, load_registry_boundary

    kariba_boundary = load_registry_boundary(
        REPO_ROOT / "cases" / "boundaries" / "kariba-redd.geojson"
    )
    donor_collection = load_donor_boundaries(
        REPO_ROOT / "cases" / "boundaries" / "kariba-donors.geojson"
    )

    assert len(donor_collection.records) == 50
    fmap = donor_collection.feature_map()
    assert len(fmap) == 51
    assert fmap["zw-uree"] is None

    all_candidate_ids = tuple(
        c["unit_id"] for c in donor_collection.provenance_manifest["candidates"]
    )
    assert len(all_candidate_ids) == 51

    assessment = assess_donor_spatial_eligibility(
        project_unit_id="kariba-redd",
        candidate_ids=all_candidate_ids,
        excluded_unit_ids=frozenset({"zm-siavonga", "zm-chirundu"}),
        host_unit_ids=frozenset({"zw-hurungwe", "zw-binga", "zw-mbire", "zw-nyaminyami"}),
        donor_geometries=fmap,
        require_spatial_provenance=True,
        project_geometry=kariba_boundary.geometry,
        spatial_buffer_km=10.0,
    )

    # Verify exact exclusion categories across all 51 candidate districts
    assert set(assessment.host_unit_ids) == {
        "zw-hurungwe",
        "zw-binga",
        "zw-mbire",
        "zw-nyaminyami",
    }
    assert set(assessment.unverified_unit_ids) == {"zw-uree"}
    assert set(assessment.overlapping_donor_unit_ids) == {"zw-centenary"}
    assert set(assessment.boundary_overlapping_unit_ids) == {
        "zw-gokwe-north",
        "zw-makonde",
        "zw-muzarabani",
        "zw-centenary",
        "zw-guruve",
    }
    assert set(assessment.buffer_excluded_unit_ids) == {
        "zm-luangwa",
        "zm-gwembe",
        "zm-siavonga",
        "zm-chirundu",
    }
    assert len(assessment.exclusions) == 14
    assert len(assessment.eligible_unit_ids) == 37
    # Host-adjacent districts outside the 10 km project buffer are recorded, not arbitrarily excluded
    assert set(assessment.host_adjacent_admitted_unit_ids) == {
        "zw-gokwe-south",
        "zw-hwange",
        "zw-lupane",
        "zm-sinazongwe",
        "zm-kafue",
    }

    # Re-run donor matching and causal diagnostics on the 37 eligible donors
    case = get_case("kariba-redd")
    request = case.to_request(data_mode="simulated")
    access = synthetic_fixture_access(request)
    cands = access.donors.candidates(request)
    assert len(cands) == 50

    proj_ts = access.observations.series(
        ObservationSpec(
            unit=request.project,
            indicator=request.indicator,
            start_period=request.window.pre_start,
            end_period=request.window.post_end,
        )
    )
    donor_series = {
        u.unit_id: access.observations.series(
            ObservationSpec(
                unit=u,
                indicator=request.indicator,
                start_period=request.window.pre_start,
                end_period=request.window.post_end,
            )
        )
        for u in cands
    }
    cand_covs = {
        u.unit_id: access.covariates.covariates(u, request.donors.covariates) for u in cands
    }
    proj_covs = access.covariates.covariates(request.project, request.donors.covariates)

    pool = match_donors(
        request.case_id,
        proj_covs,
        cand_covs,
        MatchingConfig(
            covariates=request.donors.covariates,
            max_donors=request.donors.max_donors,
            min_donors=request.donors.min_donors,
            caliper_sd=request.donors.caliper_sd,
            excluded_unit_ids=frozenset(request.donors.excluded_unit_ids),
            min_pre_observations=request.donors.min_pre_observations,
            donor_geometries=fmap,
            project_geometry=kariba_boundary.geometry,
            spatial_buffer_km=10.0,
            require_spatial_provenance=True,
        ),
        candidate_pre_observations=pre_period_coverage(request.window, donor_series),
    )

    assert len(pool.admitted) == 37
    assert (
        len(pool.excluded) == 13
    )  # 13 of the 50 in fixture (zw-nyaminyami is the 14th, not in fixture)
    assert set(pool.unit_ids) == set(assessment.eligible_unit_ids)

    panel = align_panel(request.window, proj_ts, donor_series, pool.unit_ids)
    col_diag = diagnose_donor_collinearity(panel.donors[: panel.n_pre])
    assert col_diag.n_periods == 10
    assert col_diag.n_donors == 37
    assert col_diag.rank == 10
    assert col_diag.is_rank_deficient is True
    assert col_diag.max_pairwise_correlation > 0.99
    assert col_diag.is_highly_collinear is True

    fit = fit_synthetic_control(panel.treated, panel.donors, pool.unit_ids, panel.n_pre)
    assert fit.weights_are_identified is False
    assert fit.is_uniform_degenerate is True
    assert fit.effective_donor_count == pytest.approx(36.989, rel=1e-3)

    # Even if a divergence ratio is supplied, decide_verdict returns INCONCLUSIVE due to uniform-degenerate weights
    placebo = in_space_placebo(
        np.column_stack([panel.treated, panel.donors]),
        (request.case_id, *pool.unit_ids),
        0,
        panel.n_pre,
    )
    loo = leave_one_out(
        panel.treated,
        panel.donors,
        pool.unit_ids,
        panel.n_pre,
        baseline_effect=fit.average_effect,
        only_contributing=fit.contributing_donors(),
    )
    inputs = AssemblyInputs(
        request=request,
        indicator_unit="ndvi",
        donor_pool=pool,
        fit=fit,
        panel=panel,
        placebo=placebo,
        leave_one_out=loo,
    )
    verdict = decide_verdict(inputs, divergence_ratio=0.40)
    assert verdict.label is VerdictLabel.INCONCLUSIVE
    assert "uniform 1/J weighting" in verdict.rationale
