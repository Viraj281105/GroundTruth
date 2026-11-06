"""STAC search for Sentinel-2 / Landsat scenes and lazy loading via odc-stac."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"

COLLECTIONS: dict[str, str] = {
    "sentinel-2": "sentinel-2-l2a",
    "landsat": "landsat-c2-l2",
}


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


def _require(module: str, package: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(f"'{package}' is required: pip install {package}") from exc


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
    return SceneDescriptor(
        id=str(item.id),
        collection=str(item.collection_id),
        datetime=str(when),
        bbox=(raw[0], raw[1], raw[2], raw[3]),
        cloud_cover=None if cloud is None else float(cloud),
        assets=tuple(sorted(item.assets)),
        href=item.get_self_href(),
    )


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
) -> list[SceneDescriptor]:
    """Search a STAC API; ``client`` (a pystac_client.Client) may be injected."""
    if platform not in COLLECTIONS:
        raise ValueError(f"platform must be one of {sorted(COLLECTIONS)}, got {platform!r}")
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ValueError(f"invalid bbox (min must be < max): {bbox}")
    if client is None:
        client = _require("pystac_client", "pystac-client").Client.open(catalog_url)
    query = {"eo:cloud_cover": {"lt": max_cloud_cover}} if max_cloud_cover is not None else None
    search = client.search(
        collections=[COLLECTIONS[platform]],
        bbox=list(bbox),
        datetime=f"{start}/{end}",
        query=query,
        max_items=limit,
    )
    return [scene_from_item(i) for i in search.items()]


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
