"""Dagster assets: STAC search -> Parquet store, with lineage metadata."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from groundtruth.data_access.stac import (
    DEFAULT_STAC_URL,
    SceneDescriptor,
    scenes_hash,
    search_scenes,
)
from groundtruth.data_access.store import ParquetStore


def scenes_to_frame(scenes: list[SceneDescriptor]) -> pd.DataFrame:
    rows = []
    for s in scenes:
        d = asdict(s)
        d.pop("asset_hrefs", None)
        d.pop("geometry", None)
        d["bbox"] = list(s.bbox)
        d["assets"] = list(s.assets)
        rows.append(d)
    return pd.DataFrame(rows)


def lineage_metadata(scenes: list[SceneDescriptor], catalog_url: str) -> dict[str, Any]:
    return {
        "catalog_url": catalog_url,
        "n_scenes": len(scenes),
        "scene_ids": [s.id for s in scenes],
        "scenes_sha256": scenes_hash(scenes),
    }


def ingest_scenes(
    store: ParquetStore,
    table: str,
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    *,
    platform: str = "sentinel-2",
    catalog_url: str = DEFAULT_STAC_URL,
    client: Any | None = None,
) -> dict[str, Any]:
    """Search, persist scene descriptors, return lineage metadata."""
    scenes = search_scenes(
        bbox, start, end, platform=platform, catalog_url=catalog_url, client=client
    )
    if not scenes:
        raise ValueError("STAC search returned no scenes; refusing to write an empty table")
    store.write_table(table, scenes_to_frame(scenes))
    return lineage_metadata(scenes, catalog_url)


def build_definitions(
    store_root: str,
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    *,
    platform: str = "sentinel-2",
    catalog_url: str = DEFAULT_STAC_URL,
) -> Any:
    """Return a dagster ``Definitions`` with a ``stac_scenes`` asset."""
    try:
        import dagster as dg
    except ImportError as exc:
        raise ImportError("'dagster' is required: pip install dagster") from exc

    @dg.asset(name="stac_scenes", group_name="data_access")
    def stac_scenes() -> Any:
        meta = ingest_scenes(
            ParquetStore(store_root),
            "stac_scenes",
            bbox,
            start,
            end,
            platform=platform,
            catalog_url=catalog_url,
        )
        return dg.MaterializeResult(metadata=meta)

    return dg.Definitions(assets=[stac_scenes])
