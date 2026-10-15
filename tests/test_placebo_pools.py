"""The treated unit must never be a donor in a placebo fit (issue #55)."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.contracts.errors import EstimationError
from groundtruth.engine.uncertainty import placebo as placebo_module
from groundtruth.engine.uncertainty.placebo import in_space_placebo
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import synthetic_access


def _with_effect(factor_panel, effect: float) -> tuple[np.ndarray, tuple[str, ...], int]:
    outcomes, unit_ids, n_pre, injected = factor_panel
    panel = outcomes.copy()
    panel[n_pre:, 0] += effect - injected
    return panel, unit_ids, n_pre


def test_no_placebo_fit_is_offered_the_treated_unit(factor_panel, monkeypatch):
    panel, unit_ids, n_pre = _with_effect(factor_panel, 0.5)
    seen: list[tuple[str, tuple[str, ...]]] = []
    real_fit = placebo_module.fit_synthetic_control

    def recording_fit(treated, donors, donor_ids, *args, **kwargs):  # type: ignore[no-untyped-def]
        fit = real_fit(treated, donors, donor_ids, *args, **kwargs)
        seen.append((str(treated[0]), donor_ids))
        weights = dict(zip(donor_ids, fit.weights, strict=True))
        if donor_ids != unit_ids[1:]:  # a placebo fit, not the treated unit's own
            assert weights.get(unit_ids[0], 0.0) == 0.0
        return fit

    monkeypatch.setattr(placebo_module, "fit_synthetic_control", recording_fit)
    in_space_placebo(panel, unit_ids, 0, n_pre)

    placebo_pools = [donors for _, donors in seen[1:]]
    assert len(placebo_pools) == len(unit_ids) - 1
    assert all(unit_ids[0] not in pool for pool in placebo_pools)
    assert all(len(pool) == len(unit_ids) - 2 for pool in placebo_pools)


def test_the_reference_distribution_does_not_depend_on_the_treated_effect(factor_panel):
    """The defining property: placebos describe untreated outcomes only."""
    small = in_space_placebo(*_with_effect(factor_panel, 0.0)[:2], 0, factor_panel[2])
    large = in_space_placebo(*_with_effect(factor_panel, 0.3)[:2], 0, factor_panel[2])
    assert small.placebo_statistics == large.placebo_statistics


class TestRegressionAgainstTheContaminatedVersion:
    """Values from the same seeded panel before and after the fix.

    "Before" was measured on the engine as of 0.5.0, where each placebo pool
    still contained the treated unit. The shift is not uniformly conservative,
    which is why it is recorded here rather than assumed.
    """

    @pytest.mark.parametrize(
        ("effect", "p_before", "p_after"),
        [
            (0.0, 14 / 24, 13 / 24),
            (0.005, 9 / 24, 10 / 24),
            (0.07, 1 / 24, 1 / 24),
        ],
    )
    def test_p_value_shift(self, factor_panel, effect, p_before, p_after):
        # p_before is kept in the parameters as the documented baseline.
        panel, unit_ids, n_pre = _with_effect(factor_panel, effect)
        result = in_space_placebo(panel, unit_ids, 0, n_pre)
        assert result.p_value == pytest.approx(p_after)

    def test_contamination_inflated_the_placebo_tail(self, factor_panel):
        panel, unit_ids, n_pre = _with_effect(factor_panel, 0.3)
        result = in_space_placebo(panel, unit_ids, 0, n_pre)
        # Contaminated: the largest placebo ratio was 11.56. Clean: 2.44.
        assert max(result.placebo_statistics) == pytest.approx(2.441, abs=1e-3)

    def test_the_poor_fit_screen_is_unchanged_by_the_smaller_pools(self, factor_panel):
        panel, unit_ids, n_pre = _with_effect(factor_panel, 0.07)
        result = in_space_placebo(panel, unit_ids, 0, n_pre)
        # One fewer donor per placebo pool; the screen still drops the same one unit.
        assert result.excluded_poor_fit == 1
        assert result.n_placebos == len(unit_ids) - 2


def test_further_units_can_be_kept_out_of_placebo_pools(factor_panel, monkeypatch):
    panel, unit_ids, n_pre = _with_effect(factor_panel, 0.07)
    pools: list[tuple[str, ...]] = []
    real_fit = placebo_module.fit_synthetic_control

    def recording_fit(treated, donors, donor_ids, *args, **kwargs):  # type: ignore[no-untyped-def]
        pools.append(donor_ids)
        return real_fit(treated, donors, donor_ids, *args, **kwargs)

    monkeypatch.setattr(placebo_module, "fit_synthetic_control", recording_fit)
    result = in_space_placebo(panel, unit_ids, 0, n_pre, exclude_indices=(3,))

    assert result.excluded_from_placebo_pools == (unit_ids[0], unit_ids[3])
    assert all(unit_ids[3] not in pool for pool in pools[1:])
    # Still a placebo unit itself: one fit has it as the pretend-treated unit.
    assert len(pools) == len(unit_ids)


def test_an_out_of_range_exclusion_is_a_programming_error(factor_panel):
    panel, unit_ids, n_pre = _with_effect(factor_panel, 0.07)
    with pytest.raises(EstimationError):
        in_space_placebo(panel, unit_ids, 0, n_pre, exclude_indices=(99,))


def test_the_bundle_provenance_states_the_exclusion():
    request = get_case("kariba-redd").to_request(seed=20260101)
    from groundtruth.engine import run_analysis

    result = run_analysis(request, synthetic_access(request, true_effect=0.06))
    assert result.bundle is not None
    prov = result.bundle.require("placebo.p_value").provenance
    assert prov.parameters["excluded_from_placebo_pools"] == [request.case_id]
    assert "never a donor in a placebo fit" in (prov.notes or "")
