"""Provider interfaces for Earth-observation and registry data.

Every concrete provider implements one of these protocols. The pipeline depends
only on the protocol, so swapping a synthetic fixture for Google Earth Engine is
a configuration change, not a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from groundtruth.core.provenance import Provenance
from groundtruth.core.types import Indicator, ProjectClaim, TimeSeries


@dataclass(frozen=True)
class AreaOfInterest:
    """A named spatial unit the pipeline can observe.

    ``geometry`` is deliberately loose (GeoJSON-like mapping) so the core package
    does not require GEOS/GDAL to be installed. The optional ``geo`` extra adds
    shapely/geopandas for real geometry work.
    """

    unit_id: str
    geometry: dict[str, object] | None = None
    centroid_lat: float | None = None
    centroid_lon: float | None = None
    area_ha: float | None = None
    attributes: dict[str, float] = field(default_factory=dict)

    @property
    def is_geometric(self) -> bool:
        """True if a real geometry (not just a centroid) is attached."""
        return self.geometry is not None


@dataclass(frozen=True)
class ObservationRequest:
    """A request for one indicator over one area across a period range."""

    area: AreaOfInterest
    indicator: Indicator
    start_period: int
    end_period: int
    max_cloud_fraction: float = 0.4

    def __post_init__(self) -> None:
        if self.end_period <= self.start_period:
            raise ValueError("end_period must be after start_period")


@runtime_checkable
class ObservationProvider(Protocol):
    """Source of multi-temporal indicator series for an area of interest."""

    name: str

    def provenance(self, request: ObservationRequest) -> Provenance:
        """Describe how this provider produced the series."""
        ...

    def fetch(self, request: ObservationRequest) -> TimeSeries:
        """Return the indicator series for the requested area and periods."""
        ...


@runtime_checkable
class CovariateProvider(Protocol):
    """Source of static/slow-moving covariates used for donor matching."""

    name: str

    def covariates(self, area: AreaOfInterest) -> dict[str, float]:
        """Return matching covariates (rainfall, elevation, slope, access, ...)."""
        ...


@runtime_checkable
class ClaimProvider(Protocol):
    """Source of registry-published project claims."""

    name: str

    def fetch_claim(self, case_id: str) -> ProjectClaim:
        """Return the registry claim for a case."""
        ...


@runtime_checkable
class DonorPoolProvider(Protocol):
    """Source of candidate control regions for a given project."""

    name: str

    def candidates(self, project: AreaOfInterest, n: int) -> list[AreaOfInterest]:
        """Return up to ``n`` candidate donor areas."""
        ...
