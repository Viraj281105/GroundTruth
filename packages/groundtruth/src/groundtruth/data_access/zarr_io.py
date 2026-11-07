"""Chunked Zarr read/write for xarray Datasets."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


def _need(module: str, package: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(f"'{package}' is required: pip install {package}") from exc


def write_zarr(
    ds: Any, path: str | Path, *, chunks: dict[str, int] | None = None, mode: str = "w-"
) -> Path:
    """Write an xarray Dataset to Zarr (refuses to overwrite by default)."""
    _need("xarray", "xarray")
    _need("zarr", "zarr")
    if chunks:
        _need("dask", "dask")  # xarray chunking needs dask
        ds = ds.chunk(chunks)
    ds.to_zarr(str(path), mode=mode)
    return Path(path)


def read_zarr(path: str | Path) -> Any:
    """Open a Zarr store lazily as an xarray Dataset."""
    xr = _need("xarray", "xarray")
    _need("zarr", "zarr")
    _need("dask", "dask")  # open_zarr reads lazily through dask
    if not Path(path).exists():
        raise FileNotFoundError(f"zarr store not found: {path}")
    return xr.open_zarr(str(path))
