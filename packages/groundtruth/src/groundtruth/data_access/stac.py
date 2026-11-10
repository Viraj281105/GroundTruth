"""STAC search for Sentinel-2 / Landsat scenes, COG window retrieval, and lazy loading."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError

if TYPE_CHECKING:
    import numpy as np

DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"

COLLECTIONS: dict[str, str] = {
    "sentinel-2": "sentinel-2-l2a",
    "sentinel-2-l2a": "sentinel-2-l2a",
    "s2": "sentinel-2-l2a",
    "landsat": "landsat-c2-l2",
    "landsat-c2-l2": "landsat-c2-l2",
    "landsat-8": "landsat-c2-l2",
    "landsat-9": "landsat-c2-l2",
    "landsat-7": "landsat-c2-l2",
    "landsat-5": "landsat-c2-l2",
    "sentinel-1": "sentinel-1-rtc",
    "sentinel-1-rtc": "sentinel-1-rtc",
    "s1": "sentinel-1-rtc",
    "s1-rtc": "sentinel-1-rtc",
}

_ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "B02": ("B02", "B2", "blue", "SR_B2", "SR_B1"),
    "B03": ("B03", "B3", "green", "SR_B3", "SR_B2"),
    "B04": ("B04", "B4", "red", "SR_B4", "SR_B3"),
    "B08": ("B08", "B8", "nir", "nir08", "SR_B5", "SR_B4", "B8A"),
    "B11": ("B11", "swir1", "swir16", "SR_B6", "SR_B5"),
    "B12": ("B12", "swir2", "swir22", "SR_B7"),
    "SCL": ("SCL", "scl"),
    "blue": ("blue", "B02", "B2", "SR_B2", "SR_B1"),
    "green": ("green", "B03", "B3", "SR_B3", "SR_B2"),
    "red": ("red", "B04", "B4", "SR_B4", "SR_B3"),
    "nir": ("nir", "B08", "B8", "nir08", "SR_B5", "SR_B4", "B8A"),
    "nir08": ("nir08", "B08", "B8", "nir", "SR_B5", "SR_B4"),
    "swir1": ("swir1", "B11", "swir16", "SR_B6", "SR_B5"),
    "swir2": ("swir2", "B12", "swir22", "SR_B7"),
    "qa_pixel": ("qa_pixel", "QA_PIXEL"),
    "QA_PIXEL": ("QA_PIXEL", "qa_pixel"),
    "qa_radsat": ("qa_radsat", "QA_RADSAT"),
    "QA_RADSAT": ("QA_RADSAT", "qa_radsat"),
    "vv": ("vv", "VV"),
    "vh": ("vh", "VH"),
    "hh": ("hh", "HH"),
    "hv": ("hv", "HV"),
}


def resolve_collection_id(platform_or_collection: str) -> str:
    """Resolve a platform shorthand, alias, or full collection name to a STAC collection ID."""
    clean = platform_or_collection.lower().strip()
    if clean in COLLECTIONS:
        return COLLECTIONS[clean]
    known = set(COLLECTIONS.values())
    if clean in known:
        return clean
    raise ValueError(
        f"platform must be one of {sorted(COLLECTIONS)}, got {platform_or_collection!r}"
    )


def sign_asset_url(url: str) -> str:
    """Sign or re-sign a Planetary Computer asset URL, stripping expired SAS tokens."""
    if not url or not isinstance(url, str):
        return url
    lower = url.lower()
    if "planetarycomputer" not in lower and "blob.core.windows.net" not in lower:
        return url
    clean_url = url.split("?")[0]
    try:
        pc = importlib.import_module("planetary_computer")
        return str(pc.sign(clean_url))
    except Exception:
        return url


def _configure_proj_env() -> None:
    """Point PROJ_DATA and PROJ_LIB to rasterio/pyproj bundled data before GDAL initializes.

    Prevents host-level PostgreSQL/PostGIS PROJ installations with older database
    layouts from causing ``rasterio.errors.CRSError`` during coordinate transforms.
    """
    spec = importlib.util.find_spec("rasterio")
    if spec is not None and spec.origin is not None:
        rio_proj = Path(spec.origin).parent / "proj_data"
        if rio_proj.is_dir():
            os.environ["PROJ_DATA"] = str(rio_proj)
            os.environ["PROJ_LIB"] = str(rio_proj)
            return
    pyproj_spec = importlib.util.find_spec("pyproj")
    if pyproj_spec is not None and pyproj_spec.origin is not None:
        pyproj_dir = Path(pyproj_spec.origin).parent / "proj_dir" / "share" / "proj"
        if pyproj_dir.is_dir():
            os.environ["PROJ_DATA"] = str(pyproj_dir)
            os.environ["PROJ_LIB"] = str(pyproj_dir)


_configure_proj_env()


@dataclass(frozen=True)
class SceneDescriptor:
    """Minimal, typed description of one STAC item."""

    id: str
    collection: str
    datetime: str
    bbox: tuple[float, float, float, float]
    cloud_cover: float | None
    assets: tuple[str, ...]
    href: str | None = None
    sensor: str | None = None
    tile_id: str | None = None
    asset_hrefs: Mapping[str, str] = field(default_factory=dict)
    epsg: int | None = None
    processing_baseline: str | None = None
    geometry: dict[str, Any] | None = None


@dataclass(frozen=True)
class RasterGridSpec:
    """Canonical spatial grid for aligning multi-temporal scene chips over an AOI."""

    crs: str
    bounds: tuple[float, float, float, float]
    height: int
    width: int
    resolution_m: float
    wgs84_bounds: tuple[float, float, float, float]


def _require(module: str, package: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(f"'{package}' is required: pip install {package}") from exc


def _extract_linear_rings(geojson: Mapping[str, Any]) -> list[Sequence[Any]]:
    """Extract all linear rings from a Polygon, MultiPolygon, Feature, or FeatureCollection."""
    if not isinstance(geojson, Mapping):
        raise ValueError("GeoJSON must be a mapping")
    gtype = geojson.get("type")
    if gtype == "FeatureCollection":
        features = geojson.get("features")
        if not isinstance(features, Sequence) or isinstance(features, (str, bytes)) or not features:
            raise ValueError("FeatureCollection must contain a non-empty 'features' list")
        rings: list[Sequence[Any]] = []
        for feat in features:
            if not isinstance(feat, Mapping) or feat.get("type") != "Feature":
                raise ValueError("FeatureCollection elements must be GeoJSON Feature objects")
            rings.extend(_extract_linear_rings(feat))
        return rings
    if gtype == "Feature":
        geom = geojson.get("geometry")
        if not isinstance(geom, Mapping):
            raise ValueError("Feature must contain a non-null 'geometry' object")
        return _extract_linear_rings(geom)
    if gtype == "Polygon":
        coords = geojson.get("coordinates")
        if not isinstance(coords, Sequence) or isinstance(coords, (str, bytes)) or not coords:
            raise ValueError("Polygon must have non-empty 'coordinates'")
        return list(coords)
    if gtype == "MultiPolygon":
        coords = geojson.get("coordinates")
        if not isinstance(coords, Sequence) or isinstance(coords, (str, bytes)) or not coords:
            raise ValueError("MultiPolygon must have non-empty 'coordinates'")
        multi_rings: list[Sequence[Any]] = []
        for poly in coords:
            if not isinstance(poly, Sequence) or isinstance(poly, (str, bytes)) or not poly:
                raise ValueError("Each polygon in MultiPolygon must have non-empty rings")
            multi_rings.extend(poly)
        return multi_rings
    raise ValueError(f"Unsupported or missing GeoJSON type: {gtype!r}")


def validate_aoi_geojson(geojson: dict[str, Any]) -> tuple[float, float, float, float]:
    """Validate an AOI GeoJSON object and return its ``(min_lon, min_lat, max_lon, max_lat)`` bbox.

    Supports ``Polygon``, ``MultiPolygon``, ``Feature``, and ``FeatureCollection``.
    Checks non-empty coordinates, valid lon in ``[-180, 180]``, lat in ``[-90, 90]``,
    closed linear rings with at least 4 positions, and positive bounding-box area.
    """
    rings = _extract_linear_rings(geojson)
    if not rings:
        raise ValueError("AOI GeoJSON contains no linear rings")

    lons: list[float] = []
    lats: list[float] = []
    for ring in rings:
        if not isinstance(ring, Sequence) or isinstance(ring, (str, bytes)) or len(ring) < 4:
            raise ValueError("Each linear ring must contain at least 4 positions")
        parsed_ring: list[tuple[float, float]] = []
        for pos in ring:
            if (
                not isinstance(pos, Sequence)
                or isinstance(pos, (str, bytes))
                or len(pos) < 2
                or isinstance(pos[0], bool)
                or isinstance(pos[1], bool)
            ):
                raise ValueError(f"Invalid coordinate position: {pos!r}")
            lon = float(pos[0])
            lat = float(pos[1])
            if not (math.isfinite(lon) and math.isfinite(lat)):
                raise ValueError(f"Non-finite coordinates: {(lon, lat)!r}")
            if not (-180.0 <= lon <= 180.0):
                raise ValueError(f"Longitude {lon} out of bounds [-180, 180]")
            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude {lat} out of bounds [-90, 90]")
            parsed_ring.append((lon, lat))
            lons.append(lon)
            lats.append(lat)
        if parsed_ring[0] != parsed_ring[-1]:
            raise ValueError(
                f"Linear ring is not closed: start {parsed_ring[0]} != end {parsed_ring[-1]}"
            )

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ValueError(
            f"AOI bounding box has zero or negative area: {(min_lon, min_lat, max_lon, max_lat)}"
        )
    return (min_lon, min_lat, max_lon, max_lat)


def scene_from_item(item: Any) -> SceneDescriptor:
    """Convert a pystac Item (or any object with the same attributes)."""
    props = item.properties
    raw = [float(v) for v in item.bbox]
    if len(raw) != 4:
        raise ValueError(f"Item {item.id} has non-2D bbox: {item.bbox!r}")
    when = props.get("datetime") or props.get("start_datetime")
    if when is None:
        raise ValueError(f"Item {item.id} has no datetime")
    cloud = props.get("eo:cloud_cover")

    raw_platform = props.get("platform")
    raw_instruments = props.get("instruments")
    if raw_platform is not None:
        sensor: str | None = str(raw_platform)
    elif isinstance(raw_instruments, Sequence) and not isinstance(raw_instruments, (str, bytes)):
        sensor = "/".join(str(x) for x in raw_instruments) if raw_instruments else None
    elif raw_instruments is not None:
        sensor = str(raw_instruments)
    else:
        sensor = None

    mgrs_tile = props.get("s2:mgrs_tile")
    wrs_path = props.get("landsat:wrs_path")
    wrs_row = props.get("landsat:wrs_row")
    if mgrs_tile is not None:
        tile_id: str | None = str(mgrs_tile)
    elif wrs_path is not None and wrs_row is not None:
        tile_id = f"{wrs_path}/{wrs_row}"
    elif wrs_path is not None:
        tile_id = str(wrs_path)
    else:
        tile_id = None

    asset_hrefs: dict[str, str] = {}
    if isinstance(item.assets, Mapping):
        for k, asset_obj in item.assets.items():
            href_val = getattr(asset_obj, "href", None)
            if href_val is None and isinstance(asset_obj, Mapping):
                href_val = asset_obj.get("href")
            if isinstance(href_val, str) and href_val.strip():
                asset_hrefs[str(k)] = href_val

    epsg: int | None = None
    raw_epsg = props.get("proj:epsg")
    if raw_epsg is not None:
        try:
            epsg = int(raw_epsg)
        except (TypeError, ValueError):
            epsg = None
    elif isinstance(props.get("proj:code"), str):
        code_str = str(props["proj:code"])
        if code_str.upper().startswith("EPSG:"):
            try:
                epsg = int(code_str.split(":", 1)[1])
            except ValueError:
                epsg = None

    raw_baseline = props.get("s2:processing_baseline")
    processing_baseline = str(raw_baseline) if raw_baseline is not None else None

    raw_geom = getattr(item, "geometry", None)
    geometry = dict(raw_geom) if isinstance(raw_geom, Mapping) else None

    return SceneDescriptor(
        id=str(item.id),
        collection=str(item.collection_id),
        datetime=str(when),
        bbox=(raw[0], raw[1], raw[2], raw[3]),
        cloud_cover=None if cloud is None else float(cloud),
        assets=tuple(sorted(item.assets)),
        href=item.get_self_href(),
        sensor=sensor,
        tile_id=tile_id,
        asset_hrefs=asset_hrefs,
        epsg=epsg,
        processing_baseline=processing_baseline,
        geometry=geometry,
    )


def _classify_stac_exception(exc: Exception, context: str) -> GroundTruthStacError:
    msg = str(exc)
    low = msg.lower()
    auth_tokens = ("401", "403", "unauthorized", "forbidden", "credential", "sas")
    if any(code in low for code in auth_tokens):
        return ConfigurationError(
            f"{context} failed due to invalid credentials or access denied: {msg}"
        )
    return DataUnavailableError(f"{context} failed: {msg}")


GroundTruthStacError = ConfigurationError | DataUnavailableError


def open_stac_client(
    catalog_url: str = DEFAULT_STAC_URL,
    *,
    sign_planetary_computer: bool = True,
    timeout: float | tuple[float, float] = 30.0,
    max_retries: int = 5,
    backoff_factor: float = 1.0,
) -> Any:
    """Open a real STAC API client with automatic SAS signing for Planetary Computer.

    Supports configurable timeouts, automatic retries with exponential backoff,
    and HTTP 429 rate-limit handling via urllib3.

    Raises:
        ConfigurationError: if ``catalog_url`` is malformed or credentials are rejected.
        DataUnavailableError: if the STAC endpoint is unreachable or returns an API error.
    """
    if not catalog_url or not isinstance(catalog_url, str) or not catalog_url.strip():
        raise ConfigurationError("catalog_url must be a non-empty URL string")
    parsed = urlparse(catalog_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigurationError(f"Invalid STAC catalog_url {catalog_url!r}; must be http(s)://...")

    pystac_client = _require("pystac_client", "pystac-client")
    modifier: Any = None
    if sign_planetary_computer and "planetarycomputer.microsoft.com" in parsed.netloc.lower():
        try:
            pc = importlib.import_module("planetary_computer")
            modifier = pc.sign_inplace
        except ImportError:
            modifier = None

    try:
        from urllib3.util.retry import Retry

        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        stac_io = pystac_client.stac_api_io.StacApiIO(
            timeout=timeout,
            max_retries=retry_strategy,
        )
        if modifier is not None:
            return pystac_client.Client.open(
                catalog_url, modifier=modifier, stac_io=stac_io, timeout=timeout
            )
        return pystac_client.Client.open(catalog_url, stac_io=stac_io, timeout=timeout)
    except (ConfigurationError, DataUnavailableError):
        raise
    except Exception as exc:
        raise _classify_stac_exception(exc, f"Opening STAC catalog {catalog_url!r}") from exc


def check_catalog_connectivity(
    catalog_url: str = DEFAULT_STAC_URL,
    *,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Test STAC catalog connectivity and return catalog metadata without requiring credentials.

    Args:
        catalog_url: The root STAC API URL (defaults to Microsoft Planetary Computer).
        timeout: Maximum seconds to wait for root catalog response.

    Returns:
        Dictionary containing catalog status, URL, id, title, description, stac_version,
        and conforms_to classes.

    Raises:
        ConfigurationError: if catalog_url is malformed.
        DataUnavailableError: if the endpoint is unreachable.
    """
    client = open_stac_client(catalog_url, sign_planetary_computer=False, timeout=timeout)
    try:
        conforms = (
            client.get_conforms_to()
            if hasattr(client, "get_conforms_to") and callable(client.get_conforms_to)
            else []
        )
        stac_version = getattr(client, "stac_version", None)
        if stac_version is None and hasattr(client, "to_dict"):
            try:
                stac_version = client.to_dict().get("stac_version")
            except Exception:
                stac_version = None

        return {
            "status": "connected",
            "url": catalog_url,
            "id": getattr(client, "id", None),
            "title": getattr(client, "title", None),
            "description": getattr(client, "description", None),
            "stac_version": stac_version,
            "conforms_to": conforms,
        }
    except Exception as exc:
        raise _classify_stac_exception(exc, f"Connecting to STAC catalog {catalog_url!r}") from exc


def discover_collections(
    catalog_url: str = DEFAULT_STAC_URL,
    *,
    limit: int | None = None,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    """Discover available STAC collections from the catalog without credentials.

    Args:
        catalog_url: STAC API catalog URL.
        limit: Optional maximum number of collections to return.
        client: Optional pre-configured STAC client.

    Returns:
        List of collection summaries with id, title, description, license, keywords,
        and available item assets.
    """
    if client is None:
        client = open_stac_client(catalog_url, sign_planetary_computer=False)
    try:
        collections: list[dict[str, Any]] = []
        for i, col in enumerate(client.get_collections()):
            if limit is not None and i >= limit:
                break
            item_assets: list[str] = []
            if hasattr(col, "item_assets") and col.item_assets:
                item_assets = sorted(col.item_assets.keys())
            elif hasattr(col, "extra_fields") and "item_assets" in col.extra_fields:
                item_assets = sorted(col.extra_fields["item_assets"].keys())

            spatial_extent = None
            temporal_extent = None
            if hasattr(col, "extent") and col.extent is not None:
                if hasattr(col.extent, "spatial") and col.extent.spatial:
                    spatial_extent = col.extent.spatial.bboxes
                if hasattr(col.extent, "temporal") and col.extent.temporal:
                    temporal_extent = [
                        [str(t) if t is not None else None for t in interval]
                        for interval in col.extent.temporal.intervals
                    ]

            collections.append(
                {
                    "id": col.id,
                    "title": getattr(col, "title", None) or col.id,
                    "description": getattr(col, "description", None),
                    "license": getattr(col, "license", None),
                    "keywords": list(getattr(col, "keywords", None) or []),
                    "item_assets": item_assets,
                    "spatial_extent": spatial_extent,
                    "temporal_extent": temporal_extent,
                }
            )
        return collections
    except Exception as exc:
        raise _classify_stac_exception(
            exc, f"Discovering STAC collections on {catalog_url!r}"
        ) from exc


def get_stac_collection(
    collection_id: str,
    catalog_url: str = DEFAULT_STAC_URL,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    """Retrieve detailed metadata for one collection without credentials.

    Supports sentinel-2-l2a, landsat-c2-l2, sentinel-1-rtc, and other public collections.
    """
    resolved_id = resolve_collection_id(collection_id)
    if client is None:
        client = open_stac_client(catalog_url, sign_planetary_computer=False)
    try:
        col = client.get_collection(resolved_id)
        if col is None:
            raise DataUnavailableError(
                f"Collection {resolved_id!r} not found in catalog {catalog_url!r}"
            )
        item_assets: dict[str, Any] = {}
        if hasattr(col, "item_assets") and col.item_assets:
            for k, v in col.item_assets.items():
                item_assets[k] = {
                    "title": getattr(v, "title", None),
                    "description": getattr(v, "description", None),
                    "type": getattr(v, "media_type", getattr(v, "type", None)),
                    "roles": getattr(v, "roles", None),
                }
        summaries: dict[str, Any] = {}
        if hasattr(col, "summaries") and col.summaries:
            raw_sums = getattr(col.summaries, "to_dict", None)
            summaries = raw_sums() if callable(raw_sums) else dict(col.summaries)

        return {
            "id": col.id,
            "title": getattr(col, "title", None) or col.id,
            "description": getattr(col, "description", None),
            "license": getattr(col, "license", None),
            "keywords": list(getattr(col, "keywords", None) or []),
            "item_assets": item_assets,
            "summaries": summaries,
        }
    except (ConfigurationError, DataUnavailableError):
        raise
    except Exception as exc:
        raise _classify_stac_exception(
            exc, f"Getting STAC collection {resolved_id!r} on {catalog_url!r}"
        ) from exc


def deduplicate_scene_overpasses(scenes: Sequence[SceneDescriptor]) -> list[SceneDescriptor]:
    """Deduplicate reprocessed STAC items sharing the same ``(collection, tile_id, datetime)``.

    Microsoft Planetary Computer frequently hosts both an initial processing baseline
    (e.g. ``04.00`` or ``05.09``) and a Collection 1 reprocessed item (``05.10``) for the
    exact same satellite overpass. Keeping both would double-count that acquisition in
    annual compositing and valid observation counts.
    """
    best_by_key: dict[tuple[str, str, str], SceneDescriptor] = {}
    order_keys: list[tuple[str, str, str]] = []

    def _rank(s: SceneDescriptor) -> tuple[float, str]:
        try:
            pb = float(s.processing_baseline) if s.processing_baseline is not None else -1.0
        except ValueError:
            pb = -1.0
        return (pb, s.id)

    unkeyed: list[SceneDescriptor] = []
    for s in scenes:
        if s.tile_id is None:
            unkeyed.append(s)
            continue
        key = (s.collection, s.tile_id, s.datetime)
        if key not in best_by_key:
            best_by_key[key] = s
            order_keys.append(key)
        elif _rank(s) > _rank(best_by_key[key]):
            best_by_key[key] = s

    if not best_by_key:
        return list(scenes)
    return [best_by_key[k] for k in order_keys] + unkeyed


def search_scenes(
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    *,
    platform: str = "sentinel-2",
    max_cloud_cover: float | None = None,
    catalog_url: str = DEFAULT_STAC_URL,
    limit: int | None = None,
    client: Any | None = None,
    intersects: Mapping[str, Any] | None = None,
    tile_id: str | None = None,
    deduplicate_overpasses: bool = False,
) -> list[SceneDescriptor]:
    """Search a STAC API; ``client`` (a pystac_client.Client) may be injected."""
    collection_id = resolve_collection_id(platform)
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ValueError(f"invalid bbox (min must be < max): {bbox}")
    if client is None:
        client = open_stac_client(catalog_url)

    query: dict[str, Any] = {}
    if max_cloud_cover is not None and collection_id != "sentinel-1-rtc":
        query["eo:cloud_cover"] = {"lt": max_cloud_cover}
    if tile_id is not None:
        if collection_id == "sentinel-2-l2a":
            query["s2:mgrs_tile"] = {"eq": tile_id}
        elif collection_id == "landsat-c2-l2":
            query["landsat:wrs_path"] = {"eq": tile_id}

    search_kwargs: dict[str, Any] = {
        "collections": [collection_id],
        "datetime": f"{start}/{end}",
        "query": query if query else None,
        "max_items": limit,
    }
    if intersects is not None:
        search_kwargs["intersects"] = dict(intersects)
    else:
        search_kwargs["bbox"] = list(bbox)

    try:
        search = client.search(**search_kwargs)
        scenes = [scene_from_item(i) for i in search.items()]
    except (ConfigurationError, DataUnavailableError, ValueError):
        raise
    except Exception as exc:
        raise _classify_stac_exception(exc, f"STAC scene search on {catalog_url!r}") from exc

    if deduplicate_overpasses:
        return deduplicate_scene_overpasses(scenes)
    return scenes


def _extract_geojson_geometry(geojson: Mapping[str, Any]) -> dict[str, Any]:
    """Return a single GeoJSON Geometry dict (Polygon or MultiPolygon) from an AOI GeoJSON."""
    gtype = geojson.get("type")
    if gtype in ("Polygon", "MultiPolygon"):
        return dict(geojson)
    if gtype == "Feature":
        geom = geojson.get("geometry")
        if not isinstance(geom, Mapping):
            raise ValueError("GeoJSON Feature has no geometry")
        return _extract_geojson_geometry(geom)
    if gtype == "FeatureCollection":
        features = geojson.get("features") or []
        if len(features) == 1 and isinstance(features[0], Mapping):
            return _extract_geojson_geometry(features[0])
        polys: list[Any] = []
        for feat in features:
            if isinstance(feat, Mapping):
                sub = _extract_geojson_geometry(feat)
                if sub["type"] == "Polygon":
                    polys.append(sub["coordinates"])
                elif sub["type"] == "MultiPolygon":
                    polys.extend(sub["coordinates"])
        return {"type": "MultiPolygon", "coordinates": polys}
    raise ValueError(f"Unsupported GeoJSON type: {gtype!r}")


def calculate_spatial_coverage(
    zone_mask: np.ndarray,
    valid_mask: np.ndarray,
    resolution_m: float = 100.0,
) -> dict[str, Any]:
    """Calculate exact spatial coverage, valid pixel counts, and completeness metrics.

    Args:
        zone_mask: 2D boolean array of AOI boundary pixels.
        valid_mask: 2D boolean array of unmasked valid observations.
        resolution_m: Grid resolution in meters.

    Returns:
        Dictionary with:
        - total_pixels: int
        - valid_pixels: int
        - masked_pixels: int
        - coverage_fraction: float in [0.0, 1.0]
        - coverage_pct: float in [0.0, 100.0]
        - total_area_ha: float
        - observed_area_ha: float
        - is_spatially_complete: bool (coverage_pct >= 95.0)
    """
    import numpy as np

    zm = np.asarray(zone_mask, dtype=bool)
    vm = np.asarray(valid_mask, dtype=bool)
    total_px = int(np.sum(zm))
    if total_px == 0:
        return {
            "total_pixels": 0,
            "valid_pixels": 0,
            "masked_pixels": 0,
            "coverage_fraction": 0.0,
            "coverage_pct": 0.0,
            "total_area_ha": 0.0,
            "observed_area_ha": 0.0,
            "is_spatially_complete": False,
        }
    valid_px = int(np.sum(zm & vm))
    masked_px = total_px - valid_px
    cov_frac = float(valid_px / total_px)
    pixel_area_ha = (resolution_m * resolution_m) / 10000.0
    return {
        "total_pixels": total_px,
        "valid_pixels": valid_px,
        "masked_pixels": masked_px,
        "coverage_fraction": round(cov_frac, 6),
        "coverage_pct": round(cov_frac * 100.0, 3),
        "total_area_ha": round(total_px * pixel_area_ha, 2),
        "observed_area_ha": round(valid_px * pixel_area_ha, 2),
        "is_spatially_complete": bool(cov_frac >= 0.95),
    }


def build_aoi_raster_grid(
    aoi_geojson: Mapping[str, Any],
    scenes: Sequence[SceneDescriptor],
    *,
    resolution_m: float = 100.0,
    quality_band: str = "SCL",
    full_aoi_bounds: bool = True,
) -> tuple[RasterGridSpec, Any]:
    """Construct a canonical UTM :class:`RasterGridSpec` and boolean ``zone_mask`` for an AOI.

    When ``full_aoi_bounds=True`` (the default), the grid bounds span the complete AOI geometry
    so multi-tile acquisitions cover the whole project boundary without artificial clipping.
    """
    if resolution_m <= 0:
        raise ValueError(f"resolution_m must be positive, got {resolution_m}")
    if not scenes:
        raise DataUnavailableError("Cannot build raster grid from an empty scene list")

    _configure_proj_env()
    rasterio = _require("rasterio", "rasterio")
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds as transform_from_bounds
    from rasterio.warp import transform_bounds, transform_geom

    shapely_geom = _require("shapely.geometry", "shapely")
    shapely_ops = _require("shapely.ops", "shapely")

    aoi_bbox = validate_aoi_geojson(dict(aoi_geojson))
    geom_dict = _extract_geojson_geometry(aoi_geojson)
    aoi_shape = shapely_geom.shape(geom_dict)

    scene_shapes = [
        shapely_geom.shape(s.geometry) for s in scenes if isinstance(s.geometry, Mapping)
    ]
    if scene_shapes:
        try:
            from shapely.validation import make_valid

            valid_aoi = make_valid(aoi_shape)
            valid_scenes = [make_valid(s) for s in scene_shapes]
            footprint_union = make_valid(shapely_ops.unary_union(valid_scenes))
            inter_shape = valid_aoi.intersection(footprint_union)
        except Exception:
            footprint_union = shapely_ops.unary_union(scene_shapes)
            inter_shape = aoi_shape.intersection(footprint_union)

        if inter_shape.is_empty:
            raise DataUnavailableError(
                "Retrieved STAC scenes do not geometrically intersect the target AOI"
            )
        if full_aoi_bounds:
            wgs84_bounds = aoi_bbox
        else:
            b = inter_shape.bounds
            wgs84_bounds = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    else:
        wgs84_bounds = aoi_bbox

    target_crs: str | None = None
    epsg_counts: dict[int, int] = {}
    for s in scenes:
        if s.epsg is not None:
            epsg_counts[s.epsg] = epsg_counts.get(s.epsg, 0) + 1
    if epsg_counts:
        dominant_epsg = max(sorted(epsg_counts), key=lambda e: epsg_counts[e])
        target_crs = f"EPSG:{dominant_epsg}"

    if target_crs is None:
        first_href = scenes[0].asset_hrefs.get(quality_band) if quality_band else None
        if not first_href and scenes[0].asset_hrefs:
            first_href = next(iter(scenes[0].asset_hrefs.values()))
        if not first_href:
            raise DataUnavailableError(
                f"Scene {scenes[0].id!r} missing quality asset {quality_band!r} and proj:epsg"
            )
        try:
            with rasterio.open(first_href) as src:
                target_crs = str(src.crs)
        except Exception as exc:
            raise _classify_stac_exception(
                exc, f"Reading CRS from asset of scene {scenes[0].id!r}"
            ) from exc

    utm_bounds = transform_bounds("EPSG:4326", target_crs, *wgs84_bounds)
    utm_minx, utm_miny, utm_maxx, utm_maxy = (
        float(utm_bounds[0]),
        float(utm_bounds[1]),
        float(utm_bounds[2]),
        float(utm_bounds[3]),
    )
    width = max(1, round((utm_maxx - utm_minx) / resolution_m))
    height = max(1, round((utm_maxy - utm_miny) / resolution_m))
    grid_transform = transform_from_bounds(utm_minx, utm_miny, utm_maxx, utm_maxy, width, height)

    utm_geom = transform_geom("EPSG:4326", target_crs, geom_dict)
    zone_mask = ~geometry_mask(
        [utm_geom],
        out_shape=(height, width),
        transform=grid_transform,
        invert=False,
        all_touched=True,
    )
    if not zone_mask.any():
        raise DataUnavailableError(
            f"AOI geometry produced 0 pixels at resolution {resolution_m}m in {target_crs}"
        )

    grid = RasterGridSpec(
        crs=target_crs,
        bounds=(utm_minx, utm_miny, utm_maxx, utm_maxy),
        height=height,
        width=width,
        resolution_m=float(resolution_m),
        wgs84_bounds=wgs84_bounds,
    )
    return grid, zone_mask


def fetch_scene_raster_data(
    scene: SceneDescriptor,
    grid: RasterGridSpec,
    *,
    bands: Sequence[str] = ("B02", "B04", "B08", "B11", "B12"),
    quality_band: str | None = "SCL",
    radsat_band: str | None = None,
    harmonize_s2_baseline: bool = True,
    max_retries: int = 3,
) -> tuple[dict[str, Any], Any, Any, dict[str, Any]]:
    """Fetch actual windowed raster arrays for one STAC scene aligned to ``grid``.

    Reads only the required bounding-box window and only the requested band assets,
    avoiding downloading entire scene archives. Handles SAS token expiration by
    re-signing URLs using ``planetary_computer`` and retrying on authentication errors.

    Raises:
        DataUnavailableError: if a required band asset is missing or cannot be read.
        ConfigurationError: if asset access fails due to invalid credentials / 401 / 403.
    """
    _configure_proj_env()
    import time

    import numpy as np

    rasterio = _require("rasterio", "rasterio")
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds as transform_from_bounds
    from rasterio.vrt import WarpedVRT
    from rasterio.windows import from_bounds as window_from_bounds

    required_assets = list(bands)
    if quality_band is not None:
        required_assets.append(quality_band)
    if radsat_band is not None:
        required_assets.append(radsat_band)

    resolved_hrefs: dict[str, str] = {}
    for asset_name in required_assets:
        href = scene.asset_hrefs.get(asset_name)
        if not href or not isinstance(href, str) or not href.strip():
            for alt in (asset_name.lower(), asset_name.upper()):
                alt_href = scene.asset_hrefs.get(alt)
                if alt_href and isinstance(alt_href, str) and alt_href.strip():
                    href = alt_href
                    break
        if not href or not isinstance(href, str) or not href.strip():
            aliases = _ASSET_ALIASES.get(asset_name, ())
            for alias in aliases:
                alt_href = scene.asset_hrefs.get(alias)
                if alt_href and isinstance(alt_href, str) and alt_href.strip():
                    href = alt_href
                    break
        if not href or not isinstance(href, str) or not href.strip():
            raise DataUnavailableError(
                f"Scene {scene.id!r} is missing required raster asset {asset_name!r} "
                f"(available assets with hrefs: {sorted(scene.asset_hrefs)})"
            )
        resolved_hrefs[asset_name] = href

    grid_transform = transform_from_bounds(*grid.bounds, grid.width, grid.height)

    def _read_asset(asset_key: str, resampling: Any, dtype: Any) -> Any:
        href = resolved_hrefs[asset_key]
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                with (
                    rasterio.Env(
                        GDAL_HTTP_TIMEOUT="30",
                        GDAL_HTTP_MAX_RETRY="5",
                        GDAL_HTTP_RETRY_DELAY="1",
                        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.jp2",
                        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                    ),
                    rasterio.open(href) as src,
                ):
                    if str(src.crs) == grid.crs:
                        win = window_from_bounds(*grid.bounds, transform=src.transform)
                        return src.read(
                            1,
                            window=win,
                            out_shape=(grid.height, grid.width),
                            boundless=True,
                            fill_value=0,
                            resampling=resampling,
                        ).astype(dtype)
                    with WarpedVRT(
                        src,
                        crs=grid.crs,
                        transform=grid_transform,
                        width=grid.width,
                        height=grid.height,
                        resampling=resampling,
                    ) as vrt:
                        return vrt.read(1).astype(dtype)
            except Exception as exc:
                last_exc = exc
                err_msg = str(exc).lower()
                # Check for expired SAS token / authorization failure
                if any(
                    x in err_msg
                    for x in (
                        "401",
                        "403",
                        "auth",
                        "sas",
                        "forbidden",
                        "unauthorized",
                        "signature",
                        "expired",
                    )
                ):
                    fresh_href = sign_asset_url(href)
                    if fresh_href != href:
                        href = fresh_href
                        resolved_hrefs[asset_key] = fresh_href
                        continue
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (2**attempt))
                    continue
                break

        if last_exc is not None:
            raise _classify_stac_exception(
                last_exc, f"Fetching raster asset {asset_key!r} for scene {scene.id!r}"
            ) from last_exc

    quality_arr = (
        _read_asset(quality_band, Resampling.nearest, np.int64)
        if quality_band is not None
        else np.ones((grid.height, grid.width), dtype=np.int64)
    )
    radsat_arr = (
        _read_asset(radsat_band, Resampling.nearest, np.int64) if radsat_band is not None else None
    )

    s2_offset_applied = False
    if (
        harmonize_s2_baseline
        and scene.collection == "sentinel-2-l2a"
        and scene.processing_baseline is not None
    ):
        try:
            if float(scene.processing_baseline) >= 4.0:
                s2_offset_applied = True
        except ValueError:
            s2_offset_applied = False

    bands_dn: dict[str, Any] = {}
    for band_name in bands:
        raw_dn = _read_asset(band_name, Resampling.bilinear, float)
        # 0 in Sentinel-2 L2A and Landsat C2 L2 COGs is nodata fill
        valid_dn = np.where(raw_dn > 0.0, raw_dn, np.nan)
        if s2_offset_applied:
            # Remove the +1000 BOA_ADD_OFFSET introduced in Sentinel-2 PB 04.00+
            valid_dn = np.where(
                np.isfinite(valid_dn),
                np.maximum(valid_dn - 1000.0, 0.0),
                np.nan,
            )
        bands_dn[band_name] = valid_dn

    meta = {
        "scene_id": scene.id,
        "collection_id": scene.collection,
        "datetime": scene.datetime,
        "sensor": scene.sensor,
        "tile_id": scene.tile_id,
        "cloud_cover": scene.cloud_cover,
        "source_url": scene.href,
        "asset_source_urls": {k: v.split("?")[0] for k, v in resolved_hrefs.items()},
        "processing_baseline": scene.processing_baseline,
        "s2_boa_offset_harmonized": s2_offset_applied,
        "crs": grid.crs,
        "resolution_m": grid.resolution_m,
        "shape": [grid.height, grid.width],
    }
    return bands_dn, quality_arr, radsat_arr, meta


def scenes_hash(scenes: Sequence[SceneDescriptor]) -> str:
    """Deterministic sha256 over scene ids (order-independent)."""
    digest = hashlib.sha256()
    for sid in sorted(s.id for s in scenes):
        digest.update(sid.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def load_scenes(
    items: Sequence[Any],
    *,
    bands: Sequence[str],
    bbox: tuple[float, float, float, float],
    resolution: float = 10.0,
    chunks: dict[str, int] | None = None,
    crs: str = "EPSG:4326",
) -> Any:
    """Lazily load pystac Items into a dask-backed xarray Dataset via odc-stac."""
    if not items:
        raise ValueError("no items to load")
    odc = _require("odc.stac", "odc-stac")
    return odc.load(
        list(items),
        bands=list(bands),
        bbox=bbox,
        resolution=resolution,
        crs=crs,
        chunks=chunks or {"x": 1024, "y": 1024},
    )


__all__ = [
    "COLLECTIONS",
    "DEFAULT_STAC_URL",
    "EARTH_SEARCH_URL",
    "RasterGridSpec",
    "SceneDescriptor",
    "build_aoi_raster_grid",
    "calculate_spatial_coverage",
    "check_catalog_connectivity",
    "deduplicate_scene_overpasses",
    "discover_collections",
    "fetch_scene_raster_data",
    "get_stac_collection",
    "load_scenes",
    "open_stac_client",
    "resolve_collection_id",
    "scenes_hash",
    "search_scenes",
    "sign_asset_url",
    "validate_aoi_geojson",
]
