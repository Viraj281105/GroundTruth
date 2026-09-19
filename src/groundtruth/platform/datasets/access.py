"""DataAccess implementations: the platform side of the engine's ports.

**Owner: Bhumi.**

This module is where dataset choice, version pinning, credentials, caching and
retries live. The engine states what it needs through
:mod:`groundtruth.contracts.ports`; this module decides where it comes from.

Two bundles are provided today:

- :func:`synthetic_access` — deterministic fixtures for offline development,
  CI and the demo. Every series it returns is pinned to a dataset reference
  whose provider is ``synthetic``, which propagates into the result's
  ``is_simulated`` flag and from there into the UI banner.
- :func:`earth_engine_access` — the real path. Not implemented; it raises
  rather than falling back to fixtures, because a silent fallback would let
  simulated numbers be published under a real-data label.
"""

from __future__ import annotations

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.ports import DataAccess, ObservationSpec
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import AnalysisRequest, UnitRef
from groundtruth.contracts.types import Indicator, TimeSeries
from groundtruth.platform.datasets.synthetic import (
    SyntheticCovariateProvider,
    SyntheticDonorPoolProvider,
    SyntheticObservationProvider,
)

SYNTHETIC_OBSERVATION_DATASET = DatasetRef(
    dataset_id="synthetic-latent-factor",
    version="1.0",
    provider="synthetic",
    source_uri=None,
)

SYNTHETIC_COVARIATE_DATASET = DatasetRef(
    dataset_id="synthetic-covariates",
    version="1.0",
    provider="synthetic",
)


class SyntheticObservationAccess:
    """Observation port backed by the deterministic fixture simulator.

    **Returns simulated data.** Pinned to a dataset reference whose provider is
    ``synthetic``, so the result carries ``is_simulated=True`` and the UI shows
    its banner without anyone having to remember to set a flag.
    """

    def __init__(
        self,
        *,
        seed: int = 20260101,
        treated_unit_id: str | None = None,
        true_effect: float = 0.0,
        treatment_period: int | None = None,
    ) -> None:
        self._provider = SyntheticObservationProvider(
            seed=seed,
            treated_unit_id=treated_unit_id,
            true_effect=true_effect,
            treatment_period=treatment_period,
        )

    def series(self, spec: ObservationSpec) -> TimeSeries:
        """Return a simulated indicator series for the requested unit."""
        return self._provider.fetch_series(
            unit_id=spec.unit.unit_id,
            indicator=spec.indicator,
            start_period=spec.start_period,
            end_period=spec.end_period,
        )

    def dataset(self, indicator: Indicator) -> DatasetRef:
        """Return the pinned dataset backing this indicator."""
        return SYNTHETIC_OBSERVATION_DATASET

    def provenance(self, spec: ObservationSpec) -> Provenance:
        """Provenance that unambiguously marks the data as simulated."""
        return self._provider.provenance_for(spec.indicator)


class SyntheticCovariateAccess:
    """Covariate port backed by the fixture generator. **Simulated values.**"""

    def __init__(self, *, seed: int = 20260101, project_unit_id: str | None = None) -> None:
        self._provider = SyntheticCovariateProvider(seed=seed, project_unit_id=project_unit_id)

    def covariates(self, unit: UnitRef, keys: tuple[str, ...]) -> dict[str, float]:
        """Return simulated covariates, restricted to the requested keys."""
        values = self._provider.covariates_for(unit.unit_id, dict(unit.attributes))
        return {k: values[k] for k in keys if k in values}

    def dataset(self, key: str) -> DatasetRef:
        """Return the pinned dataset backing one covariate."""
        return SYNTHETIC_COVARIATE_DATASET


class SyntheticDonorAccess:
    """Donor-candidate port backed by the fixture generator."""

    def __init__(self, prefix: str = "donor") -> None:
        self._provider = SyntheticDonorPoolProvider(prefix=prefix)

    def candidates(self, request: AnalysisRequest) -> list[UnitRef]:
        """Return synthetic donor candidates for a request."""
        return [
            UnitRef(unit_id=uid) for uid in self._provider.candidate_ids(request.donors.pool_size)
        ]


def synthetic_access(
    request: AnalysisRequest,
    *,
    true_effect: float = 0.0,
) -> DataAccess:
    """Build a complete simulated DataAccess bundle for a request.

    Args:
        request: The analysis request the bundle will serve.
        true_effect: Effect injected into the simulated treated unit, so the
            estimator's ability to recover a known value can be exercised.
    """
    return DataAccess(
        observations=SyntheticObservationAccess(
            seed=request.seed,
            treated_unit_id=request.project.unit_id,
            true_effect=true_effect,
            treatment_period=request.window.post_start,
        ),
        covariates=SyntheticCovariateAccess(
            seed=request.seed, project_unit_id=request.project.unit_id
        ),
        donors=SyntheticDonorAccess(),
    )


def earth_engine_access(request: AnalysisRequest) -> DataAccess:
    """Build a real, Earth Engine-backed DataAccess bundle. NOT IMPLEMENTED.

    Raises:
        DataUnavailableError: always, until the reducer chain lands.

    This deliberately raises rather than returning fixtures. A silent fallback
    would let simulated numbers be served under ``data_mode='observed'``, which
    is the one failure mode this system must not have.
    """
    raise DataUnavailableError(
        "Observed-data access is not implemented: the Earth Engine reducer chain has not "
        "landed. See docs/10-roadmap.md milestone M1 and issue #1."
    )
