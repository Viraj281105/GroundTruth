"""Spectral index computation.

These are pure array functions with no I/O, which makes them directly testable
against the published formulae.
"""

from __future__ import annotations

import numpy as np


def _safe_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Element-wise division that yields NaN instead of raising on zero denominators."""
    out = np.full(np.broadcast(numerator, denominator).shape, np.nan, dtype=float)
    valid = np.abs(denominator) > 1e-12
    np.divide(numerator, denominator, out=out, where=valid)
    return out


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """Normalised Difference Vegetation Index, ``(NIR - Red) / (NIR + Red)``.

    Bounded in ``[-1, 1]``. NDVI saturates over dense canopy, which is precisely
    why it is a weak proxy for biomass in closed-canopy forest. It is used here
    as a *condition* indicator, never converted directly to carbon.
    """
    nir_a, red_a = np.asarray(nir, dtype=float), np.asarray(red, dtype=float)
    return _safe_ratio(nir_a - red_a, nir_a + red_a)


def evi(nir: np.ndarray, red: np.ndarray, blue: np.ndarray, *, gain: float = 2.5) -> np.ndarray:
    """Enhanced Vegetation Index (Huete et al., 2002).

    Less prone to canopy saturation than NDVI and more robust to aerosols, at the
    cost of sensitivity to blue-band calibration.
    """
    nir_a = np.asarray(nir, dtype=float)
    red_a = np.asarray(red, dtype=float)
    blue_a = np.asarray(blue, dtype=float)
    return gain * _safe_ratio(nir_a - red_a, nir_a + 6.0 * red_a - 7.5 * blue_a + 1.0)


def nbr(nir: np.ndarray, swir: np.ndarray) -> np.ndarray:
    """Normalised Burn Ratio, used to separate fire disturbance from clearing."""
    nir_a, swir_a = np.asarray(nir, dtype=float), np.asarray(swir, dtype=float)
    return _safe_ratio(nir_a - swir_a, nir_a + swir_a)


def savi(nir: np.ndarray, red: np.ndarray, *, soil_factor: float = 0.5) -> np.ndarray:
    """Soil-Adjusted Vegetation Index, for sparse-canopy dryland projects."""
    nir_a, red_a = np.asarray(nir, dtype=float), np.asarray(red, dtype=float)
    return _safe_ratio((nir_a - red_a) * (1.0 + soil_factor), nir_a + red_a + soil_factor)
