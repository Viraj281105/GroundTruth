"""The fit gate and the convex-hull containment diagnostic (issue #56)."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.contracts.types import DonorMatch, VerdictLabel
from groundtruth.engine.assembler import (
    MAX_RELATIVE_PRE_FIT,
    AssemblyInputs,
    assemble_evidence,
    decide_verdict,
)
from groundtruth.engine.causal.synthetic_control import (
    convex_hull_diagnostic,
    fit_synthetic_control,
)
from groundtruth.engine.matching.donors import DonorPool
from groundtruth.engine.uncertainty.placebo import in_space_placebo
from groundtruth.engine.uncertainty.robustness import leave_one_out
from groundtruth.platform.cases.registry import get_case


def _inputs(outcomes: np.ndarray, unit_ids: tuple[str, ...], n_pre: int) -> AssemblyInputs:
    """Run the estimation stages on a panel whose column 0 is treated."""
    treated, donors = outcomes[:, 0], outcomes[:, 1:]
    donor_ids = unit_ids[1:]
    fit = fit_synthetic_control(treated, donors, donor_ids, n_pre)
    pool = DonorPool(
        project_unit_id=unit_ids[0],
        matches=tuple(DonorMatch(unit_id=uid, distance=0.1) for uid in donor_ids),
        covariates=("x",),
        standardised_mean_differences={"x": 0.0},
    )
    return AssemblyInputs(
        request=get_case("kariba-redd").to_request(seed=20260101),
        indicator_unit="ndvi",
        donor_pool=pool,
        fit=fit,
        placebo=in_space_placebo(outcomes, unit_ids, 0, n_pre),
        leave_one_out=leave_one_out(
            treated,
            donors,
            donor_ids,
            n_pre,
            baseline_effect=fit.average_effect,
            only_contributing=fit.contributing_donors(),
        ),
    )


class TestConvexHull:
    def test_a_project_outside_the_donor_hull_is_inconclusive_with_a_warning(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        shifted = outcomes.copy()
        # Lift the project well above every donor in every period.
        shifted[:, 0] = outcomes[:, 1:].max(axis=1) + 0.2

        inputs = _inputs(shifted, unit_ids, n_pre)
        assert inputs.fit.hull is not None and inputs.fit.hull.materially_outside

        bundle = assemble_evidence(inputs, divergence_ratio=1.0)
        assert bundle.verdict is not None
        assert bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "outside the convex hull" in bundle.verdict.rationale
        assert any("outside the convex hull" in w for w in bundle.warnings)
        assert bundle.require("fit.inside_donor_hull").value is False
        assert bundle.require("fit.hull_periods_outside_envelope").value == 1.0
        assert bundle.require("fit.hull_level_excess").value > 0.19

    def test_a_project_inside_the_donor_hull_passes_cleanly(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        inputs = _inputs(outcomes, unit_ids, n_pre)
        assert inputs.fit.hull is not None and not inputs.fit.hull.materially_outside

        bundle = assemble_evidence(inputs, divergence_ratio=1.0)
        assert bundle.verdict is not None
        assert bundle.verdict.label is VerdictLabel.CONSISTENT_WITH_CLAIM
        assert bundle.require("fit.inside_donor_hull").value is True
        assert bundle.require("fit.hull_level_excess").value == 0.0
        assert not any("convex hull" in w for w in bundle.warnings)

    def test_level_excess_is_measured_against_the_range_of_donor_means(self):
        donors = np.array([[0.4, 0.5], [0.5, 0.6], [0.45, 0.55]])
        treated = np.array([0.70, 0.72, 0.74])
        hull = convex_hull_diagnostic(treated, donors)
        assert hull.level_excess == pytest.approx(0.72 - 0.55)
        assert hull.share_periods_outside_envelope == 1.0
        # Per-period excesses are 0.20, 0.12 and 0.19; the first is the largest.
        assert hull.max_envelope_excess == pytest.approx(0.70 - 0.50)

    def test_a_few_noisy_periods_outside_the_envelope_are_not_material(self):
        donors = np.tile(np.array([0.4, 0.6]), (10, 1))
        treated = np.full(10, 0.5)
        treated[3] = 0.61
        hull = convex_hull_diagnostic(treated, donors)
        assert hull.share_periods_outside_envelope == pytest.approx(0.1)
        assert hull.level_excess == 0.0
        assert not hull.materially_outside


class TestFitGate:
    def test_the_gate_fires_on_a_fit_the_mean_scaled_gate_would_have_passed(self, rng):
        n_periods, n_donors, n_pre = 20, 20, 12
        offsets = np.linspace(-0.1, 0.1, n_donors)
        donors = 0.6 + offsets + rng.normal(0.0, 0.001, size=(n_periods, n_donors))
        # Year-to-year variation the donors do not share, so no weighting fits it.
        treated = 0.6 + rng.normal(0.0, 0.02, size=n_periods)
        outcomes = np.column_stack([treated, donors])
        unit_ids = tuple(f"unit-{i:02d}" for i in range(n_donors + 1))

        inputs = _inputs(outcomes, unit_ids, n_pre)
        fit = inputs.fit

        # The old gate: RMSPE as a share of the outcome *level*, limit 30%.
        assert fit.pre_rmspe / abs(fit.treated_pre.mean()) < 0.30
        # The new gate: RMSPE as a share of the outcome *SD*.
        assert fit.relative_pre_fit > MAX_RELATIVE_PRE_FIT
        assert fit.hull is not None and not fit.hull.materially_outside

        verdict = decide_verdict(inputs, divergence_ratio=1.0)
        assert verdict.label is VerdictLabel.INCONCLUSIVE
        assert "pre-treatment fit is poor" in verdict.rationale
        assert "pre-period outcome SD" in verdict.rationale

    def test_a_good_fit_passes_the_gate(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        inputs = _inputs(outcomes, unit_ids, n_pre)
        assert inputs.fit.relative_pre_fit < MAX_RELATIVE_PRE_FIT
        verdict = decide_verdict(inputs, divergence_ratio=1.0)
        assert "pre-treatment fit is poor" not in verdict.rationale

    def test_the_relative_fit_is_recorded_as_evidence(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        bundle = assemble_evidence(_inputs(outcomes, unit_ids, n_pre))
        item = bundle.require("fit.relative_pre_rmspe")
        assert item.qualifiers["gate_threshold"] == MAX_RELATIVE_PRE_FIT
        assert item.value == pytest.approx(
            bundle.require("fit.pre_rmspe").value / float(np.std(outcomes[:n_pre, 0], ddof=1)),
            rel=1e-9,
        )
