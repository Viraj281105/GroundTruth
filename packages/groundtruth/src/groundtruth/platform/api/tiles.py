"""Case boundaries as GeoJSON, and Mapbox Vector Tiles from PostGIS.

Tiles need a PostGIS database (``DATABASE_URL`` on PostgreSQL) holding a ``case_boundaries``
table with ``case_id text`` and ``geom geometry(Geometry, 4326)``. Without one the tile
endpoint answers ``503 postgis_not_configured``; it never returns made-up tiles.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi import Path as PathParam

from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.platform.api.errors import ApiErrorBody, ApiErrorCode, api_error
from groundtruth.platform.cases.registry import cases_directory, get_case
from groundtruth.platform.config import get_settings

router = APIRouter(tags=["geo"])

POSTGIS_NOT_CONFIGURED = "postgis_not_configured"
MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"

_TILE_SQL = """
WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env),
mvtgeom AS (
    SELECT b.case_id,
           ST_AsMVTGeom(ST_Transform(b.geom, 3857), bounds.env, 4096, 64, true) AS geom
    FROM case_boundaries b, bounds
    WHERE ST_Transform(b.geom, 3857) && bounds.env
)
SELECT COALESCE(ST_AsMVT(mvtgeom.*, 'boundaries', 4096, 'geom'), ''::bytea) FROM mvtgeom
"""


def _unavailable(message: str, hint: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": POSTGIS_NOT_CONFIGURED, "message": message, "hint": hint},
    )


@router.get(
    "/cases/{case_id}/boundary.geojson",
    summary="A case's project boundary as GeoJSON",
    responses={
        200: {
            "content": {"application/geo+json": {"schema": {"type": "object"}}},
            "description": "The boundary.",
        },
        404: {"model": ApiErrorBody, "description": "Unknown case or no boundary file."},
    },
)
def case_boundary(case_id: str) -> Response:
    """The boundary file named by the case's `boundary_path`, served as stored."""
    try:
        case = get_case(case_id)
    except CaseDefinitionError as exc:
        raise api_error(ApiErrorCode.CASE_NOT_FOUND, str(exc)) from exc
    relative = case.claim.boundary_path
    if not relative:
        raise api_error(ApiErrorCode.CASE_NOT_FOUND, f"Case {case_id!r} has no boundary.")
    root = cases_directory().parent.resolve()
    path = (root / relative).resolve()
    if root not in path.parents or not path.is_file():
        raise api_error(
            ApiErrorCode.CASE_NOT_FOUND,
            f"The boundary file for {case_id!r} has not been obtained.",
        )
    return Response(path.read_bytes(), media_type="application/geo+json")


@lru_cache(maxsize=4)
def _engine(url: str) -> Any:
    import sqlalchemy as sa

    return sa.create_engine(url, pool_pre_ping=True)


@router.get(
    "/tiles/{z}/{x}/{y}.mvt",
    summary="Boundary vector tile (PostGIS)",
    responses={
        200: {
            "content": {MVT_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "A Mapbox Vector Tile.",
        },
        404: {"model": ApiErrorBody, "description": "Tile coordinates out of range."},
        503: {"model": ApiErrorBody, "description": "PostGIS is not configured or not answering."},
    },
)
def boundary_tile(
    z: int = PathParam(ge=0, le=22), x: int = PathParam(ge=0), y: int = PathParam(ge=0)
) -> Response:
    """Case boundaries clipped to tile z/x/y by `ST_AsMVT`; layer name `boundaries`."""
    if x >= 2**z or y >= 2**z:
        raise HTTPException(status_code=404, detail={"code": "tile_out_of_range"})
    url = get_settings().database_url
    if not url or not url.startswith("postgres"):
        raise _unavailable(
            "Vector tiles need a PostGIS database; DATABASE_URL is not a PostgreSQL URL.",
            "Set DATABASE_URL to a PostGIS database (infrastructure/docker/postgis.override.yml).",
        )
    import sqlalchemy as sa

    try:
        with _engine(url).connect() as conn:
            tile = conn.execute(sa.text(_TILE_SQL), {"z": z, "x": x, "y": y}).scalar_one()
    except sa.exc.SQLAlchemyError as exc:
        raise _unavailable(
            "PostGIS did not answer the tile query.",
            "Check the database runs PostGIS and has a case_boundaries table.",
        ) from exc
    return Response(bytes(tile), media_type=MVT_MEDIA_TYPE, headers={"Cache-Control": "no-store"})
