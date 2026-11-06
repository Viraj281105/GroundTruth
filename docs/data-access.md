# Data access

Package `groundtruth.data_access`.

- `stac.py`: `search_scenes(bbox, start, end, platform="sentinel-2"|"landsat")` returns
  `SceneDescriptor`s (default catalog Planetary Computer; `EARTH_SEARCH_URL` or any URL
  via `catalog_url`). `load_scenes(items, bands=..., bbox=...)` loads lazily with odc-stac.
- `store.py`: `ParquetStore(root)` with `write_table`, `read_table`, `query(sql)`
  (tables are DuckDB views by name; GeoDataFrames are written as GeoParquet).
- `zarr_io.py`: `write_zarr` / `read_zarr` for chunked xarray Datasets.
- `pipelines.py`: `build_definitions(...)` returns Dagster `Definitions` with a
  `stac_scenes` asset; materialization metadata records scene ids and a sha256 of them.

Optional pip packages (lazy; clear ImportError if missing): `pystac-client`, `odc-stac`,
`duckdb`, `pyarrow`, `zarr`, `xarray`, `dagster`, `geopandas` (GeoParquet).
No fallbacks: empty searches and missing tables raise.
