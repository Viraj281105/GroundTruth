"""Optional cross-check of the main estimate against pysyncon / dowhy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CrossCheck:
    """Independent estimate and its agreement with the main one."""

    backend: str
    main_estimate: float
    other_estimate: float
    agreement: float
    interpretation: str


def agreement_metric(main: float, other: float) -> float:
    """1 - |a-b| / max(|a|,|b|), clipped to [0, 1]; 1.0 when both are zero."""
    scale = max(abs(main), abs(other))
    if scale == 0:
        return 1.0
    return float(max(0.0, 1.0 - abs(main - other) / scale))


def _text(name: str, a: float) -> str:
    return (
        f"{name} gives an estimate with agreement {a:.2f} (1 = identical) relative to the "
        "main estimate. Agreement is a consistency check, not validation of causality."
    )


def crosscheck_pysyncon(
    treated_series: np.ndarray,
    donor_matrix: np.ndarray,
    n_pre_periods: int,
    main_estimate: float,
) -> CrossCheck:
    """Re-estimate the mean post gap with pysyncon's Synth and compare."""
    try:
        import pandas as pd
        from pysyncon import Dataprep, Synth
    except ImportError as exc:
        raise ImportError("pysyncon is required: pip install pysyncon") from exc
    y = np.asarray(treated_series, dtype=float)
    x = np.asarray(donor_matrix, dtype=float)
    names = [f"d{j}" for j in range(x.shape[1])]
    wide = pd.DataFrame(x, columns=names)
    wide["treated"] = y
    wide["time"] = np.arange(y.shape[0])
    long = wide.melt(id_vars="time", var_name="unit", value_name="y")
    pre = range(n_pre_periods)
    prep = Dataprep(
        foo=long,
        predictors=["y"],
        predictors_op="mean",
        time_predictors_prior=pre,
        dependent="y",
        unit_variable="unit",
        time_variable="time",
        treatment_identifier="treated",
        controls_identifier=names,
        time_optimize_ssr=pre,
    )
    synth = Synth()
    synth.fit(dataprep=prep)
    w = np.asarray(synth.W, dtype=float)
    other = float(np.mean(y[n_pre_periods:] - x[n_pre_periods:] @ w))
    a = agreement_metric(main_estimate, other)
    return CrossCheck("pysyncon", main_estimate, other, a, _text("pysyncon", a))


def crosscheck_dowhy(
    outcome: np.ndarray, treatment: np.ndarray, main_estimate: float, seed: int = 0
) -> CrossCheck:
    """Estimate the treatment effect with dowhy's linear regression and compare."""
    try:
        import pandas as pd
        from dowhy import CausalModel
    except ImportError as exc:
        raise ImportError("dowhy is required: pip install dowhy") from exc
    np.random.seed(seed)
    df = pd.DataFrame({"y": np.asarray(outcome, float), "t": np.asarray(treatment, float)})
    model = CausalModel(data=df, treatment="t", outcome="y", common_causes=[])
    est = model.estimate_effect(
        model.identify_effect(proceed_when_unidentifiable=True),
        method_name="backdoor.linear_regression",
    )
    other = float(est.value)
    a = agreement_metric(main_estimate, other)
    return CrossCheck("dowhy", main_estimate, other, a, _text("dowhy", a))
