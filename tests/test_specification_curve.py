"""The specification curve runs inside an analysis (issue #28)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from groundtruth.contracts.types import VerdictLabel
from groundtruth.engine import run_analysis
from groundtruth.engine.assembler import assemble_evidence
from groundtruth.engine.uncertainty.robustness import SpecificationCurve
from groundtruth.engine.uncertainty.specification import (
    CENTRE_ID,
    build_specifications,
    specification_curve,
)
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access


def _run(*, specification_curve: bool = True, true_effect: float = 0.06):
    request = get_case("kariba-redd").to_request(seed=20260101)
    request = request.model_copy(
        update={
            "robustness": request.robustness.model_copy(
                update={"specification_curve": specification_curve}
            )
        }
    )
    return run_analysis(request, synthetic_access(request, true_effect=true_effect))


class TestBuildSpecifications:
    def test_one_at_a_time_around_the_centre(self):
        specs = build_specifications(
            ridge=0.0, n_pre=10, n_donors=40, min_pre_periods=5, min_donors=10
        )
        ids = [s.spec_id for s in specs]
        assert ids[0] == CENTRE_ID
        assert ids == [
            "centre",
            "ridge-0-01",
            "ridge-0-1",
            "pre-period-8",
            "treatment-1-earlier",
            "donor-cap-20",
            "donor-cap-35",
        ]
        # Every non-centre specification changes exactly one choice.
        for s in specs[1:]:
            changed = [
                s.ridge != 0.0,
                s.leading_periods_dropped != 0,
                s.treatment_shift != 0,
                s.donor_cap is not None,
            ]
            assert sum(changed) == 1, s

    def test_only_variations_the_panel_supports_are_built(self):
        specs = build_specifications(
            ridge=0.01, n_pre=6, n_donors=15, min_pre_periods=5, min_donors=10
        )
        ids = {s.spec_id for s in specs}
        assert "ridge-0-01" not in ids  # equals the centre
        assert {"ridge-0", "ridge-0-1"} <= ids
        assert not any(i.startswith("pre-period-") for i in ids)
        assert not any(i.startswith("donor-cap-") for i in ids)
        assert "treatment-1-earlier" in ids


class TestCurveOnAPanel:
    def test_a_real_effect_agrees_on_sign(self, factor_panel):
        outcomes, unit_ids, n_pre, true_effect = factor_panel
        curve = specification_curve(outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre)
        assert curve.centre_id == CENTRE_ID
        assert curve.sign_agreement == 1.0
        assert curve.sign_flips == ()
        assert curve.median == pytest.approx(true_effect, abs=0.02)

    def test_a_null_effect_produces_flips_that_are_reported(self, null_panel):
        outcomes, unit_ids, n_pre = null_panel
        curve = specification_curve(outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre)
        assert set(curve.estimates) | set(curve.failed) == set(curve.dimensions)
        # Under the null, some specification lands on the other side of zero.
        assert curve.sign_flips
        assert all(s in curve.estimates for s in curve.sign_flips)

    def test_a_specification_that_cannot_be_fitted_is_kept_as_failed(
        self, factor_panel, monkeypatch
    ):
        from groundtruth.contracts.errors import EstimationError
        from groundtruth.engine.uncertainty import specification as module

        real_fit = module.fit_synthetic_control

        def failing_for_heavy_ridge(*args, ridge=0.0, **kwargs):  # type: ignore[no-untyped-def]
            if ridge == 0.1:
                raise EstimationError("simulated solver failure")
            return real_fit(*args, ridge=ridge, **kwargs)

        monkeypatch.setattr(module, "fit_synthetic_control", failing_for_heavy_ridge)
        outcomes, unit_ids, n_pre, _ = factor_panel
        curve = specification_curve(outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre)
        assert curve.failed == {"ridge-0-1": "simulated solver failure"}
        assert "ridge-0-1" not in curve.estimates
        assert "ridge-0-1" in curve.dimensions

    def test_a_short_pre_period_skips_the_variations_it_cannot_support(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        curve = specification_curve(
            outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre, min_pre_periods=n_pre
        )
        assert "treatment-1-earlier" not in curve.dimensions
        assert not any(s.startswith("pre-period-") for s in curve.dimensions)


class TestCurveInARun:
    def test_the_curve_is_emitted_as_evidence(self):
        result = _run()
        assert result.bundle is not None
        median = result.bundle.require("robustness.spec_curve.median")
        assert median.unit == "ndvi"
        assert median.confidence is not None
        assert median.confidence.kind == "sensitivity-envelope"
        assert median.qualifiers["range_is"].startswith("sensitivity-envelope")
        agreement = result.bundle.require("robustness.spec_curve.sign_agreement")
        assert agreement.value == 1.0

        estimates = [
            i for i in result.bundle.items if i.id.startswith("robustness.spec_curve.estimate.")
        ]
        centres = [i for i in estimates if i.qualifiers["is_centre"]]
        assert len(centres) == 1
        # The centre is the run's own estimate, but it is one point among many.
        assert centres[0].value == pytest.approx(
            result.bundle.require("effect.point_estimate").value
        )
        values = [i.value for i in estimates]
        assert values == sorted(values)
        assert median.value == pytest.approx(float(np.median(values)))

    def test_without_the_flag_there_is_no_curve(self):
        result = _run(specification_curve=False)
        assert result.bundle is not None
        assert not any(i.id.startswith("robustness.spec_curve.") for i in result.bundle.items)

    def test_the_provenance_lists_what_was_not_varied(self):
        result = _run()
        assert result.bundle is not None
        prov = result.bundle.require("robustness.spec_curve.median").provenance
        assert prov.parameters["dimensions_not_varied_in_run"] == [
            "indicator",
            "caliper",
            "covariate_weighting",
        ]
        assert "centre" not in prov.parameters["dimensions_varied"]


class TestSignFlipsGateTheVerdict:
    def test_a_flipping_curve_is_inconclusive_and_named(self, factor_panel, assembly_inputs):
        outcomes, unit_ids, n_pre, _ = factor_panel
        inputs = assembly_inputs(outcomes, unit_ids, n_pre)
        flipping = SpecificationCurve(
            {"centre": 0.07, "ridge-0-1": 0.06, "pre-period-8": -0.01},
            centre_id="centre",
            dimensions={
                "centre": "centre",
                "ridge-0-1": "ridge",
                "pre-period-8": "pre_period_length",
            },
        )
        bundle = assemble_evidence(
            replace(inputs, specification_curve=flipping), divergence_ratio=1.0
        )
        assert bundle.verdict is not None
        assert bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "pre-period-8" in bundle.verdict.rationale
        flipped = bundle.require("robustness.spec_curve.estimate.pre-period-8")
        assert flipped.qualifiers["flips_sign"] is True
        assert any("not stable across specifications" in w for w in bundle.warnings)
