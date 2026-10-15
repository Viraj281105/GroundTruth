"""Observed series must be aligned to the analysis window before estimation.

Issue #53. The synthetic provider always returns exactly the requested periods,
so these tests wrap it in a port that returns the kinds of series a real
provider will: a skipped year, ragged donors, extra periods, non-finite values.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.ports import DataAccess, ObservationSpec
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import AnalysisRequest, AnalysisWindow
from groundtruth.contracts.result import AnalysisResult, EngineStatus, ErrorCode
from groundtruth.contracts.types import Indicator, TimeSeries
from groundtruth.engine import run_analysis
from groundtruth.engine.observation.alignment import (
    MisalignedSeriesError,
    align_panel,
    analysis_periods,
)
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access

Tamper = Callable[[TimeSeries, ObservationSpec], TimeSeries]


class _TamperedObservations:
    """Wraps an observation port and rewrites the series it returns."""

    def __init__(self, inner: object, tamper: Tamper) -> None:
        self._inner = inner
        self._tamper = tamper

    def series(self, spec: ObservationSpec) -> TimeSeries:
        return self._tamper(self._inner.series(spec), spec)  # type: ignore[attr-defined]

    def dataset(self, indicator: Indicator) -> DatasetRef:
        return self._inner.dataset(indicator)  # type: ignore[attr-defined,no-any-return]

    def provenance(self, spec: ObservationSpec) -> Provenance:
        return self._inner.provenance(spec)  # type: ignore[attr-defined,no-any-return]


def _rebuild(series: TimeSeries, periods: list[int], values: list[float]) -> TimeSeries:
    return series.model_copy(update={"periods": tuple(periods), "values": tuple(values)})


def _drop(series: TimeSeries, drop: set[int]) -> TimeSeries:
    kept = [(p, v) for p, v in zip(series.periods, series.values, strict=True) if p not in drop]
    return _rebuild(series, [p for p, _ in kept], [v for _, v in kept])


def _request() -> AnalysisRequest:
    return get_case("kariba-redd").to_request(seed=20260101)


def _run(request: AnalysisRequest, tamper: Tamper | None = None) -> AnalysisResult:
    access = synthetic_access(request, true_effect=0.06)
    if tamper is not None:
        access = DataAccess(
            observations=_TamperedObservations(access.observations, tamper),
            covariates=access.covariates,
            donors=access.donors,
        )
    return run_analysis(request, access)


def _refusal(result: AnalysisResult) -> None:
    assert result.status is EngineStatus.REFUSED
    assert result.error is not None
    assert result.error.code is ErrorCode.INSUFFICIENT_DATA
    assert result.error.stage == "alignment"
    assert result.bundle is None


class TestRunRefusesMisalignedSeries:
    def test_a_project_series_missing_an_interior_year_refuses(self):
        request = _request()
        missing = request.window.pre_start + 4

        def tamper(series: TimeSeries, spec: ObservationSpec) -> TimeSeries:
            if spec.unit.unit_id == request.project.unit_id:
                return _drop(series, {missing})
            return series

        result = _run(request, tamper)
        _refusal(result)
        assert result.error is not None
        units = result.error.detail["units"]
        assert units == [
            {
                "unit_id": request.project.unit_id,
                "missing_periods": [missing],
                "non_finite_periods": [],
            }
        ]
        assert request.project.unit_id in result.error.message

    def test_donors_of_differing_lengths_refuse_rather_than_raise(self):
        request = _request()
        first_donor: list[str] = []

        def tamper(series: TimeSeries, spec: ObservationSpec) -> TimeSeries:
            if spec.unit.unit_id == request.project.unit_id:
                return series
            if not first_donor:
                first_donor.append(spec.unit.unit_id)
                return series
            # Every donor but the first starts two years late.
            return _drop(series, {request.window.pre_start, request.window.pre_start + 1})

        result = _run(request, tamper)
        _refusal(result)
        assert result.error is not None
        units = result.error.detail["units"]
        assert units, "every offending donor is named"
        assert all(u["missing_periods"] == [2001, 2002] for u in units)
        assert result.error.detail["n_units_misaligned"] == len(units)

    def test_a_non_finite_value_in_the_window_refuses(self):
        request = _request()
        bad = request.window.post_start + 2

        def tamper(series: TimeSeries, spec: ObservationSpec) -> TimeSeries:
            if spec.unit.unit_id != request.project.unit_id:
                return series
            values = [
                math.nan if p == bad else v
                for p, v in zip(series.periods, series.values, strict=True)
            ]
            return _rebuild(series, list(series.periods), values)

        result = _run(request, tamper)
        _refusal(result)
        assert result.error is not None
        assert result.error.detail["units"][0]["non_finite_periods"] == [bad]

    def test_the_refusal_round_trips_through_json(self):
        request = _request()

        def tamper(series: TimeSeries, spec: ObservationSpec) -> TimeSeries:
            return _drop(series, {request.window.post_end})

        result = _run(request, tamper)
        restored = AnalysisResult.model_validate_json(result.model_dump_json())
        assert restored.error is not None and result.error is not None
        assert restored.error.detail == result.error.detail


class TestTreatmentBoundaryComesFromLabels:
    def test_extra_leading_periods_do_not_shift_the_treatment_boundary(self):
        """Positional indexing would treat 2008 as the first post period here."""
        request = _request()
        lead = [request.window.pre_start - k for k in (3, 2, 1)]

        def tamper(series: TimeSeries, spec: ObservationSpec) -> TimeSeries:
            # Wildly off-scale values: if any estimator saw them, the fit changes.
            return _rebuild(series, [*lead, *series.periods], [5.0, -5.0, 5.0, *series.values])

        clean, padded = _run(request), _run(request, tamper)
        assert padded.status is EngineStatus.COMPLETED
        assert clean.bundle is not None and padded.bundle is not None

        boundary = padded.bundle.require("fit.treatment_boundary_period")
        assert boundary.value == request.window.post_start
        assert boundary.qualifiers["dropped_periods"] == lead

        assert padded.bundle.require("effect.point_estimate").value == pytest.approx(
            clean.bundle.require("effect.point_estimate").value, abs=0.0
        )
        assert any("outside the analysis window" in w for w in padded.bundle.warnings)

    def test_the_split_lands_on_post_start_when_the_window_has_a_gap(self):
        window = AnalysisWindow(pre_start=2001, pre_end=2010, post_start=2012, post_end=2022)
        periods = tuple(range(2001, 2023))
        series = {
            uid: TimeSeries(
                unit_id=uid,
                indicator=Indicator.NDVI,
                periods=periods,
                values=tuple(float(p) for p in periods),
            )
            for uid in ("project", "d1", "d2")
        }
        panel = align_panel(window, series["project"], series, ("d1", "d2"))

        assert panel.n_pre == 10
        assert panel.periods[panel.n_pre] == 2012
        assert panel.treated[panel.n_pre] == 2012.0
        assert 2011 not in panel.periods
        assert panel.dropped_periods == (2011,)
        assert panel.donors.shape == (21, 2)

    def test_a_clean_run_records_its_period_coverage(self):
        request = _request()
        result = _run(request)
        assert result.status is EngineStatus.COMPLETED
        assert result.bundle is not None
        pre, post = analysis_periods(request.window)

        n_pre = result.bundle.require("fit.n_pre_periods")
        n_post = result.bundle.require("fit.n_post_periods")
        assert n_pre.value == len(pre)
        assert n_post.value == len(post)
        assert n_pre.qualifiers == {"first_period": pre[0], "last_period": pre[-1]}
        assert n_post.qualifiers == {"first_period": post[0], "last_period": post[-1]}
        assert n_pre.provenance.stage == "alignment"
        assert not any("outside the analysis window" in w for w in result.bundle.warnings)


class TestAlignPanel:
    def _series(self, uid: str, periods: tuple[int, ...]) -> TimeSeries:
        return TimeSeries(
            unit_id=uid,
            indicator=Indicator.NDVI,
            periods=periods,
            values=tuple(np.linspace(0.5, 0.6, len(periods))),
        )

    def test_every_offending_unit_is_reported_not_just_the_first(self):
        window = AnalysisWindow(pre_start=2001, pre_end=2005, post_start=2006, post_end=2008)
        full = tuple(range(2001, 2009))
        series = {
            "p": self._series("p", full),
            "a": self._series("a", full[1:]),
            "b": self._series("b", full),
            "c": self._series("c", full[:-1]),
        }
        with pytest.raises(MisalignedSeriesError) as caught:
            align_panel(window, series["p"], series, ("a", "b", "c"))
        assert [d.unit_id for d in caught.value.defects] == ["a", "c"]
        assert caught.value.defects[0].missing_periods == (2001,)
        assert caught.value.defects[1].missing_periods == (2008,)

    def test_donors_not_in_the_pool_are_not_validated(self):
        """Only series that reach an estimator are held to the window."""
        window = AnalysisWindow(pre_start=2001, pre_end=2005, post_start=2006, post_end=2008)
        full = tuple(range(2001, 2009))
        series = {
            "p": self._series("p", full),
            "a": self._series("a", full),
            "unused": self._series("unused", full[2:]),
        }
        panel = align_panel(window, series["p"], series, ("a",))
        assert panel.donor_ids == ("a",)


def test_run_analysis_never_stacks_raw_series():
    """Acceptance for #53: no column_stack on unvalidated input remains in run.py."""
    import groundtruth.engine.run as run_module

    tree = ast.parse(Path(run_module.__file__).read_text(encoding="utf-8"))
    raw_reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"as_array", "values"}
    ]
    assert raw_reads == [], "run.py must read series only through align_panel"
