"""Offline tests for data_access (fakes; heavy deps via importorskip)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from groundtruth.data_access.pipelines import ingest_scenes, lineage_metadata
from groundtruth.data_access.stac import scenes_hash, search_scenes
from groundtruth.data_access.store import ParquetStore

BBOX = (73.0, 18.0, 73.5, 18.5)


def _item(i: str) -> Any:
    return SimpleNamespace(
        id=i,
        collection_id="sentinel-2-l2a",
        properties={"datetime": "2024-01-01T00:00:00Z", "eo:cloud_cover": 5},
        bbox=[73.0, 18.0, 73.5, 18.5],
        assets={"B04": 1, "B08": 1},
        get_self_href=lambda: f"https://x/{i}",
    )


class FakeClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def search(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return SimpleNamespace(items=lambda: [_item("b"), _item("a")])


def test_search_scenes_typed() -> None:
    c = FakeClient()
    scenes = search_scenes(BBOX, "2024-01-01", "2024-02-01", client=c)
    assert [s.id for s in scenes] == ["b", "a"]
    assert scenes[0].cloud_cover == 5.0
    assert c.kwargs["collections"] == ["sentinel-2-l2a"]
    assert c.kwargs["datetime"] == "2024-01-01/2024-02-01"


def test_search_validation() -> None:
    with pytest.raises(ValueError):
        search_scenes(BBOX, "a", "b", platform="modis", client=FakeClient())
    with pytest.raises(ValueError):
        search_scenes((1, 1, 0, 0), "a", "b", client=FakeClient())


def test_hash_order_independent() -> None:
    s = search_scenes(BBOX, "a", "b", client=FakeClient())
    assert scenes_hash(s) == scenes_hash(list(reversed(s)))
    meta = lineage_metadata(s, "u")
    assert meta["n_scenes"] == 2 and meta["scenes_sha256"] == scenes_hash(s)


def test_store_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    store = ParquetStore(tmp_path)
    store.write_table("donors", pd.DataFrame({"id": [1, 2, 3], "v": [0.1, 0.2, 0.3]}))
    assert len(store.read_table("donors")) == 3
    assert store.query("SELECT sum(v) AS s FROM donors")["s"][0] == pytest.approx(0.6)
    with pytest.raises(FileNotFoundError):
        store.read_table("missing")
    with pytest.raises(ValueError):
        store.path("../x")


def test_ingest_lineage(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    store = ParquetStore(tmp_path)
    meta = ingest_scenes(store, "scenes", BBOX, "a", "b", client=FakeClient())
    assert meta["scene_ids"] == ["b", "a"]
    assert len(store.read_table("scenes")) == 2


def test_zarr_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("zarr")
    xr = pytest.importorskip("xarray")
    from groundtruth.data_access.zarr_io import read_zarr, write_zarr

    ds = xr.Dataset({"a": (("x",), [1.0, 2.0, 3.0, 4.0])})
    write_zarr(ds, tmp_path / "z.zarr", chunks={"x": 2})
    assert list(read_zarr(tmp_path / "z.zarr")["a"].values) == [1.0, 2.0, 3.0, 4.0]


def test_dagster_defs() -> None:
    pytest.importorskip("dagster")
    from groundtruth.data_access.pipelines import build_definitions

    assert build_definitions(".", BBOX, "a", "b") is not None
