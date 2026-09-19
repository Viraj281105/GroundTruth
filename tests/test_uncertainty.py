"""Tests for placebo inference and robustness checks."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.causal.synthetic_control import fit_synthetic_control
from groundtruth.core.errors import EstimationError, InsufficientDataError
from groundtruth.uncertainty.placebo import in_space_placebo, in_time_placebo
from groundtruth.uncertainty.robustness import (
    SpecificationCurve,
    leave_one_out,
    permutation_interval,
)


class TestInSpacePlacebo:
    def test_a_real_effect_ranks_extreme(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        result = in_space_placebo(outcomes, unit_ids, 0, n_pre)
        assert result.is_extreme
        assert result.rank == 1

    def test_no_effect_is_not_flagged_as_extreme(self, null_panel):
        outcomes, unit_ids, n_pre = null_panel
        result = in_space_placebo(outcomes, unit_ids, 0, n_pre)
        assert not result.is_extreme

    def test_p_value_is_never_exactly_zero(self, factor_panel):
        """The add-one correction: with N placebos the smallest p is 1/(N+1)."""
        outcomes, unit_ids, n_pre, _ = factor_panel
        result = in_space_placebo(outcomes, unit_ids, 0, n_pre)
        assert result.p_value > 0.0
        assert result.p_value == pytest.approx(1.0 / (result.n_placebos + 1), rel=1e-9)

    def test_p_value_is_bounded(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        result = in_space_placebo(outcomes, unit_ids, 0, n_pre)
        assert 0.0 < result.p_value <= 1.0

    def test_interpretation_does_not_claim_a_probability_of_misreporting(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        text = in_space_placebo(outcomes, unit_ids, 0, n_pre).interpretation().lower()
        assert "not a probability that the project misreported" in text
        assert "fraud" not in text

    def test_requires_at_least_three_units(self):
        outcomes = np.random.default_rng(0).normal(size=(20, 2))
        with pytest.raises(InsufficientDataError):
            in_space_placebo(outcomes, ("a", "b"), 0, 12)

    def test_rejects_mismatched_unit_ids(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        with pytest.raises(EstimationError):
            in_space_placebo(outcomes, unit_ids[:-1], 0, n_pre)


class TestInTimePlacebo:
    def test_no_spurious_effect_before_the_real_treatment(self, factor_panel):
        outcomes, unit_ids, n_pre, true_effect = factor_panel
        result = in_time_placebo(
            outcomes[:, 0],
            outcomes[:, 1:],
            unit_ids[1:],
            n_pre,
            fake_treatment_index=6,
            true_effect=true_effect,
        )
        assert result.passes

    def test_fake_treatment_must_sit_inside_the_pre_period(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        with pytest.raises(EstimationError, match="inside the pre-treatment period"):
            in_time_placebo(
                outcomes[:, 0],
                outcomes[:, 1:],
                unit_ids[1:],
                n_pre,
                fake_treatment_index=n_pre + 2,
                true_effect=0.07,
            )


class TestLeaveOneOut:
    def test_sign_is_stable_for_a_genuine_effect(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        fit = fit_synthetic_control(outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre)
        result = leave_one_out(
            outcomes[:, 0],
            outcomes[:, 1:],
            unit_ids[1:],
            n_pre,
            baseline_effect=fit.average_effect,
            only_contributing=fit.contributing_donors(),
        )
        assert result.sign_is_stable
        assert result.effects

    def test_shift_is_small_when_no_single_donor_dominates(self, factor_panel):
        outcomes, unit_ids, n_pre, true_effect = factor_panel
        fit = fit_synthetic_control(outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre)
        result = leave_one_out(
            outcomes[:, 0],
            outcomes[:, 1:],
            unit_ids[1:],
            n_pre,
            baseline_effect=fit.average_effect,
            only_contributing=fit.contributing_donors(),
        )
        assert result.max_absolute_shift < 0.5 * true_effect

    def test_envelope_is_labelled_a_sensitivity_envelope(self, factor_panel):
        outcomes, unit_ids, n_pre, _ = factor_panel
        fit = fit_synthetic_control(outcomes[:, 0], outcomes[:, 1:], unit_ids[1:], n_pre)
        result = leave_one_out(
            outcomes[:, 0],
            outcomes[:, 1:],
            unit_ids[1:],
            n_pre,
            baseline_effect=fit.average_effect,
            only_contributing=fit.contributing_donors(),
        )
        envelope = result.envelope()
        assert envelope.kind == "sensitivity-envelope"
        assert envelope.lower <= envelope.upper


class TestPermutationInterval:
    def test_interval_brackets_the_estimate(self):
        placebos = tuple(np.linspace(-0.02, 0.02, 21))
        interval = permutation_interval(0.05, placebos)
        assert interval.contains(0.05)
        assert interval.kind == "permutation"

    def test_refuses_to_build_an_interval_from_too_few_placebos(self):
        with pytest.raises(InsufficientDataError):
            permutation_interval(0.05, (0.01, 0.02))


class TestSpecificationCurve:
    def test_sign_agreement_is_one_when_all_specifications_agree(self):
        curve = SpecificationCurve({"a": 0.04, "b": 0.05, "c": 0.06})
        assert curve.sign_agreement == pytest.approx(1.0)
        assert curve.median == pytest.approx(0.05)

    def test_sign_agreement_falls_when_specifications_disagree(self):
        curve = SpecificationCurve({"a": 0.04, "b": -0.05, "c": 0.06, "d": -0.01})
        assert curve.sign_agreement < 1.0

    def test_envelope_spans_the_specifications(self):
        curve = SpecificationCurve({"a": 0.04, "b": 0.05, "c": 0.06})
        envelope = curve.envelope()
        assert envelope.lower == pytest.approx(0.04)
        assert envelope.upper == pytest.approx(0.06)
        assert envelope.kind == "sensitivity-envelope"
