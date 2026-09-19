"""Zonal statistics and boundary handling.

Real raster clipping needs the optional ``geo`` extra (rasterio/shapely). The
functions here that operate on already-extracted arrays are dependency-free so
the core pipeline and its tests run everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ZonalStats:
    """Summary statistics for one zone in one period."""

    mean: float
    median: float
    std: float
    p10: float
    p90: float
    n_valid: int
    n_total: int

    @property
    def valid_fraction(self) -> float:
        """Share of pixels in the zone that survived masking."""
        return self.n_valid / self.n_total if self.n_total else 0.0


def zonal_stats(values: np.ndarray) -> ZonalStats:
    """Compute NaN-aware summary statistics over a zone's pixel values."""
    arr = np.asarray(values, dtype=float).ravel()
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return ZonalStats(np.nan, np.nan, np.nan, np.nan, np.nan, 0, int(arr.size))
    return ZonalStats(
        mean=float(np.mean(valid)),
        median=float(np.median(valid)),
        std=float(np.std(valid, ddof=1)) if valid.size > 1 else 0.0,
        p10=float(np.percentile(valid, 10)),
        p90=float(np.percentile(valid, 90)),
        n_valid=int(valid.size),
        n_total=int(arr.size),
    )


def apply_edge_buffer_note(buffer_m: float) -> str:
    """Return the caveat text that must accompany buffered zonal statistics.

    Project boundaries are frequently drawn along roads and rivers, so edge
    pixels mix land-cover classes. GroundTruth buffers boundaries inward and
    records the fact, because an un-noted buffer changes the estimate.
    """
    return (
        f"Zonal statistics computed on an inward buffer of {buffer_m:.0f} m to avoid mixed "
        "boundary pixels; effect sizes are therefore for the buffered interior, not the "
        "full registered area."
    )


def leakage_belt_note(inner_km: float, outer_km: float) -> str:
    """Caveat text for the leakage belt surrounding a project."""
    return (
        f"A leakage belt of {inner_km:.0f}-{outer_km:.0f} km around the project boundary is "
        "monitored separately. Displaced deforestation inside this belt offsets, and can fully "
        "negate, an apparent within-boundary gain."
    )
