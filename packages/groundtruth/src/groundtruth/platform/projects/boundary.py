"""Project boundary parsing and validation (GeoJSON and KML).

Everything here is pure: bytes in, a validated :class:`BoundaryResult` out. The file that is
stored on disk is the canonical serialization of ``geojson``, and ``sha256`` is its hash, so a
stored boundary can always be re-verified against the recorded digest.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import shapely
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

MAX_BOUNDARY_BYTES = 5 * 1024 * 1024
EQUAL_AREA_CRS = "EPSG:6933"
_HA_PER_M2 = 1.0 / 10_000.0
_POLYGONAL = {"Polygon", "MultiPolygon"}


class BoundaryValidationError(ValueError):
    """The uploaded boundary is not usable; the message says why (surfaced as HTTP 422)."""


@dataclass(frozen=True)
class BoundaryResult:
    geojson: dict[str, Any]
    """A GeoJSON ``FeatureCollection`` with exactly one polygonal feature, WGS84 lon/lat."""
    sha256: str
    """SHA-256 of :func:`serialize_geojson` applied to ``geojson``."""
    area_ha: float


def serialize_geojson(geojson: dict[str, Any]) -> bytes:
    """Canonical bytes: stable key order, no insignificant whitespace."""
    return json.dumps(geojson, sort_keys=True, separators=(",", ":")).encode("utf-8")


@lru_cache(maxsize=1)
def _to_equal_area() -> Transformer:
    return Transformer.from_crs("EPSG:4326", EQUAL_AREA_CRS, always_xy=True)


def _area_ha(geom: BaseGeometry) -> float:
    projected = transform(_to_equal_area().transform, geom)
    return float(projected.area) * _HA_PER_M2


def _polygons_from_geojson_geometry(geometry: Any) -> list[BaseGeometry]:
    if not isinstance(geometry, dict):
        raise BoundaryValidationError("a feature has no geometry")
    kind = geometry.get("type")
    if kind not in _POLYGONAL:
        raise BoundaryValidationError(
            f"boundary geometry must be a Polygon or MultiPolygon, not {kind!r}"
        )
    try:
        geom = shape(geometry)
    except (ValueError, TypeError, KeyError, shapely.errors.ShapelyError) as exc:
        raise BoundaryValidationError(f"malformed {kind} coordinates") from exc
    return [geom]


def _from_geojson(data: bytes) -> list[BaseGeometry]:
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BoundaryValidationError("boundary is not valid UTF-8 JSON") from exc
    if not isinstance(doc, dict):
        raise BoundaryValidationError("boundary JSON must be an object")
    kind = doc.get("type")
    if kind == "FeatureCollection":
        features = doc.get("features")
        if not isinstance(features, list) or not features:
            raise BoundaryValidationError("FeatureCollection has no features")
        out: list[BaseGeometry] = []
        for feature in features:
            if not isinstance(feature, dict):
                raise BoundaryValidationError("FeatureCollection holds a non-feature entry")
            out += _polygons_from_geojson_geometry(feature.get("geometry"))
        return out
    if kind == "Feature":
        return _polygons_from_geojson_geometry(doc.get("geometry"))
    return _polygons_from_geojson_geometry(doc)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ring(element: ET.Element) -> list[tuple[float, float]]:
    coords = next((e for e in element.iter() if _local(e.tag) == "coordinates"), None)
    if coords is None or not (coords.text or "").strip():
        raise BoundaryValidationError("KML ring has no coordinates")
    points: list[tuple[float, float]] = []
    for token in (coords.text or "").split():
        parts = token.split(",")
        if len(parts) < 2:
            raise BoundaryValidationError(f"KML coordinate {token!r} is not lon,lat[,alt]")
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError as exc:
            raise BoundaryValidationError(f"KML coordinate {token!r} is not numeric") from exc
    return points


_XML_DECL = re.compile(rb"^\s*<\?xml\s[^>]*?encoding\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


def _require_utf8_kml(data: bytes) -> bytes:
    """Only UTF-8 KML is accepted, so the byte-level DOCTYPE/ENTITY guard cannot be bypassed
    by a wider encoding (UTF-16/32) that expat would transcode. Returns ``data`` sans BOM."""
    if data.startswith(codecs.BOM_UTF8):
        data = data[len(codecs.BOM_UTF8) :]
    wide = (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE, codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)
    if data.startswith(wide) or b"\x00" in data:
        raise BoundaryValidationError("KML must be UTF-8 encoded (UTF-16/32 is not accepted)")
    declared = _XML_DECL.match(data)
    if declared is not None and declared.group(1).decode("ascii", "replace").lower() != "utf-8":
        raise BoundaryValidationError("KML must be UTF-8 encoded (declared encoding differs)")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BoundaryValidationError("KML is not valid UTF-8") from exc
    return data


def _from_kml(data: bytes) -> list[BaseGeometry]:
    data = _require_utf8_kml(data)
    head = data.lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise BoundaryValidationError("KML must not declare a DOCTYPE or entities")
    try:
        root = ET.fromstring(data)  # DOCTYPE/ENTITY rejected above
    except ET.ParseError as exc:
        raise BoundaryValidationError("boundary is not well-formed KML") from exc
    polygons: list[BaseGeometry] = []
    for element in root.iter():
        if _local(element.tag) != "Polygon":
            continue
        outer = [e for e in element if _local(e.tag) == "outerBoundaryIs"]
        if len(outer) != 1:
            raise BoundaryValidationError("KML Polygon needs exactly one outerBoundaryIs")
        holes = [_ring(e) for e in element if _local(e.tag) == "innerBoundaryIs"]
        try:
            polygons.append(Polygon(_ring(outer[0]), holes))
        except (ValueError, shapely.errors.ShapelyError) as exc:
            raise BoundaryValidationError("KML polygon ring is degenerate") from exc
    if not polygons:
        raise BoundaryValidationError("KML contains no Polygon placemarks")
    return polygons


def _check_coordinates(geom: BaseGeometry) -> None:
    minx, miny, maxx, maxy = geom.bounds
    if not (minx >= -180.0 and maxx <= 180.0 and miny >= -90.0 and maxy <= 90.0):
        raise BoundaryValidationError("coordinates must be WGS84 longitude/latitude degrees")


def _repair_overlap(part: BaseGeometry) -> BaseGeometry:
    """Return ``part`` if valid; dissolve overlapping members of an otherwise sound MultiPolygon.

    Registry boundaries often list adjacent parcels that overlap slightly, which makes the
    MultiPolygon invalid although every parcel is a sound polygon. Their union is exact and
    loses nothing. Anything else invalid (a bowtie ring, a repeated point) is rejected.
    """
    if shapely.is_valid(part):
        return part
    if isinstance(part, MultiPolygon) and all(shapely.is_valid(p) for p in part.geoms):
        return unary_union(list(part.geoms))
    raise BoundaryValidationError(f"boundary geometry is invalid: {shapely.is_valid_reason(part)}")


def parse_boundary(data: bytes, filename: str) -> BoundaryResult:
    """Validate an uploaded boundary and return its normalized form.

    Raises:
        BoundaryValidationError: too large, wrong type, not polygonal, empty, invalid
            geometry (for example a self-intersecting ring) or out-of-range coordinates.
    """
    if len(data) > MAX_BOUNDARY_BYTES:
        raise BoundaryValidationError("boundary file is larger than 5 MB")
    if not data.strip():
        raise BoundaryValidationError("boundary file is empty")
    name = filename.lower()
    if name.endswith((".geojson", ".json")):
        parts = _from_geojson(data)
    elif name.endswith(".kml"):
        parts = _from_kml(data)
    else:
        raise BoundaryValidationError("boundary must be a .geojson, .json or .kml file")

    for part in parts:
        if part.is_empty:
            raise BoundaryValidationError("boundary contains an empty geometry")
        _check_coordinates(part)
    parts = [_repair_overlap(part) for part in parts]
    merged = parts[0] if len(parts) == 1 else unary_union(parts)
    if merged.is_empty or not isinstance(merged, Polygon | MultiPolygon):
        raise BoundaryValidationError("boundary does not form a polygon")
    area = _area_ha(merged)
    if not area > 0:
        raise BoundaryValidationError("boundary has zero area")

    geojson: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(merged)}],
    }
    # Round-trip through JSON so tuples become lists and the digest matches the stored bytes.
    geojson = json.loads(json.dumps(geojson))
    return BoundaryResult(
        geojson=geojson,
        sha256=hashlib.sha256(serialize_geojson(geojson)).hexdigest(),
        area_ha=area,
    )
