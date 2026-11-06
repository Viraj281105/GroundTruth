"""Tests for augmented SC, conformal intervals, sensitivity and crosscheck."""

from __future__ import annotations

import numpy as np
import pytest

from groundtruth.engine.causal.augmented import fit_augmented_synthetic_control
from groundtruth.engine.causal.crosscheck import agreement_metric
from groundtruth.engine.uncertainty.conformal import conformal_gap_interval
from groundtruth.engine.uncertainty.sensitivity import confounder_bound, e_value

T0, T, TRUE = 30, 40, 5.0


def _panel(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    f = np.cumsum(rng.normal(size=T)) * 0.5
    load = rng.uniform(0.5, 1.5, size=12)
    donors = np.outer(f, load) + rng.normal(scale=0.3, size=(T, 12)) + 10
    y = f + rng.normal(scale=0.3, size=T) + 10
    y[T0:] += TRUE
    return y, donors


def test_augmented_recovers_effect() -> None:
    y, d = _panel(1)
    fit = fit_augmented_synthetic_control(y, d, T0)
    assert abs(fit.att - TRUE) < 1.0
    assert fit.effect_path.shape == (T - T0,)


def test_augmented_deterministic() -> None:
    y, d = _panel(2)
    a = fit_augmented_synthetic_control(y, d, T0, seed=3).att
    assert a == fit_augmented_synthetic_control(y, d, T0, seed=3).att


def test_conformal_coverage() -> None:
    hits, n = 0, 200
    for s in range(n):
        rng = np.random.default_rng(s)
        ci = conformal_gap_interval(
            rng.normal(size=40), rng.normal(size=1), alpha=0.1, method="full_sample"
        )
        hits += int(ci.per_period_lower[0] <= 0.0 <= ci.per_period_upper[0])
    assert hits / n > 0.8


def test_conformal_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        conformal_gap_interval(np.ones(10), np.ones(2), alpha=2.0)


def test_e_value_known() -> None:
    assert e_value(2.0).e_value_point == pytest.approx(2 + 2**0.5)
    assert e_value(0.5).e_value_point == pytest.approx(2 + 2**0.5)
    assert e_value(1.5, ci_bound=0.9).e_value_ci == 1.0
    assert "not proof" in e_value(2.0).interpretation


def test_confounder_bound_sign() -> None:
    assert confounder_bound(1.0, 2.0).breaks_sign
    assert not confounder_bound(1.0, 0.2).breaks_sign


def test_agreement_metric() -> None:
    assert agreement_metric(0.0, 0.0) == 1.0
    assert agreement_metric(2.0, 1.0) == pytest.approx(0.5)
