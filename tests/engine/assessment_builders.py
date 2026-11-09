"""Builders for the assessment-engine tests (imported by the three assessment test files).

All values are small illustrative fixtures that exercise the rules. None of them
describes a real project (R6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from groundtruth.engine.assessment.types import (
    AssessmentInputs,
    ClimateYear,
    ReadinessSummary,
    SeriesPoint,
    SpreadPoint,
)


def make_points(
    indicator: str,
    start_year: int,
    values: Sequence[float],
    *,
    n_valid_pixels: int = 1000,
) -> list[SeriesPoint]:
    return [
        SeriesPoint(
            year=start_year + i,
            value=float(v),
            n_valid_pixels=n_valid_pixels,
            evidence_refs=(f"series:{indicator}:{start_year + i}",),
        )
        for i, v in enumerate(values)
    ]


def make_climate(start_year: int, spis: Sequence[float | None]) -> list[ClimateYear]:
    return [
        ClimateYear(
            year=start_year + i,
            rainfall_mm=700.0 + 10.0 * i,
            spi12=spi,
            temperature_c=24.0,
            evidence_refs=(f"climate:{start_year + i}",),
        )
        for i, spi in enumerate(spis)
    ]


def make_spread(
    start_year: int, n: int, *, std: float = 0.05, n_valid_pixels: int = 100
) -> list[SpreadPoint]:
    return [
        SpreadPoint(
            year=start_year + i,
            p10=0.2,
            p90=0.5,
            std=std,
            n_valid_pixels=n_valid_pixels,
            evidence_refs=(f"spread:{start_year + i}",),
        )
        for i in range(n)
    ]


def readiness(**over: Any) -> ReadinessSummary:
    base: dict[str, Any] = {
        "attribution_ready": False,
        "pre_treatment_observed": False,
        "donor_panel_available": False,
        "boundary_verified": True,
        "climate_missing_months": (),
    }
    base.update(over)
    return ReadinessSummary(**base)


def full_coverage(start_year: int, n: int, pct: float = 100.0) -> dict[int, float]:
    return {start_year + i: pct for i in range(n)}


def sensors(start_year: int, n: int, name: str = "Sentinel-2") -> dict[int, list[str]]:
    return {start_year + i: [name] for i in range(n)}


def build_inputs(**over: Any) -> AssessmentInputs:
    """Kariba-shaped by default: 3 annual points, 3 climate years, no reference."""
    base: dict[str, Any] = {
        "series": {"NDVI": make_points("NDVI", 2021, [0.304, 0.296, 0.301])},
        "zonal_spread": None,
        "climate": make_climate(2021, [-1.3, 0.2, 0.4]),
        "reference_series": None,
        "readiness": readiness(climate_missing_months=("2023-11", "2023-12")),
        "coverage_pct": {2021: 62.0, 2022: 71.0, 2023: 68.0},
        "sensors": sensors(2021, 3),
        "field_evidence": False,
        "treatment_start_year": 2012,
        "data_mode": "observed",
    }
    base.update(over)
    return AssessmentInputs(**base)


def reference_panel(
    indicator: str,
    start_year: int,
    n_periods: int,
    n_donors: int = 4,
) -> Mapping[str, Mapping[str, list[SeriesPoint]]]:
    return {
        indicator: {
            f"donor-{k}": make_points(
                f"{indicator}:donor-{k}",
                start_year,
                [0.40 + 0.002 * k + 0.001 * (i % 2) for i in range(n_periods)],
            )
            for k in range(n_donors)
        }
    }


def quiet_inputs() -> AssessmentInputs:
    """Evidence-rich, no trigger fires: stable record, complete coverage, donors, run done."""
    n = 10
    values = [0.50 + 0.0005 * (i % 2) for i in range(n)]
    return build_inputs(
        series={"NDVI": make_points("NDVI", 2012, values)},
        climate=make_climate(2012, [0.1 * ((-1) ** i) for i in range(n)]),
        reference_series=reference_panel("NDVI", 2012, n),
        readiness=readiness(
            attribution_ready=True,
            pre_treatment_observed=True,
            donor_panel_available=True,
            causal_run_completed=True,
            causal_verdict="Not supported",
            causal_limitation="none",
            causal_methodology="synthetic control with placebo tests",
        ),
        coverage_pct=full_coverage(2012, n),
        sensors=sensors(2012, n),
        treatment_start_year=2012,
    )
