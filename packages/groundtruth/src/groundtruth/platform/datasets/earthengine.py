"""Google Earth Engine: credentials, error handling, and the reduction as an EE graph.

**Owner: Bhumi** (#22). The methodology is Viraj's (#1): which bands, how digital
numbers become reflectance, which pixels are masked, how a year collapses to one
value. It arrives as plain data, one dict per (sensor, indicator), from
``describe_engine()["reduction"]`` (coordination point C3). This module only
translates that dict into Earth Engine calls; it chooses none of it.

The chain each year, as the spec states it:

1. scenes over the unit in the calendar year, written at or before the snapshot
   date (:mod:`~groundtruth.platform.datasets.catalog`);
2. reflectance ``DN x scale + offset``; a pixel with any band outside the valid
   range is masked;
3. the quality mask (SCL classes, or QA_PIXEL bits plus QA_RADSAT);
4. the index on each clear scene, masked where its denominator is ~0 (as the
   engine's ``_safe_ratio``), then the per-pixel median across the year;
5. the zone mean of those medians over pixels with a clear scene, and a histogram
   of per-pixel clear-scene counts, from which the service takes the median count
   and the clear-pixel fraction exactly.

Zonal reducers are ``unweighted`` so a pixel is in the zone or not, as in the
engine's numpy reference ``reduce_period``; the network test checks a small chip
against it.

**Credentials.** The key is read only when Earth Engine is first used. It never
appears in a log line, an exception message or a traceback: messages are written
here, external error text is redacted against the key before use, and every
translated exception is raised ``from None``.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import SecretStr

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.contracts.request import UnitRef
from groundtruth.platform.datasets.resilience import PermanentError, TransientError

COLLECTIONS: dict[str, str] = {
    "sentinel2": "COPERNICUS/S2_SR_HARMONIZED",
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
    "hansen": "UMD/hansen/global_forest_change_2023_v1_11",
}
"""Earth Engine assets referred to by name elsewhere (ADR-011). The observation
service takes its collections from the engine's reduction spec, not from here."""

CRS = "EPSG:4326"
"""Grid the zonal reduction runs on, at the spec's ``scale_m``. Named explicitly
so a re-run does not depend on Earth Engine's default for a composite."""

MAX_PIXELS = 10_000_000_000_000
"""Never let Earth Engine refuse a large unit for size; it times out instead, visibly."""

TILE_SCALE = 4
"""Splits the reduction into smaller tiles to stay under per-tile memory limits.
Changes memory use, never the result."""

DEADLINE_MS = 360_000
"""Client-side HTTP deadline: just over Earth Engine's own interactive limit."""

INSTALL_HINT = 'pip install -e "packages/groundtruth[earthengine]"'


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------

_PEM_BLOCK = re.compile(r"-----BEGIN[^-]*-----.*?-----END[^-]*-----", re.DOTALL)


class ServiceAccountKey:
    """A parsed service-account key whose secret parts cannot be printed.

    ``repr`` and ``str`` show only the project; :meth:`redact` removes every
    secret part of the key from a piece of external text.
    """

    __slots__ = ("_secrets", "_text", "client_email", "project_id")

    def __init__(self, info: Mapping[str, Any], text: str) -> None:
        self.client_email = str(info["client_email"])
        project = info.get("project_id")
        self.project_id = str(project) if project else None
        self._text = text
        private_key = str(info.get("private_key", ""))
        secrets = {text, private_key, private_key.replace("\n", "\\n"), self.client_email}
        for field in ("private_key_id", "client_id"):
            if info.get(field):
                secrets.add(str(info[field]))
        # Each line of the key body too, in case a message quotes part of it.
        secrets.update(line for line in private_key.splitlines() if len(line) >= 16)
        self._secrets = tuple(sorted((s for s in secrets if s), key=len, reverse=True))

    def __repr__(self) -> str:
        return f"ServiceAccountKey(project_id={self.project_id!r}, secret=<redacted>)"

    __str__ = __repr__

    def json_text(self) -> str:
        """The key JSON, for the Earth Engine client only."""
        return self._text

    def redact(self, text: str) -> str:
        """``text`` with every secret part of this key replaced."""
        for secret in self._secrets:
            text = text.replace(secret, "[redacted]")
        return _PEM_BLOCK.sub("[redacted]", text)


def load_service_account_key(value: SecretStr | None) -> ServiceAccountKey:
    """Parse ``GEE_SERVICE_ACCOUNT_JSON``: a path to a key file, or the key JSON itself.

    Raises:
        ConfigurationError: if it is unset, names no readable file, or is not a
            service-account key. No message repeats any part of the value, since
            a value that failed to parse may still be a key.
    """
    if value is None:
        raise ConfigurationError(
            "GEE_SERVICE_ACCOUNT_JSON is not set, so Earth Engine cannot be used. Set it to the "
            "path of a service-account key file (or to the key JSON). Observed data is never "
            "replaced by simulated data."
        )
    raw = value.get_secret_value().strip()
    if raw.startswith("{"):
        text = raw
    else:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ConfigurationError(
                "GEE_SERVICE_ACCOUNT_JSON does not name a readable file, and is not key JSON. "
                "Set it to the full path of the downloaded key file."
            )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            raise ConfigurationError(
                "the file GEE_SERVICE_ACCOUNT_JSON names could not be read as UTF-8 text"
            ) from None
    try:
        info = json.loads(text)
    except ValueError:
        raise ConfigurationError(
            "GEE_SERVICE_ACCOUNT_JSON is not valid JSON; expected a service-account key"
        ) from None
    if (
        not isinstance(info, dict)
        or info.get("type") != "service_account"
        or not info.get("client_email")
        or not info.get("private_key")
    ):
        raise ConfigurationError(
            "GEE_SERVICE_ACCOUNT_JSON is JSON but not a service-account key (it needs "
            '"type": "service_account", a client_email and a private_key)'
        )
    return ServiceAccountKey(info, text)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

_PERMANENT_MARKERS = (
    "computation timed out",
    "user memory limit exceeded",
    "too many pixels",
    "not found",
    "does not exist",
    "permission",
    "not authorized",
    "unauthorized",
    "forbidden",
    "invalid geometry",
    "geometry is invalid",
    "invalid argument",
    "not initialized",
)
_TRANSIENT_MARKERS = (
    "too many concurrent",
    "too many requests",
    "rate limit",
    "quota exceeded",
    "capacity exceeded",
    "service unavailable",
    "temporarily unavailable",
    "internal error",
    "backend error",
    "deadline exceeded",
    "timed out",
    "connection reset",
    "connection aborted",
    "connection refused",
)
_TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_MAX_REASON_CHARS = 400


def _http_status(exc: BaseException) -> int | None:
    for candidate in (
        getattr(getattr(exc, "resp", None), "status", None),
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
    ):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def classify(
    exc: BaseException, key: ServiceAccountKey | None = None
) -> TransientError | PermanentError:
    """Translate an Earth Engine or transport error into a retry decision.

    Permanent markers win over transient ones ("Computation timed out" repeats on
    retry; a dropped connection does not). Anything unrecognised is permanent: the
    job layer still retries a whole attempt later, so an unknown error is retried
    once more in minutes rather than hammered here in seconds.
    """
    message = str(exc)
    if key is not None:
        message = key.redact(message)
    reason = f"{type(exc).__name__}: {message}"[:_MAX_REASON_CHARS]
    lowered = message.lower()
    status = _http_status(exc)

    if any(marker in lowered for marker in _PERMANENT_MARKERS):
        return PermanentError(reason)
    if status in _TRANSIENT_STATUS:
        return TransientError(reason)
    if status is not None and 400 <= status < 500:
        return PermanentError(reason)
    if isinstance(exc, ConnectionError | TimeoutError):
        return TransientError(reason)
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return TransientError(reason)
    if any(marker in lowered for marker in _TRANSIENT_MARKERS):
        return TransientError(reason)
    return PermanentError(reason)


# --------------------------------------------------------------------------
# The backend: the only code that talks to Earth Engine
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class YearQuery:
    """One unit, one calendar year, one reduction spec."""

    collection: str
    year: int
    geometry: Mapping[str, Any]
    reduction: Mapping[str, Any]
    snapshot_micros: int
    scale_m: int
    crs: str = CRS


class EarthEngineBackend(Protocol):
    """What the observation service needs from Earth Engine. Faked in tests."""

    def initialize(self, key: ServiceAccountKey, project: str) -> None:
        """Authenticate this process."""
        ...

    def list_scenes(self, query: YearQuery) -> dict[str, Any]:
        """``{"n_available": int, "ids": [...], "versions": [...]}``.

        ``n_available`` counts scenes before the snapshot filter; ``ids`` and
        ``versions`` describe the scenes that pass it.
        """
        ...

    def reduce(self, query: YearQuery) -> dict[str, Any]:
        """``{"mean": {"index": float | None}, "histogram": {"count": {str: n}}}``."""
        ...


def import_ee() -> Any:
    """The ``ee`` module, or a :class:`ConfigurationError` naming the extra to install."""
    try:
        return importlib.import_module("ee")
    except ImportError:
        raise ConfigurationError(
            f"the Earth Engine client is not installed: {INSTALL_HINT}"
        ) from None


def _quality_mask(ee: Any, image: Any, mask: Mapping[str, Any]) -> Any:
    if mask["type"] == "scl":
        scl = image.select(mask["band"])
        usable = ee.Image.constant(1)
        for value in mask["invalid_classes"]:
            usable = usable.And(scl.neq(int(value)))
        return usable
    if mask["type"] == "qa_pixel":
        bits = 0
        for bit in mask["invalid_bits"]:
            bits |= 1 << int(bit)
        usable = image.select(mask["band"]).bitwiseAnd(bits).eq(0)
        radsat = mask.get("radiometric_saturation_band")
        if radsat:
            usable = usable.And(image.select(radsat).eq(0))
        return usable
    raise PermanentError(f"the reduction spec names an unknown mask type {mask['type']!r}")


def _index(ee: Any, indicator: str, rho: Any) -> tuple[Any, Any, float]:
    """Numerator, denominator and gain for each index, as in ``engine/observation/indices.py``."""
    nir = rho.select("nir")
    if indicator == "ndvi":
        red = rho.select("red")
        return nir.subtract(red), nir.add(red), 1.0
    if indicator == "evi":
        red, blue = rho.select("red"), rho.select("blue")
        denominator = nir.add(red.multiply(6.0)).subtract(blue.multiply(7.5)).add(1.0)
        return nir.subtract(red), denominator, 2.5
    if indicator == "nbr":
        swir2 = rho.select("swir2")
        return nir.subtract(swir2), nir.add(swir2), 1.0
    raise PermanentError(f"no Earth Engine translation for indicator {indicator!r}")


def scene_index(ee: Any, image: Any, reduction: Mapping[str, Any]) -> Any:
    """One scene's index band, masked exactly where the reference chain yields NaN."""
    bands: Mapping[str, str] = reduction["bands"]
    roles = list(bands)
    reflectance = reduction["reflectance"]
    low, high = reflectance["valid_range"]
    rho = (
        image.select([bands[role] for role in roles], roles)
        .multiply(float(reflectance["scale"]))
        .add(float(reflectance["offset"]))
    )
    in_range = rho.gte(low).And(rho.lte(high)).reduce(ee.Reducer.allNonZero())
    numerator, denominator, gain = _index(ee, reduction["indicator"], rho)
    usable = in_range.And(_quality_mask(ee, image, reduction["mask"])).And(
        denominator.abs().gt(1e-12)
    )
    return numerator.divide(denominator).multiply(gain).updateMask(usable).rename("index")


class EarthEngineApiBackend:
    """The real backend, over the ``earthengine-api`` client."""

    def __init__(self) -> None:
        self._ee: Any = None

    @property
    def ee(self) -> Any:
        if self._ee is None:
            self._ee = import_ee()
        return self._ee

    def initialize(self, key: ServiceAccountKey, project: str) -> None:
        ee = self.ee
        credentials = ee.ServiceAccountCredentials(key.client_email, key_data=key.json_text())
        ee.Initialize(credentials, project=project)
        ee.data.setDeadline(DEADLINE_MS)

    def _scenes(self, query: YearQuery) -> tuple[Any, Any, Any]:
        ee = self.ee
        # Geodesic with the left-inside rule: the boundary artifacts are wound for it
        # (cases/boundaries/*.provenance.json), and a sliver where two parts of a
        # boundary overlap stays inside once rather than being cut out as even-odd
        # would. The geometry itself is passed as delivered, never repaired.
        region = ee.Geometry(dict(query.geometry), None, True, False)
        start = ee.Date.fromYMD(query.year, 1, 1)
        scenes = (
            ee.ImageCollection(query.collection)
            .filterBounds(region)
            .filterDate(start, start.advance(1, "year"))
        )
        pinned = scenes.filter(ee.Filter.lte("system:version", query.snapshot_micros))
        return region, scenes, pinned

    def list_scenes(self, query: YearQuery) -> dict[str, Any]:
        ee = self.ee
        _, scenes, pinned = self._scenes(query)
        listing: dict[str, Any] = ee.Dictionary(
            {
                "n_available": scenes.size(),
                "ids": pinned.aggregate_array("system:index"),
                "versions": pinned.aggregate_array("system:version"),
            }
        ).getInfo()
        return listing

    def reduce(self, query: YearQuery) -> dict[str, Any]:
        ee = self.ee
        region, _, pinned = self._scenes(query)
        reduction = query.reduction
        indexed = pinned.map(lambda image: scene_index(ee, ee.Image(image), reduction))
        median = indexed.median().rename("index")
        # A pixel no clear scene reached counts as zero, not as absent: the engine's
        # n_valid is the median over every pixel in the zone.
        counts = indexed.count().rename("count").unmask(0)
        common = {
            "geometry": region,
            "scale": query.scale_m,
            "crs": query.crs,
            "maxPixels": MAX_PIXELS,
            "tileScale": TILE_SCALE,
            "bestEffort": False,
        }
        result: dict[str, Any] = ee.Dictionary(
            {
                "mean": median.reduceRegion(reducer=ee.Reducer.mean().unweighted(), **common),
                "histogram": counts.reduceRegion(
                    reducer=ee.Reducer.frequencyHistogram().unweighted(), **common
                ),
            }
        ).getInfo()
        return result


class EarthEngineCovariateProvider:
    """Matching covariates from Earth Engine assets. NOT IMPLEMENTED.

    Planned assets: CHIRPS daily rainfall, SRTM elevation and derived slope,
    JRC Global Surface Water, WorldPop population density, and an OSM-derived
    distance-to-road raster. Which covariates and how they are derived is
    coordination point C4.
    """

    name = "google-earth-engine"

    def covariates(self, unit: UnitRef) -> dict[str, float]:
        """Fetch covariates for an area. NOT IMPLEMENTED."""
        raise DataUnavailableError(
            "EarthEngineCovariateProvider.covariates is not implemented yet; "
            "use SyntheticCovariateProvider for offline runs."
        )


__all__ = [
    "COLLECTIONS",
    "CRS",
    "EarthEngineApiBackend",
    "EarthEngineBackend",
    "EarthEngineCovariateProvider",
    "ServiceAccountKey",
    "YearQuery",
    "classify",
    "import_ee",
    "load_service_account_key",
    "scene_index",
]
