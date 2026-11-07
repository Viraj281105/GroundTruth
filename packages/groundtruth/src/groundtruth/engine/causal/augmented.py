"""Augmented synthetic control (Ben-Michael, Feller & Rothstein 2021), numpy only.

Starts from simplex-constrained synthetic control weights and adds a ridge
regression bias correction fitted on the donors' pre-period to post-period
relationship. The correction removes bias from imperfect pre-period fit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.contracts.errors import InsufficientDataError
from groundtruth.engine.causal.synthetic_control import fit_synthetic_control


@dataclass(frozen=True)
class AugmentedFit:
    """Augmented synthetic control result.

    Attributes:
        effect_path: Post-period gap (treated minus counterfactual), per period.
        att: Mean post-period gap.
        counterfactual_post: Bias-corrected post-period counterfactual.
        scm_att: Mean post-period gap of the uncorrected synthetic control.
        bias_correction: ``scm_att - att``; how much the correction moved the estimate.
        ridge_lambda: Ridge penalty used.
        pre_rmspe: Pre-period RMSPE of the uncorrected synthetic control.
    """

    effect_path: np.ndarray
    att: float
    counterfactual_post: np.ndarray
    scm_att: float
    bias_correction: float
    ridge_lambda: float
    pre_rmspe: float


def fit_augmented_synthetic_control(
    treated_series: np.ndarray,
    donor_matrix: np.ndarray,
    n_pre_periods: int,
    ridge_lambda: float = 1.0,
    seed: int = 0,
) -> AugmentedFit:
    """Fit ASCM. ``donor_matrix`` is (T, J); the first ``n_pre_periods`` rows are pre.

    ``seed`` is accepted for API uniformity; the procedure is deterministic.
    """
    del seed
    y = np.asarray(treated_series, dtype=float)
    x = np.asarray(donor_matrix, dtype=float)
    t0 = int(n_pre_periods)
    if x.ndim != 2 or x.shape[0] != y.shape[0]:
        raise ValueError("donor_matrix must be (T, J) matching treated_series length")
    if t0 < 5 or t0 >= y.shape[0]:
        raise InsufficientDataError("need >=5 pre-periods and >=1 post-period")
    if ridge_lambda < 0:
        raise ValueError("ridge_lambda must be non-negative")
    ids = tuple(str(j) for j in range(x.shape[1]))
    scm = fit_synthetic_control(y, x, ids, t0)
    w = np.asarray(scm.weights, dtype=float)
    # Ridge outcome model: post-period donor outcomes regressed on pre-period outcomes.
    xpre, xpost = x[:t0].T, x[t0:].T  # (J, t0), (J, T1)
    mu = xpre.mean(axis=0)
    xc = xpre - mu
    ym = xpost.mean(axis=0)
    gram = xc.T @ xc + ridge_lambda * np.eye(t0)
    beta = np.linalg.solve(gram, xc.T @ (xpost - ym))  # (t0, T1)
    treated_pre_c = y[:t0] - mu
    synth_pre_c = xpre.T @ w - mu
    scm_post = x[t0:] @ w
    correction = (treated_pre_c - synth_pre_c) @ beta
    cf = scm_post + correction
    gap = y[t0:] - cf
    scm_att = float(np.mean(y[t0:] - scm_post))
    att = float(np.mean(gap))
    return AugmentedFit(
        gap, att, cf, scm_att, scm_att - att, float(ridge_lambda), float(scm.pre_rmspe)
    )
