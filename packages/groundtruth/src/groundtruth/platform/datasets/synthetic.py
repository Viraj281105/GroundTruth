"""Deterministic fixture data generator.

**Owner: Bhumi** (it is a dataset service). **This generates simulated data.
It is not real Earth observation and must never back a published finding.**

Every series it produces is pinned to a dataset reference whose provider is
``synthetic`` and carries ``method='synthetic-simulation'`` in its provenance,
so the simulated flag reaches the evidence bundle, the API response and the UI
banner without anyone having to remember to set it.

Its purpose is to let the causal machinery, the platform and the demo be
developed and tested deterministically while real Earth-observation access is
being built.
"""

from __future__ import annotations

import hashlib

import numpy as np

from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.types import Indicator, TimeSeries

SYNTHETIC_MARKER = "synthetic-simulation"

SIMULATED_DATA_NOTE = (
    "SIMULATED DATA. Generated for pipeline development and testing only; carries no "
    "information about any real project."
)


def stable_seed(*parts: object) -> int:
    """Derive a reproducible 32-bit seed from arbitrary parts.

    Python salts string hashing per process, so ``hash()`` would make every run
    of the fixture different. Reproducibility is a requirement of this system,
    not a convenience, so the seed comes from a fixed digest.
    """
    payload = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=4).digest(), "big")


class SyntheticObservationProvider:
    """Deterministic simulator with a shared latent factor structure.

    Units are generated from a small number of common factors plus unit-specific
    noise, which is exactly the data-generating process synthetic control
    assumes. A designated treated unit can be given a known post-treatment
    effect, which makes it possible to test whether the estimator recovers the
    truth.
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

    def provenance_for(self, indicator: Indicator) -> Provenance:
        """Provenance that unambiguously flags the data as simulated."""
        return Provenance.computed(
            source="groundtruth.platform.datasets.synthetic",
            method=SYNTHETIC_MARKER,
            stage="ingestion",
            parameters={
                "seed": self.seed,
                "n_factors": self.n_factors,
                "noise_sd": self.noise_sd,
                "indicator": indicator.value,
            },
            notes=SIMULATED_DATA_NOTE,
        )

    def _factor_loadings(self, unit_id: str) -> np.ndarray:
        rng = np.random.default_rng(stable_seed(self.seed, unit_id))
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

    def fetch_series(
        self,
        *,
        unit_id: str,
        indicator: Indicator,
        start_period: int,
        end_period: int,
    ) -> TimeSeries:
        """Return a simulated indicator series for one unit."""
        if end_period <= start_period:
            raise ValueError("end_period must be after start_period")

        periods = np.arange(start_period, end_period + 1)
        values = self._factor_loadings(unit_id) @ self._common_factors(periods)

        rng = np.random.default_rng(stable_seed(self.seed, unit_id, "noise"))
        values = values + rng.normal(0.0, self.noise_sd, size=values.shape)

        if (
            self.treated_unit_id is not None
            and unit_id == self.treated_unit_id
            and self.treatment_period is not None
        ):
            values = values + self.true_effect * (periods >= self.treatment_period)

        if indicator in (Indicator.NDVI, Indicator.EVI, Indicator.TREE_COVER_FRACTION):
            values = np.clip(values, 0.0, 1.0)

        return TimeSeries(
            unit_id=unit_id,
            indicator=indicator,
            periods=tuple(int(p) for p in periods),
            values=tuple(float(v) for v in values),
            n_valid_observations=tuple(int(12 + (i % 5)) for i in range(len(periods))),
        )


class SyntheticCovariateProvider:
    """Deterministic matching covariates for simulated donor pools.

    **Simulated values.** Real covariates come from CHIRPS (rainfall), SRTM
    (elevation and slope), OSM (road access) and WorldPop (settlement
    pressure); see ``docs/data/sources.md``.
    """

    name = "synthetic"

    CENTRES: dict[str, float] = {
        "rainfall_mm": 850.0,
        "elevation_m": 750.0,
        "slope_deg": 8.0,
        "road_distance_km": 20.0,
        "population_density": 30.0,
    }
    SPREADS: dict[str, float] = {
        "rainfall_mm": 120.0,
        "elevation_m": 180.0,
        "slope_deg": 2.5,
        "road_distance_km": 7.0,
        "population_density": 10.0,
    }

    def __init__(self, seed: int = 20260101, project_unit_id: str | None = None) -> None:
        self.seed = seed
        self.project_unit_id = project_unit_id

    def covariates_for(
        self, unit_id: str, attributes: dict[str, float] | None = None
    ) -> dict[str, float]:
        """Return simulated covariates, reusing any real attributes already set.

        Candidates are drawn around a common ecoregion centre rather than
        uniformly at random, which is what a real donor search restricted to a
        matched ecoregion produces. A uniform draw would make every pool fail
        its balance check for reasons that have nothing to do with the method.

        The designated project unit sits exactly at the centre. That is a
        fixture convenience, not a claim about real projects: it gives the
        balance gate a pool it can actually pass, so tests can exercise the
        path where every gate succeeds as well as the paths where one fails.
        """
        if self.project_unit_id is not None and unit_id == self.project_unit_id:
            draws = dict(self.CENTRES)
        else:
            rng = np.random.default_rng(stable_seed(self.seed, unit_id, "cov"))
            draws = {
                key: float(centre + self.SPREADS[key] * rng.normal())
                for key, centre in self.CENTRES.items()
            }
        draws.update(attributes or {})
        return draws


class SyntheticDonorPoolProvider:
    """Generates a named pool of candidate donor regions."""

    name = "synthetic"

    def __init__(self, prefix: str = "donor") -> None:
        self.prefix = prefix

    def candidate_ids(self, n: int) -> list[str]:
        """Return ``n`` synthetic donor unit identifiers."""
        return [f"{self.prefix}-{i:03d}" for i in range(n)]


def is_synthetic(provenance: Provenance) -> bool:
    """True if a provenance record came from the synthetic simulator."""
    return provenance.method == SYNTHETIC_MARKER or SYNTHETIC_MARKER in (provenance.notes or "")
