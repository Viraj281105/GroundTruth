"""No request field is accepted, hashed and then silently ignored (issue #54)."""

from __future__ import annotations

from typing import Any

import pytest

from groundtruth.contracts.identifiers import ModelRef
from groundtruth.contracts.request import AnalysisRequest, EstimationSpec, RobustnessSpec
from groundtruth.contracts.result import AnalysisResult, EngineStatus, ErrorCode
from groundtruth.contracts.types import VerdictLabel
from groundtruth.engine import run_analysis
from groundtruth.engine.run import describe_engine
from groundtruth.engine.uncertainty.placebo import PlaceboResult
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access

COMMENSURABILITY = "commensurable units"
"""Rationale reached only when every robustness gate passes (no biomass layer yet)."""


def _request(**changes: dict[str, Any]) -> AnalysisRequest:
    request = get_case("kariba-redd").to_request(seed=20260101)
    update: dict[str, Any] = {}
    if "estimation" in changes:
        update["estimation"] = request.estimation.model_copy(update=changes["estimation"])
    if "robustness" in changes:
        update["robustness"] = request.robustness.model_copy(update=changes["robustness"])
    return request.model_copy(update=update)


def _run(request: AnalysisRequest) -> AnalysisResult:
    return run_analysis(request, synthetic_access(request, true_effect=0.06))


def _rationale(result: AnalysisResult) -> str:
    assert result.bundle is not None and result.bundle.verdict is not None
    return result.bundle.verdict.rationale


def test_the_baseline_passes_every_gate():
    """The other tests flip this baseline, so it must start clean."""
    assert COMMENSURABILITY in _rationale(_run(_request()))


class TestInTimePlacebo:
    def test_requesting_it_produces_in_time_evidence(self):
        result = _run(_request(robustness={"in_time_placebo": True}))
        assert result.bundle is not None
        fake = result.bundle.require("placebo.in_time_fake_effect")
        assert fake.unit == "ndvi"
        assert fake.qualifiers["fake_treatment_period"] == 2006
        assert result.bundle.require("placebo.in_time_passes").value is True
        assert COMMENSURABILITY in _rationale(result)

    def test_not_requesting_it_produces_none(self):
        result = _run(_request(robustness={"in_time_placebo": False}))
        assert result.bundle is not None
        assert result.bundle.get("placebo.in_time_fake_effect") is None
        assert result.bundle.get("placebo.in_time_passes") is None

    def test_a_spurious_pre_period_effect_fails_the_gate(self):
        from groundtruth.engine.uncertainty.placebo import InTimePlaceboResult

        assert not InTimePlaceboResult(
            fake_treatment_index=5, fake_effect=0.04, true_effect=0.06
        ).passes


class TestFitThreshold:
    def test_a_tightened_max_pre_rmse_ratio_flips_the_verdict(self):
        baseline = _run(_request())
        assert baseline.bundle is not None
        relative = baseline.bundle.require("fit.relative_pre_rmspe").value
        assert isinstance(relative, float)

        tightened = _run(_request(estimation={"max_pre_rmse_ratio": relative * 0.9}))
        assert tightened.bundle is not None and tightened.bundle.verdict is not None
        assert tightened.bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "pre-treatment fit is poor" in tightened.bundle.verdict.rationale
        gate = tightened.bundle.require("fit.relative_pre_rmspe").qualifiers["gate_threshold"]
        assert gate == pytest.approx(relative * 0.9)


class TestConfidenceLevel:
    def test_it_sets_the_placebo_significance_level(self):
        result = _run(_request(robustness={"confidence_level": 0.90}))
        assert result.bundle is not None
        item = result.bundle.require("placebo.p_value")
        assert item.qualifiers["significance_level"] == pytest.approx(0.10)

    def test_a_stricter_level_than_the_placebos_can_reach_is_inconclusive(self):
        result = _run(_request(robustness={"confidence_level": 0.99}))
        assert result.bundle is not None
        floor = result.bundle.require("placebo.p_value").qualifiers["p_value_floor"]
        assert floor > 0.01
        assert "smallest attainable p-value" in _rationale(result)

    @pytest.mark.parametrize(("level", "extreme"), [(0.10, True), (0.05, False)])
    def test_the_threshold_moves_with_the_level(self, level, extreme):
        # Rank 2 of 23: p = 2/23 = 0.087, extreme at 10% but not at 5%.
        placebo = PlaceboResult(
            observed_statistic=3.0,
            placebo_statistics=tuple([1.0] * 21 + [4.0]),
            p_value=2 / 23,
            n_placebos=22,
            n_failed=0,
            significance_level=level,
        )
        assert placebo.can_reject
        assert placebo.is_extreme is extreme


class TestUnimplementedOptionsAreReported:
    def test_an_unknown_primary_estimator_is_refused(self):
        result = _run(_request(estimation={"primary": ModelRef(model_id="matched-controls")}))
        assert result.status is EngineStatus.ERROR
        assert result.error is not None
        assert result.error.code is ErrorCode.NOT_IMPLEMENTED

    def test_an_unknown_cross_check_is_warned_about(self):
        result = _run(
            _request(
                estimation={
                    "cross_checks": (
                        ModelRef(model_id="difference-in-differences"),
                        ModelRef(model_id="event-study"),
                    )
                }
            )
        )
        assert result.bundle is not None
        assert any("'event-study'" in w and "not implemented" in w for w in result.bundle.warnings)
        assert result.bundle.get("crosscheck.did_estimate") is not None

    def test_a_requested_specification_curve_is_warned_about(self):
        result = _run(_request(robustness={"specification_curve": True}))
        assert result.bundle is not None
        assert any("specification curve" in w.lower() for w in result.bundle.warnings)


# Every RobustnessSpec and EstimationSpec field, classified. A new field fails
# this test until someone decides whether the engine consumes it.
CONSUMED = {
    "EstimationSpec": {
        "primary": "refused with NOT_IMPLEMENTED unless synthetic-control",
        "cross_checks": "difference-in-differences run; unknown ids warned about",
        "ridge": "passed to every synthetic-control fit",
        "min_pre_periods": "passed to every synthetic-control fit",
        "max_pre_rmse_ratio": "the SD-scaled pre-fit gate threshold",
    },
    "RobustnessSpec": {
        "in_space_placebo": "runs the in-space placebo",
        "in_time_placebo": "runs the in-time placebo",
        "leave_one_out": "runs leave-one-out",
        "confidence_level": "sets the placebo significance level",
        "max_placebo_pre_rmspe_multiple": "the placebo poor-fit screen",
    },
}
NOT_YET_IMPLEMENTED = {
    "RobustnessSpec": {"specification_curve": "#28; warned about when requested"},
}


@pytest.mark.parametrize("spec", [EstimationSpec, RobustnessSpec])
def test_every_field_is_consumed_or_explicitly_unimplemented(spec):
    name = spec.__name__
    classified = set(CONSUMED.get(name, {})) | set(NOT_YET_IMPLEMENTED.get(name, {}))
    assert set(spec.model_fields) == classified


def test_describe_engine_matches_what_the_pipeline_runs():
    implemented = describe_engine()["implemented"]
    assert implemented["in_time_placebo"] is True
    assert implemented["in_space_placebo"] is True
    assert implemented["specification_curve"] is False

    result = _run(_request(robustness={"in_time_placebo": True, "specification_curve": True}))
    assert result.bundle is not None
    ids = {item.id for item in result.bundle.items}
    assert "placebo.in_time_passes" in ids
    assert "placebo.p_value" in ids
    assert "robustness.sign_stable" in ids
    assert not any(i.startswith("speccurve.") for i in ids)
