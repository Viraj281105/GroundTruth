"""The Earth Engine observation service: the platform's ``ObservationAccess``.

**Owner: Bhumi** (#22).

The engine asks for one indicator series over one unit
(:class:`~groundtruth.contracts.ports.ObservationSpec`). This service answers it
year by year:

1. check the request against what was agreed (the C3 sensor, the engine's spec);
2. look the year up in the cache, keyed on the pinned dataset, the geometry, the
   year and the reduction spec;
3. on a miss: sign in once per process, list the scenes that pass the snapshot
   filter, reduce them, and store the result;
4. return a :class:`~groundtruth.contracts.types.TimeSeries` with
   ``n_valid_observations`` for every year.

Every failure raises. A year Earth Engine cannot serve is a
:class:`DataUnavailableError`; missing or rejected credentials are a
:class:`ConfigurationError`. Nothing on this path imports, calls or falls back to
the synthetic provider: an observed series is real or it is absent.

A year with no clear pixel is returned as NaN with zero observations — reported,
not filled — and the engine's alignment check refuses it, as it should.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import SecretStr

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.contracts.identifiers import DatasetRef, spec_hash
from groundtruth.contracts.ports import ObservationSpec
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.types import Indicator, TimeSeries
from groundtruth.engine import describe_engine
from groundtruth.logging import get_logger
from groundtruth.platform.datasets.cache import ReductionCache, cache_key
from groundtruth.platform.datasets.catalog import (
    AGREED_SENSORS,
    CLOUD_FILTER_DECISION,
    SNAPSHOT_DATE,
    SNAPSHOT_MICROS,
    pinned_dataset,
)
from groundtruth.platform.datasets.earthengine import (
    CRS,
    TILE_SCALE,
    EarthEngineApiBackend,
    EarthEngineBackend,
    YearQuery,
)
from groundtruth.platform.datasets.resilience import RateLimiter, RetryPolicy
from groundtruth.platform.datasets.session import EarthEngineSession
from groundtruth.platform.metrics import record_cache

logger = get_logger("datasets.earthengine")

SUPPORTED_COMPOSITE = "annual-median"


@dataclass(frozen=True)
class YearRecord:
    """One reduced year, as cached and as recorded in provenance."""

    value: float
    n_valid_observations: int
    clear_pixel_fraction: float
    n_scenes: int
    n_zone_pixels: int | None
    scene_fingerprint: str
    retrieved_at: str
    cache_hit: bool = False

    def as_cached(self) -> dict[str, Any]:
        """JSON-safe form. NaN is stored as null, so the file stays standard JSON."""
        record = asdict(self)
        record.pop("cache_hit")
        record["value"] = None if math.isnan(self.value) else self.value
        return record

    @classmethod
    def from_cached(cls, stored: Mapping[str, Any]) -> YearRecord:
        value = stored.get("value")
        return cls(
            value=float("nan") if value is None else float(value),
            n_valid_observations=int(stored["n_valid_observations"]),
            clear_pixel_fraction=float(stored["clear_pixel_fraction"]),
            n_scenes=int(stored["n_scenes"]),
            n_zone_pixels=(
                None if stored.get("n_zone_pixels") is None else int(stored["n_zone_pixels"])
            ),
            scene_fingerprint=str(stored["scene_fingerprint"]),
            retrieved_at=str(stored["retrieved_at"]),
            cache_hit=True,
        )


def geometry_fingerprint(geometry: Mapping[str, Any]) -> str:
    """Stable hash of a GeoJSON geometry (key order does not matter)."""
    return spec_hash(dict(geometry))


def scene_fingerprint(ids: list[str], versions: list[Any]) -> str:
    """Hash of the scenes a year used and the version of each."""
    pairs = sorted(zip((str(i) for i in ids), (str(v) for v in versions), strict=True))
    return spec_hash(pairs)


def histogram_median(counts: Mapping[int, int]) -> int:
    """``int(numpy.median(values))`` for values given as a histogram, exactly.

    Matches the engine's reference (``int(np.median(clear_counts[zone]))``): for an
    even number of pixels the two middle values are averaged, then truncated.
    """
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("an empty histogram has no median")
    ordered = sorted(counts.items())

    def nth(n: int) -> int:
        seen = 0
        for value, count in ordered:
            seen += count
            if n < seen:
                return value
        raise IndexError(n)  # pragma: no cover - n < total by construction

    if total % 2:
        return nth(total // 2)
    return int((nth(total // 2 - 1) + nth(total // 2)) / 2)


class EarthEngineObservationAccess:
    """``ObservationAccess`` over Google Earth Engine.

    Args:
        sensor: The sensor to reduce. Required, and must be one agreed under C3
            (:data:`~groundtruth.platform.datasets.catalog.AGREED_SENSORS`).
        credentials: ``GEE_SERVICE_ACCOUNT_JSON``: a key file path or key JSON.
        project: The Google Cloud project; defaults to the key's ``project_id``.
        cache: Where reduced years are cached; ``None`` disables caching.
        backend: The Earth Engine client. Defaults to the real one.
        reduction: The engine's published reduction (``describe_engine()["reduction"]``).
        rate_limiter: Shared request budget; ``None`` means unlimited.
        retry_policy: Per-call retries for transient failures.
        session: A session shared with other Earth Engine services. When given, it
            replaces ``credentials``, ``project``, ``rate_limiter`` and
            ``retry_policy``, and ``backend`` must be the backend it signed in.
    """

    def __init__(
        self,
        *,
        sensor: str | None,
        credentials: SecretStr | None = None,
        project: str | None = None,
        cache: ReductionCache | None = None,
        backend: EarthEngineBackend | None = None,
        reduction: Mapping[str, Any] | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        session: EarthEngineSession | None = None,
    ) -> None:
        agreed = ", ".join(a.describe() for a in AGREED_SENSORS.values())
        if sensor is None:
            raise ConfigurationError(
                "EARTH_ENGINE_SENSOR is not set. There is no default: which sensor serves "
                f"which year is methodology. Agreed sensors: {agreed}."
            )
        if sensor not in AGREED_SENSORS:
            raise ConfigurationError(
                f"sensor {sensor!r} has not been agreed under coordination point C3. "
                f"Agreed sensors: {agreed}."
            )
        self.sensor = sensor
        self.agreement = AGREED_SENSORS[sensor]
        self._cache = cache
        self._backend: EarthEngineBackend = backend or EarthEngineApiBackend()
        self._reduction = reduction if reduction is not None else describe_engine()["reduction"]
        self._session = session or EarthEngineSession(
            credentials=credentials,
            project=project,
            backend=self._backend,
            rate_limiter=rate_limiter,
            retry_policy=retry_policy,
            sleep=sleep,
        )
        self._now = now
        self._records: dict[tuple[str, ...], dict[int, YearRecord]] = {}

    # --- the port ---------------------------------------------------------

    def dataset(self, indicator: Indicator) -> DatasetRef:
        """The pinned dataset this service reduces for ``indicator``."""
        return pinned_dataset(self.sensor, self._spec_for(indicator)["collection"])

    def series(self, spec: ObservationSpec) -> TimeSeries:
        """The indicator series for one unit, one value per calendar year.

        Raises:
            DataUnavailableError: if the request cannot be served as agreed, or
                Earth Engine fails for any year.
            ConfigurationError: if credentials are missing or rejected.
        """
        reduction = self._spec_for(spec.indicator)
        geometry = self._check(spec, reduction)
        ref = pinned_dataset(self.sensor, reduction["collection"])
        geometry_hash = geometry_fingerprint(geometry)

        years = tuple(range(spec.start_period, spec.end_period + 1))
        records = {
            year: self._year(ref, reduction, geometry, geometry_hash, year) for year in years
        }
        self._records[self._record_key(spec, geometry_hash)] = records
        hits = sum(r.cache_hit for r in records.values())
        logger.info(
            "observed series reduced",
            extra={
                "unit_id": spec.unit.unit_id,
                "dataset": str(ref),
                "years": len(years),
                "cache_hits": hits,
            },
        )
        return TimeSeries(
            unit_id=spec.unit.unit_id,
            indicator=spec.indicator,
            periods=years,
            values=tuple(records[y].value for y in years),
            n_valid_observations=tuple(records[y].n_valid_observations for y in years),
        )

    def provenance(self, spec: ObservationSpec) -> Provenance:
        """How the series was produced: dataset, snapshot, C3 decisions, spec, per-year scenes."""
        reduction = self._spec_for(spec.indicator)
        ref = pinned_dataset(self.sensor, reduction["collection"])
        geometry = spec.unit.geometry
        geometry_hash = geometry_fingerprint(geometry) if geometry is not None else None
        records = (
            self._records.get(self._record_key(spec, geometry_hash)) if geometry_hash else None
        )
        parameters: dict[str, Any] = {
            "dataset": str(ref),
            "asset": ref.asset,
            "snapshot_date": SNAPSHOT_DATE,
            "snapshot_filter": f"system:version <= {SNAPSHOT_MICROS} ({SNAPSHOT_DATE}T00:00Z)",
            "sensor_selection": self.agreement.describe(),
            "cloud_filter": CLOUD_FILTER_DECISION,
            "requested_max_cloud_fraction": spec.max_cloud_fraction,
            "reduction": dict(reduction),
            "crs": CRS,
            "scale_m": reduction["scale_m"],
            "tile_scale": TILE_SCALE,
            "unit_id": spec.unit.unit_id,
            "geometry_blake2b": geometry_hash,
        }
        if records:
            parameters["years"] = {
                str(year): {
                    "n_scenes": r.n_scenes,
                    "scene_fingerprint": r.scene_fingerprint,
                    "n_valid_observations": r.n_valid_observations,
                    "clear_pixel_fraction": r.clear_pixel_fraction,
                    "n_zone_pixels": r.n_zone_pixels,
                    "retrieved_at": r.retrieved_at,
                    "cache_hit": r.cache_hit,
                }
                for year, r in sorted(records.items())
            }
        provenance = Provenance.computed(
            source=f"{ref.asset} via Google Earth Engine ({ref})",
            method=f"{reduction['composite']}/{reduction['zonal_value']}",
            stage="ingestion",
            parameters=parameters,
            notes=(
                f"Sensor: {self.agreement.describe()}. {CLOUD_FILTER_DECISION} Scenes written "
                f"after {SNAPSHOT_DATE} are excluded. A year with no clear pixel is reported "
                "as NaN with zero observations, never filled."
            ),
        )
        return provenance.model_copy(update={"source_uri": ref.source_uri})

    # --- request checks ---------------------------------------------------

    def _spec_for(self, indicator: Indicator) -> Mapping[str, Any]:
        for candidate in self._reduction.get("specs", ()):
            if candidate["sensor"] == self.sensor and candidate["indicator"] == indicator.value:
                found: Mapping[str, Any] = candidate
                return found
        raise DataUnavailableError(
            f"the engine's reduction spec has no {indicator.value!r} reduction for "
            f"{self.sensor}; this service reduces spectral indices only"
        )

    def _check(self, spec: ObservationSpec, reduction: Mapping[str, Any]) -> Mapping[str, Any]:
        """Everything that can be refused before any network call or credential read."""
        if spec.composite != SUPPORTED_COMPOSITE:
            raise DataUnavailableError(
                f"composite {spec.composite!r} is not served; the engine's reduction is "
                f"{reduction['composite']!r} ({SUPPORTED_COMPOSITE!r})"
            )
        if spec.buffer_m:
            raise DataUnavailableError(
                "an inward buffer is applied when the unit is constructed (ADR-011, #23), "
                f"not by the observation service; got buffer_m={spec.buffer_m}"
            )
        if spec.unit.geometry is None:
            raise DataUnavailableError(
                f"unit {spec.unit.unit_id!r} has no geometry, so there is nothing to observe"
            )
        if spec.end_period <= spec.start_period:
            raise DataUnavailableError(
                f"period range {spec.start_period}-{spec.end_period} is not a series; it needs "
                "at least two years"
            )
        first, last = reduction["years"]
        outside = [
            year
            for year in range(spec.start_period, spec.end_period + 1)
            if not self.agreement.covers(year) or year < first or (last is not None and year > last)
        ]
        if outside:
            raise DataUnavailableError(
                f"years {outside} are outside what was agreed ({self.agreement.describe()}) "
                f"or outside the {self.sensor} archive in the engine's spec ({first}-{last}); "
                "no other sensor is substituted"
            )
        return spec.unit.geometry

    @staticmethod
    def _record_key(spec: ObservationSpec, geometry_hash: str | None) -> tuple[str, ...]:
        return (
            spec.unit.unit_id,
            str(geometry_hash),
            spec.indicator.value,
            str(spec.start_period),
            str(spec.end_period),
        )

    # --- one year ---------------------------------------------------------

    def _year(
        self,
        ref: DatasetRef,
        reduction: Mapping[str, Any],
        geometry: Mapping[str, Any],
        geometry_hash: str,
        year: int,
    ) -> YearRecord:
        key = cache_key(
            dataset=ref.model_dump(mode="json", exclude={"retrieved_at"}),
            geometry_blake2b=geometry_hash,
            year=year,
            reduction=dict(reduction),
            crs=CRS,
        )
        if self._cache is not None:
            stored = self._cache.get(key)
            if stored is not None:
                try:
                    record = YearRecord.from_cached(stored)
                except (KeyError, TypeError, ValueError):
                    logger.warning("cache entry has an unexpected shape; treated as a miss")
                else:
                    record_cache("reduction", hit=True)
                    return record
            record_cache("reduction", hit=False)

        query = YearQuery(
            collection=str(reduction["collection"]),
            year=year,
            geometry=geometry,
            reduction=reduction,
            snapshot_micros=SNAPSHOT_MICROS,
            scale_m=int(reduction["scale_m"]),
        )
        listing = self._session.call(
            f"scene listing for {year}", lambda: self._backend.list_scenes(query)
        )
        ids = list(listing.get("ids") or [])
        versions = list(listing.get("versions") or [])
        n_available = int(listing.get("n_available") or 0)
        if len(ids) != len(versions):
            raise DataUnavailableError(
                f"Earth Engine returned {len(ids)} scene ids but {len(versions)} versions for "
                f"{year}; the listing cannot be fingerprinted"
            )
        retrieved_at = self._now().isoformat()

        if not ids:
            if n_available:
                raise DataUnavailableError(
                    f"{year}: all {n_available} {reduction['collection']} scenes over this unit "
                    f"were removed by the snapshot filter (system:version at or before "
                    f"{SNAPSHOT_DATE}). Earth Engine has rewritten them since the snapshot, "
                    "most likely by reprocessing the collection. Moving the snapshot date is a "
                    "new dataset version and changes spec_hash; it is never done automatically."
                )
            record = YearRecord(
                value=float("nan"),
                n_valid_observations=0,
                clear_pixel_fraction=0.0,
                n_scenes=0,
                n_zone_pixels=None,
                scene_fingerprint=scene_fingerprint([], []),
                retrieved_at=retrieved_at,
            )
        else:
            reduced = self._session.call(
                f"reduction for {year}", lambda: self._backend.reduce(query)
            )
            record = self._record(year, reduced, ids, versions, retrieved_at)

        if self._cache is not None:
            self._cache.put(key, record.as_cached())
        return record

    @staticmethod
    def _record(
        year: int,
        reduced: Mapping[str, Any],
        ids: list[str],
        versions: list[Any],
        retrieved_at: str,
    ) -> YearRecord:
        try:
            mean = (reduced.get("mean") or {}).get("index")
            raw = (reduced.get("histogram") or {}).get("count") or {}
            counts: dict[int, int] = {}
            for value, n in raw.items():
                counts[round(float(value))] = counts.get(round(float(value)), 0) + round(float(n))
        except (AttributeError, TypeError, ValueError):
            raise DataUnavailableError(
                f"Earth Engine returned an unreadable reduction for {year}: "
                f"{json.dumps(reduced, default=str)[:300]}"
            ) from None
        total = sum(counts.values())
        if total == 0:
            raise DataUnavailableError(
                f"{year}: the unit's geometry covers no pixel at the reduction scale"
            )
        clear = total - counts.get(0, 0)
        if (mean is None) != (clear == 0):
            raise DataUnavailableError(
                f"{year}: inconsistent reduction (mean {mean!r} with {clear} clear pixels); "
                "refusing to record it"
            )
        return YearRecord(
            value=float("nan") if mean is None else float(mean),
            n_valid_observations=histogram_median(counts),
            clear_pixel_fraction=clear / total,
            n_scenes=len(ids),
            n_zone_pixels=total,
            scene_fingerprint=scene_fingerprint(ids, versions),
            retrieved_at=retrieved_at,
        )


__all__ = [
    "EarthEngineObservationAccess",
    "YearRecord",
    "geometry_fingerprint",
    "histogram_median",
    "scene_fingerprint",
]
