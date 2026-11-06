"""Property tests for the synthetic-control and placebo engine."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from groundtruth.engine.causal.synthetic_control import fit_synthetic_control
from groundtruth.engine.uncertainty.placebo import in_space_placebo

N_PRE = 10
SETTINGS = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@st.composite
def panels(draw: st.DrawFn) -> np.ndarray:
    """An ``(n_periods, n_units)`` panel; column 0 is the treated unit."""
    seed = draw(st.integers(0, 2**31 - 1))
    n_donors = draw(st.integers(6, 12))
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(3, 16)).cumsum(axis=1) * 0.05 + 0.6
    load = rng.dirichlet(np.ones(3), size=n_donors + 1)
    out = (load @ base).T + rng.normal(0, 0.01, size=(16, n_donors + 1))
    out[N_PRE:, 0] += 0.05
    return out


def _ids(n: int) -> tuple[str, ...]:
    return tuple(f"d{i:02d}" for i in range(n))


@SETTINGS
@given(panels())
def test_fit_is_deterministic(panel: np.ndarray) -> None:
    ids = _ids(panel.shape[1] - 1)
    a = fit_synthetic_control(panel[:, 0], panel[:, 1:], ids, N_PRE)
    b = fit_synthetic_control(panel[:, 0], panel[:, 1:], ids, N_PRE)
    assert np.array_equal(a.weights, b.weights)


@SETTINGS
@given(panels())
def test_weights_are_a_simplex(panel: np.ndarray) -> None:
    ids = _ids(panel.shape[1] - 1)
    fit = fit_synthetic_control(panel[:, 0], panel[:, 1:], ids, N_PRE)
    assert (fit.weights >= -1e-9).all()
    assert abs(float(fit.weights.sum()) - 1.0) < 1e-6


@SETTINGS
@given(panels())
def test_placebo_p_value_in_unit_interval(panel: np.ndarray) -> None:
    res = in_space_placebo(panel, _ids(panel.shape[1]), 0, N_PRE)
    assert 0.0 <= res.p_value <= 1.0


@SETTINGS
@given(panels(), st.integers(0, 2**31 - 1))
def test_estimate_invariant_to_donor_order(panel: np.ndarray, seed: int) -> None:
    donors = panel[:, 1:]
    ids = _ids(donors.shape[1])
    perm = np.random.default_rng(seed).permutation(donors.shape[1])
    a = fit_synthetic_control(panel[:, 0], donors, ids, N_PRE)
    b = fit_synthetic_control(panel[:, 0], donors[:, perm], tuple(ids[i] for i in perm), N_PRE)
    gap_a = a.treated_post - a.synthetic_post
    gap_b = b.treated_post - b.synthetic_post
    assert np.allclose(gap_a, gap_b, atol=1e-4)
