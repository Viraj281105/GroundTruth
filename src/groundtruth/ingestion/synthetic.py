"""Synthetic observation provider for offline development and testing.

**This provider generates simulated data. It is not real Earth observation and
must never be used to produce a published finding.** Every series it emits is
stamped with ``method='synthetic-simulation'`` in its provenance, and the
evidence assembler refuses to attach a verdict of record to synthetic runs.

Its purpose is to let the causal machinery be developed, tested and demonstrated
deterministically while Earth Engine credentials and real donor pools are being
wired up.
"""

from __future__ import annotations

import numpy as np

from groundtruth.core.provenance import Provenance
from groundtruth.core.types import Indicator, TimeSeries
from groundtruth.ingestion.base import AreaOfInterest, ObservationRequest

SYNTHETIC_MARKER = "synthetic-simulation"


class SyntheticObservationProvider:
    """Deterministic simulator with a shared latent factor structure.

    Units are generated from a small number of common factors plus unit-specific
    noise, which is exactly the data-generating process synthetic control assumes.
    A single designated treated unit can be given a known post-treatment effect,
    which makes it possible to test whether the estimator recovers the truth.
    """

    name = "synthetic"

    def __init__(
        self,
        *,
        seed: int = 20260101,
        n_factors: int = 3,
        noise_sd: float = 0.01,
        treated_unit_id: str | None = None,
        true_effect: float = 0.0,
        treatment_period: int | None = None,
    ) -> None:
        self.seed = seed
        self.n_factors = n_factors
        self.noise_sd = noise_sd
        self.treated_unit_id = treated_unit_id
        self.true_effect = true_effect
        self.treatment_period = treatment_period

    def provenance(self, request: ObservationRequest) -> Provenance:
        """Provenance that unambiguously flags the data as simulated."""
        return Provenance.computed(
            source="groundtruth.ingestion.synthetic",
            method=SYNTHETIC_MARKER,
            stage="ingestion",
            parameters={
                "seed": self.seed,
                "n_factors": self.n_factors,
                "noise_sd": self.noise_sd,
                "indicator": request.indicator.value,
            },
            notes=(
                "SIMULATED DATA. Generated for pipeline development and testing only; "
                "carries no information about any real project."
            ),
        )

    def _factor_loadings(self, unit_id: str) -> np.ndarray:
        rng = np.random.default_rng(abs(hash((self.seed, unit_id))) % (2**32))
        return rng.dirichlet(np.ones(self.n_factors))

    def _common_factors(self, periods: np.ndarray) -> np.ndarray:
        rng = np.random.default_rng(self.seed)
        t = (periods - periods[0]) / max(len(periods) - 1, 1)
        factors = np.empty((self.n_factors, len(periods)))
        for k in range(self.n_factors):
            amplitude = 0.05 + 0.05 * rng.random()
            phase = 2 * np.pi * rng.random()
            trend = 0.10 * (rng.random() - 0.5)
            factors[k] = 0.55 + trend * t + amplitude * np.sin(2 * np.pi * (t + phase))
        return factors

    def fetch(self, request: ObservationRequest) -> TimeSeries:
        """Return a simulated indicator series for the requested area."""
        periods = np.arange(request.start_period, request.end_period + 1)
        loadings = self._factor_loadings(request.area.unit_id)
        values = loadings @ self._common_factors(periods)

        rng = np.random.default_rng(abs(hash((self.seed, request.area.unit_id, "noise"))) % (2**32))
        values = values + rng.normal(0.0, self.noise_sd, size=values.shape)

        if (
            self.treated_unit_id is not None
            and request.area.unit_id == self.treated_unit_id
            and self.treatment_period is not None
        ):
            values = values + self.true_effect * (periods >= self.treatment_period)

        if request.indicator in (Indicator.NDVI, Indicator.EVI, Indicator.TREE_COVER_FRACTION):
            values = np.clip(values, 0.0, 1.0)

        return TimeSeries(
            unit_id=request.area.unit_id,
            indicator=request.indicator,
            periods=tuple(int(p) for p in periods),
            values=tuple(float(v) for v in values),
            n_valid_observations=tuple(int(12 + (i % 5)) for i in range(len(periods))),
        )


class SyntheticCovariateProvider:
    """Deterministic matching covariates for simulated donor pools.

    **Simulated values.** Real covariates come from CHIRPS (rainfall), SRTM
    (elevation/slope), OSM (road access) and WorldPop (settlement pressure); see
    ``docs/04-data-sources.md``.
    """

    name = "synthetic"
    KEYS = ("rainfall_mm", "elevation_m", "slope_deg", "road_distance_km", "population_density")

    def __init__(self, seed: int = 20260101) -> None:
        self.seed = seed

    def covariates(self, area: AreaOfInterest) -> dict[str, float]:
        """Return simulated covariates, reusing any real attributes already set."""
        rng = np.random.default_rng(abs(hash((self.seed, area.unit_id, "cov"))) % (2**32))
        draws = {
            "rainfall_mm": float(600 + 500 * rng.random()),
            "elevation_m": float(300 + 900 * rng.random()),
            "slope_deg": float(1 + 14 * rng.random()),
            "road_distance_km": float(0.5 + 40 * rng.random()),
            "population_density": float(1 + 60 * rng.random()),
        }
        draws.update(area.attributes)
        return draws


class SyntheticDonorPoolProvider:
    """Generates a named pool of candidate donor regions."""

    name = "synthetic"

    def __init__(self, prefix: str = "donor") -> None:
        self.prefix = prefix

    def candidates(self, project: AreaOfInterest, n: int) -> list[AreaOfInterest]:
        """Return ``n`` synthetic donor areas around the project."""
        return [AreaOfInterest(unit_id=f"{self.prefix}-{i:03d}") for i in range(n)]


def is_synthetic(provenance: Provenance) -> bool:
    """True if a provenance record came from the synthetic simulator."""
    return provenance.method == SYNTHETIC_MARKER or SYNTHETIC_MARKER in (provenance.notes or "")
