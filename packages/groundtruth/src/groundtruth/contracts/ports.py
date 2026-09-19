"""Data-access ports: what the engine needs, and the platform supplies.

The contract runs in two directions:

1. ``AnalysisRequest`` in, ``AnalysisResult`` out — the main boundary.
2. These ports — the engine declares the data it needs; the platform decides
   where it comes from, how it is authenticated, cached, retried and pinned.

This is the seam that keeps *methodology* and *plumbing* apart. Which index to
compute, how to mask cloud, which covariates matter and how to derive them are
engine decisions. Credentials, rate limits, retries, caching, dataset version
pinning and job orchestration are platform decisions. Neither has to know how
the other does its job.

The engine must never open a socket, read a credential or touch the filesystem.
If it needs something, it asks a port.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import AnalysisRequest, UnitRef
from groundtruth.contracts.types import Indicator, TimeSeries


class ObservationSpec(BaseModel):
    """A request for one indicator series over one unit.

    Built by the engine from the analysis request. The platform fulfils it from
    whichever provider the pinned dataset names.
    """

    model_config = ConfigDict(frozen=True)

    unit: UnitRef
    indicator: Indicator
    start_period: int
    end_period: int
    max_cloud_fraction: float = Field(default=0.4, ge=0.0, le=1.0)
    composite: str = Field(default="annual-median", description="Temporal reduction to apply.")
    buffer_m: float = Field(
        default=0.0,
        ge=0.0,
        description="Inward boundary buffer, to avoid mixed edge pixels.",
    )

    def __post_init__(self) -> None:  # pragma: no cover - pydantic handles construction
        pass


@runtime_checkable
class ObservationAccess(Protocol):
    """Supplies indicator time series. Implemented by the platform."""

    def series(self, spec: ObservationSpec) -> TimeSeries:
        """Return the indicator series for one unit.

        Raises:
            DataUnavailableError: if the underlying product cannot be retrieved.
        """
        ...

    def dataset(self, indicator: Indicator) -> DatasetRef:
        """Return the pinned dataset backing this indicator."""
        ...

    def provenance(self, spec: ObservationSpec) -> Provenance:
        """Describe how the series was produced, for the audit trail."""
        ...


@runtime_checkable
class CovariateAccess(Protocol):
    """Supplies matching covariates. Implemented by the platform."""

    def covariates(self, unit: UnitRef, keys: tuple[str, ...]) -> dict[str, float]:
        """Return the requested covariates for one unit."""
        ...

    def dataset(self, key: str) -> DatasetRef:
        """Return the pinned dataset backing one covariate."""
        ...


@runtime_checkable
class DonorCandidateAccess(Protocol):
    """Supplies candidate control units. Implemented by the platform.

    Used only when ``request.donors.candidates`` is empty. When the platform has
    already resolved candidates, the engine uses those and never calls this.
    """

    def candidates(self, request: AnalysisRequest) -> list[UnitRef]:
        """Return candidate donor units for a request."""
        ...


class DataAccess(BaseModel):
    """The complete set of ports the engine may use.

    Passed to :func:`groundtruth.engine.run_analysis` as its second argument.
    Handed a bundle of fixtures in tests, and a bundle of real clients in
    production, with no change to the engine.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    observations: ObservationAccess
    covariates: CovariateAccess
    donors: DonorCandidateAccess | None = None
