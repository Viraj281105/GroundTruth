"""Cloud, shadow and quality masking.

Cloud contamination is the dominant source of spurious "greening" and "browning"
in tropical time series. Masking decisions are therefore recorded as data, not
buried in a compositing step: every masked series carries the number of clear
observations behind each period so downstream stages can refuse cloud-starved
years rather than quietly interpolating over them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Sentinel-2 Scene Classification Layer classes that should be discarded.
SCL_INVALID_CLASSES: tuple[int, ...] = (
    0,  # no data
    1,  # saturated / defective
    3,  # cloud shadow
    8,  # cloud medium probability
    9,  # cloud high probability
    10,  # thin cirrus
    11,  # snow / ice
)


@dataclass(frozen=True)
class MaskingReport:
    """Summary of how much of a series survived quality masking."""

    n_periods: int
    n_valid_per_period: tuple[int, ...]
    min_valid_observations: int
    periods_below_threshold: tuple[int, ...]

    @property
    def has_sparse_periods(self) -> bool:
        """True if any period fell below the clear-observation threshold."""
        return len(self.periods_below_threshold) > 0


def scl_cloud_mask(scl: np.ndarray, invalid: tuple[int, ...] = SCL_INVALID_CLASSES) -> np.ndarray:
    """Boolean mask that is ``True`` for *usable* pixels in a Sentinel-2 SCL band."""
    scl_a = np.asarray(scl)
    return ~np.isin(scl_a, np.asarray(invalid))


def apply_mask(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Set masked-out pixels to NaN so reducers can ignore them."""
    out = np.asarray(values, dtype=float).copy()
    out[~np.asarray(mask, dtype=bool)] = np.nan
    return out


def composite_median(stack: np.ndarray, *, axis: int = 0) -> np.ndarray:
    """NaN-aware median composite across a time axis.

    A median is preferred over a mean because residual undetected cloud is a
    heavy positive-reflectance outlier, which a mean would absorb.
    """
    arr = np.asarray(stack, dtype=float)
    with np.errstate(all="ignore"):
        return np.nanmedian(arr, axis=axis)


def valid_observation_counts(stack: np.ndarray, *, axis: int = 0) -> np.ndarray:
    """Count non-NaN observations along the time axis."""
    return np.sum(~np.isnan(np.asarray(stack, dtype=float)), axis=axis)


def audit_masking(
    periods: tuple[int, ...],
    n_valid: tuple[int, ...],
    *,
    min_observations: int = 4,
) -> MaskingReport:
    """Summarise clear-observation coverage and flag periods that are too sparse.

    Args:
        periods: Period labels.
        n_valid: Clear observations backing each period.
        min_observations: Minimum clear scenes for a period to be trusted.
    """
    if len(periods) != len(n_valid):
        raise ValueError("periods and n_valid must have the same length")
    sparse = tuple(p for p, n in zip(periods, n_valid, strict=True) if n < min_observations)
    return MaskingReport(
        n_periods=len(periods),
        n_valid_per_period=tuple(int(n) for n in n_valid),
        min_valid_observations=int(min(n_valid)) if n_valid else 0,
        periods_below_threshold=sparse,
    )
