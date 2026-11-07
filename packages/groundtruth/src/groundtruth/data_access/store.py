"""DuckDB-backed (Geo)Parquet store for donor pools and results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def _duckdb() -> Any:
    try:
        import duckdb
    except ImportError as exc:
        raise ImportError("'duckdb' is required: pip install duckdb") from exc
    return duckdb


class ParquetStore:
    """Directory of Parquet tables, queryable with SQL via DuckDB."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        if not name or any(c in name for c in "/\\.") or name.startswith("_"):
            raise ValueError(f"invalid table name: {name!r}")
        return self.root / f"{name}.parquet"

    def write_table(self, name: str, df: pd.DataFrame) -> Path:
        """Write a table; GeoDataFrames are written as GeoParquet."""
        target = self.path(name)
        if type(df).__name__ == "GeoDataFrame":
            df.to_parquet(target)
            return target
        con = _duckdb().connect()
        try:
            con.register("_df", df)
            escaped = str(target).replace("'", "''")
            con.execute(f"COPY _df TO '{escaped}' (FORMAT PARQUET)")
        finally:
            con.close()
        return target

    def read_table(self, name: str) -> pd.DataFrame:
        target = self.path(name)
        if not target.exists():
            raise FileNotFoundError(f"table not found: {target}")
        return self.query(f'SELECT * FROM "{name}"')

    def query(self, sql: str) -> pd.DataFrame:
        """Run SQL; every stored table is available as a view named after it."""
        con = _duckdb().connect()
        try:
            for p in self.root.glob("*.parquet"):
                escaped = str(p).replace("'", "''")
                con.execute(f"CREATE VIEW \"{p.stem}\" AS SELECT * FROM read_parquet('{escaped}')")
            return con.execute(sql).fetchdf()
        finally:
            con.close()
