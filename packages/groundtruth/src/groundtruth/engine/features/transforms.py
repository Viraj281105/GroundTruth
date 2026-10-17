"""Covariate transforms: pure functions over per-unit scalars.

Which covariates matter, and on what scale they are compared, is methodology and
lives here. Fetching them is plumbing and lives behind ``CovariateAccess`` in the
platform. This is the engine half of coordination point C4.

Every transform returns its output together with a :class:`TransformRecord`
naming the transform and every parameter it used, including any quantiles
learned from the reference pool, so the transformation travels with the
numbers into provenance.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from groundtruth.contracts.errors import EstimationError


@dataclass(frozen=True)
class TransformRecord:
    """What was done to one covariate, for provenance."""

    covariate: str
    steps: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)

    def as_provenance(self) -> dict[str, Any]:
        """JSON-safe form for ``Provenance.parameters``."""
        return {"covariate": self.covariate, "steps": list(self.steps), **self.parameters}


def _as_array(values: Sequence[float] | np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise EstimationError("covariate transforms take a one-dimensional array of unit values")
    if not np.isfinite(array).all():
        raise EstimationError("covariate values must be finite before they are transformed")
    return array


def log1p(values: Sequence[float] | np.ndarray) -> np.ndarray:
    """``log(1 + x)``, for non-negative right-skewed quantities.

    Used for distances and densities, where the difference between 1 and 5 km
    to a road matters far more than between 51 and 55 km. ``log1p`` rather than
    ``log`` keeps zero (a unit on a road, an empty district) finite.

    Raises:
        EstimationError: on a negative value, which would mean the covariate is
            not the quantity this transform was chosen for.
    """
    array = _as_array(values)
    if (array < 0).any():
        raise EstimationError("log1p is defined here only for non-negative covariates")
    return np.log1p(array)


def winsorise(
    values: Sequence[float] | np.ndarray,
    *,
    reference: Sequence[float] | np.ndarray | None = None,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
) -> tuple[np.ndarray, tuple[float, float]]:
    """Clip values to quantiles of a reference distribution.

    Args:
        values: Values to clip.
        reference: Distribution the bounds are learned from; ``values`` itself
            if omitted. Learning from the candidate pool, not the project,
            keeps the project's own value from moving the bounds.
        lower_quantile: Lower clipping quantile.
        upper_quantile: Upper clipping quantile.

    Returns:
        ``(clipped, (lower_bound, upper_bound))``. The bounds are returned so
        they can be recorded; the same bounds must be applied to the project.
    """
    if not 0.0 <= lower_quantile < upper_quantile <= 1.0:
        raise EstimationError("winsorising quantiles must satisfy 0 <= lower < upper <= 1")
    array = _as_array(values)
    ref = array if reference is None else _as_array(reference)
    if ref.size == 0:
        raise EstimationError("cannot learn winsorising bounds from an empty reference")
    lower, upper = (float(q) for q in np.quantile(ref, [lower_quantile, upper_quantile]))
    return np.clip(array, lower, upper), (lower, upper)


def standardise(
    values: Sequence[float] | np.ndarray,
    *,
    reference: Sequence[float] | np.ndarray | None = None,
) -> tuple[np.ndarray, tuple[float, float]]:
    """Z-score values against a reference distribution.

    Returns:
        ``(z_scores, (centre, scale))``. A zero-variance reference gets scale
        1.0 rather than a division by zero: every unit is then equally distant
        on that covariate, which is what a constant covariate means.
    """
    array = _as_array(values)
    ref = array if reference is None else _as_array(reference)
    if ref.size == 0:
        raise EstimationError("cannot standardise against an empty reference")
    centre = float(ref.mean())
    scale = float(ref.std(ddof=1)) if ref.size > 1 else 1.0
    if scale < 1e-12:
        scale = 1.0
    return (array - centre) / scale, (centre, scale)


IDENTITY = "identity"
LOG1P = "log1p"

COVARIATE_TRANSFORMS: Mapping[str, str] = {
    "rainfall_mm": IDENTITY,
    "elevation_m": IDENTITY,
    "slope_deg": IDENTITY,
    "road_distance_km": LOG1P,
    "population_density": LOG1P,
}
"""The scale each matching covariate is compared on.

Rationale per covariate is in ``docs/data/sources.md``. A covariate missing from
this mapping is compared on its raw scale, and :func:`engineer_covariates`
records that it was unregistered so the omission is visible.
"""


@dataclass(frozen=True)
class EngineeredCovariates:
    """Project and candidate covariates on their matching scale."""

    project: dict[str, float]
    candidates: dict[str, dict[str, float]]
    records: tuple[TransformRecord, ...]


def engineer_covariates(
    project: Mapping[str, float],
    candidates: Mapping[str, Mapping[str, float]],
    keys: Sequence[str],
    *,
    transforms: Mapping[str, str] = COVARIATE_TRANSFORMS,
) -> EngineeredCovariates:
    """Apply each covariate's registered transform to the project and every candidate.

    The same transform, with the same parameters, is applied to the project
    and to every candidate. Only units that carry a covariate are transformed
    on it; a missing value stays missing for matching to handle.

    Raises:
        EstimationError: if a value is outside the domain of its transform.
    """
    project_out = dict(project)
    candidates_out = {uid: dict(values) for uid, values in candidates.items()}
    records: list[TransformRecord] = []
    for key in keys:
        name = transforms.get(key)
        if name is None:
            records.append(TransformRecord(key, (IDENTITY,), {"registered": False}))
            continue
        if name == IDENTITY:
            records.append(TransformRecord(key, (IDENTITY,), {"registered": True}))
            continue
        if name != LOG1P:
            raise EstimationError(f"unknown covariate transform {name!r} for {key!r}")

        unit_ids = [uid for uid, values in candidates_out.items() if key in values]
        stacked = [candidates_out[uid][key] for uid in unit_ids]
        if key in project_out:
            stacked.append(project_out[key])
        transformed = log1p(stacked) if stacked else np.empty(0)
        for uid, value in zip(unit_ids, transformed, strict=False):
            candidates_out[uid][key] = float(value)
        if key in project_out:
            project_out[key] = float(transformed[-1])
        records.append(TransformRecord(key, (LOG1P,), {"registered": True}))

    return EngineeredCovariates(project_out, candidates_out, tuple(records))


__all__ = [
    "COVARIATE_TRANSFORMS",
    "IDENTITY",
    "LOG1P",
    "EngineeredCovariates",
    "TransformRecord",
    "engineer_covariates",
    "log1p",
    "standardise",
    "winsorise",
]
