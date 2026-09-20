"""Dependency-free geodesic geometry checks for registry boundaries.

The core package must not require GEOS or GDAL (``docs/data/conventions.md``),
so the handful of geometric facts needed to *validate* a boundary are computed
here instead: area on the WGS84 ellipsoid, ring closure, self-intersection, and
the pairwise intersection area that decides whether parts of a multipolygon
overlap.

This module deliberately does **not** implement clipping, buffering or boolean
operations. Those belong to the masking provider, which has a real geometry
engine behind it. What is here is what a reviewer needs to check that a
committed boundary artifact is what it claims to be.

Areas are computed with the spherical-excess formula of Chamberlain & Duquette
(2007) on the WGS84 ellipsoid. For polygons of this size the error against a
full geodesic computation is well under the 0.5% at which anything downstream
would notice, and the method is stated wherever a number produced here is
recorded.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

WGS84_SEMI_MAJOR_M = 6378137.0
WGS84_ECCENTRICITY_SQ = 0.00669437999014

Point = tuple[float, float]
Ring = list[Point]

KM_PER_DEGREE_LAT = 110.57
KM_PER_DEGREE_LON_EQUATOR = 111.32


def is_closed(ring: Ring) -> bool:
    """True if the ring's first and last vertices are identical."""
    return len(ring) > 3 and ring[0] == ring[-1]


def _closed(ring: Ring) -> Ring:
    return ring if is_closed(ring) else [*ring, ring[0]]


def signed_planar_area(ring: Ring) -> float:
    """Shoelace area in squared degrees. Sign only; magnitude is meaningless.

    Positive means counter-clockwise, which is the winding RFC 7946 specifies
    for exterior rings and which Earth Engine honours on geodesic polygons.
    Orientation is tested here rather than on :func:`ring_area_m2`, whose
    spherical-excess sign follows the opposite convention.
    """
    total = 0.0
    r = _closed(ring)
    for (x1, y1), (x2, y2) in pairwise(r):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def ring_area_m2(ring: Ring) -> float:
    """Area of a ring on the WGS84 ellipsoid, in square metres.

    The value is signed, but the sign follows the spherical-excess convention
    and is the opposite of the shoelace one, so callers that want orientation
    should use :func:`is_counter_clockwise` and callers that want area should
    take the absolute value.
    """
    total = 0.0
    r = _closed(ring)
    for (lon1, lat1), (lon2, lat2) in pairwise(r):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    area = total * WGS84_SEMI_MAJOR_M**2 / 2.0 * math.sqrt(1 - WGS84_ECCENTRICITY_SQ)
    return area


def is_counter_clockwise(ring: Ring) -> bool:
    """True if the ring winds counter-clockwise, as RFC 7946 wants for exteriors."""
    return signed_planar_area(ring) > 0


def polygon_area_m2(polygon: list[Ring]) -> float:
    """Area of one GeoJSON polygon: exterior ring less its holes."""
    if not polygon:
        return 0.0
    exterior = abs(ring_area_m2(polygon[0]))
    holes = sum(abs(ring_area_m2(r)) for r in polygon[1:])
    return exterior - holes


def bbox(ring: Ring) -> tuple[float, float, float, float]:
    """``(min_lon, min_lat, max_lon, max_lat)`` of a ring."""
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _bboxes_overlap(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _orientation(a: Point, b: Point, c: Point) -> int:
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(v) < 1e-15:
        return 0
    return 1 if v > 0 else -1


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return (
        min(a[0], b[0]) - 1e-12 <= p[0] <= max(a[0], b[0]) + 1e-12
        and min(a[1], b[1]) - 1e-12 <= p[1] <= max(a[1], b[1]) + 1e-12
    )


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True if segment ``p1p2`` touches or crosses segment ``p3p4``."""
    o1, o2 = _orientation(p1, p2, p3), _orientation(p1, p2, p4)
    o3, o4 = _orientation(p3, p4, p1), _orientation(p3, p4, p2)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _on_segment(p1, p2, p3):
        return True
    if o2 == 0 and _on_segment(p1, p2, p4):
        return True
    if o3 == 0 and _on_segment(p3, p4, p1):
        return True
    return bool(o4 == 0 and _on_segment(p3, p4, p2))


def _segments(ring: Ring) -> list[tuple[Point, Point]]:
    r = _closed(ring)
    return list(pairwise(r))


def self_intersections(ring: Ring) -> list[tuple[int, int]]:
    """Indices of non-adjacent segment pairs that intersect.

    An empty list is the only acceptable result for a boundary that will be
    intersected with masks downstream: a self-intersecting ring makes area and
    containment ambiguous.
    """
    segs = _segments(ring)
    n = len(segs)
    bad: list[tuple[int, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue  # neighbours legitimately share an endpoint
            if segments_intersect(*segs[i], *segs[j]):
                bad.append((i, j))
    return bad


def point_in_ring(point: Point, ring: Ring) -> bool:
    """Ray-casting containment test in planar degrees."""
    x, y = point
    inside = False
    r = _closed(ring)
    for (x1, y1), (x2, y2) in pairwise(r):
        if (y1 > y) != (y2 > y):
            x_at = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_at:
                inside = not inside
    return inside


def _x_intervals(ring: Ring, y: float) -> list[tuple[float, float]]:
    xs: list[float] = []
    r = _closed(ring)
    for (x1, y1), (x2, y2) in pairwise(r):
        if (y1 > y) != (y2 > y):
            xs.append((x2 - x1) * (y - y1) / (y2 - y1) + x1)
    xs.sort()
    return list(zip(xs[0::2], xs[1::2], strict=False))


def _overlap_length(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    total = 0.0
    for a0, a1 in a:
        for b0, b1 in b:
            lo, hi = max(a0, b0), min(a1, b1)
            if hi > lo:
                total += hi - lo
    return total


def intersection_area_km2(ring_a: Ring, ring_b: Ring, *, bands: int = 8000) -> float:
    """Area shared by two rings, by latitude-band integration.

    Exact boolean intersection needs a clipping library the core package does
    not carry. Band integration converges quickly and is sufficient for its one
    job here: deciding whether two parts of a registry multipolygon overlap, and
    by how much.

    Args:
        ring_a: First ring.
        ring_b: Second ring.
        bands: Number of latitude bands. Raise it to tighten convergence.

    Returns:
        Shared area in km², or ``0.0`` when the bounding boxes are disjoint.
    """
    box_a, box_b = bbox(ring_a), bbox(ring_b)
    if not _bboxes_overlap(box_a, box_b):
        return 0.0
    y0, y1 = max(box_a[1], box_b[1]), min(box_a[3], box_b[3])
    if y1 <= y0:
        return 0.0
    dy = (y1 - y0) / bands
    total = 0.0
    for i in range(bands):
        y = y0 + dy * (i + 0.5)
        width_deg = _overlap_length(_x_intervals(ring_a, y), _x_intervals(ring_b, y))
        if width_deg:
            km_per_deg_lon = KM_PER_DEGREE_LON_EQUATOR * math.cos(math.radians(y))
            total += width_deg * km_per_deg_lon * dy * KM_PER_DEGREE_LAT
    return total


@dataclass(frozen=True, slots=True)
class OverlapFinding:
    """Two parts of a multipolygon that share area."""

    part_a: int
    part_b: int
    area_km2: float


@dataclass(frozen=True, slots=True)
class GeometryReport:
    """What is true about a multipolygon, stated so it can be recorded."""

    parts: int
    vertices: int
    holes: int
    unclosed_rings: tuple[int, ...]
    self_intersecting_rings: tuple[int, ...]
    clockwise_exterior_rings: tuple[int, ...]
    out_of_range_vertices: int
    part_areas_km2: tuple[float, ...]
    overlaps: tuple[OverlapFinding, ...]

    @property
    def sum_of_parts_km2(self) -> float:
        """Areas summed, which double-counts any overlap."""
        return sum(self.part_areas_km2)

    @property
    def union_area_km2(self) -> float:
        """Areas summed less the pairwise overlaps — the honest total."""
        return self.sum_of_parts_km2 - sum(o.area_km2 for o in self.overlaps)

    @property
    def is_valid(self) -> bool:
        """True if nothing downstream has to guess what the geometry means.

        Overlapping parts are a defect but not an invalidity: ADR-011 keeps the
        registry geometry as delivered and dissolves at computation time.
        """
        return not (
            self.unclosed_rings or self.self_intersecting_rings or self.out_of_range_vertices
        )


def as_ring(coordinates: Sequence[Sequence[float]]) -> Ring:
    """Normalise GeoJSON coordinate pairs into ``(lon, lat)`` tuples.

    GeoJSON carries positions as lists, and may carry a third altitude value.
    Anything past the first two ordinates is dropped: this module works in two
    dimensions and altitude is not part of an area or containment question.
    """
    return [(float(p[0]), float(p[1])) for p in coordinates]


def _exteriors(multipolygon: Sequence[Sequence[Sequence[Sequence[float]]]]) -> list[Ring]:
    return [as_ring(poly[0]) for poly in multipolygon if poly]


def describe_multipolygon(
    multipolygon: Sequence[Sequence[Sequence[Sequence[float]]]],
    *,
    overlap_bands: int = 8000,
) -> GeometryReport:
    """Validate and measure a GeoJSON MultiPolygon coordinate array.

    Args:
        multipolygon: ``coordinates`` of a GeoJSON MultiPolygon, as nested lists.
        overlap_bands: Band count for the pairwise overlap integration.

    Returns:
        A :class:`GeometryReport` carrying every check and measurement, so a
        caller can record them rather than re-deriving them.
    """
    unclosed: list[int] = []
    selfint: list[int] = []
    clockwise: list[int] = []
    out_of_range = 0
    vertices = 0
    holes = 0
    areas: list[float] = []

    for index, polygon in enumerate(multipolygon, start=1):
        if not polygon:
            continue
        exterior = as_ring(polygon[0])
        rings: list[Ring] = [exterior, *(as_ring(r) for r in polygon[1:])]
        holes += len(polygon) - 1
        for ring in rings:
            vertices += len(ring)
            out_of_range += sum(
                1 for lon, lat in ring if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0)
            )
            if not is_closed(ring):
                unclosed.append(index)
            if self_intersections(ring):
                selfint.append(index)
        if not is_counter_clockwise(exterior):
            clockwise.append(index)
        areas.append(polygon_area_m2([exterior, *rings[1:]]) / 1e6)

    exteriors = _exteriors(multipolygon)
    overlaps: list[OverlapFinding] = []
    for i in range(len(exteriors)):
        for j in range(i + 1, len(exteriors)):
            shared = intersection_area_km2(exteriors[i], exteriors[j], bands=overlap_bands)
            if shared > 0:
                overlaps.append(OverlapFinding(part_a=i + 1, part_b=j + 1, area_km2=shared))

    return GeometryReport(
        parts=len(multipolygon),
        vertices=vertices,
        holes=holes,
        unclosed_rings=tuple(sorted(set(unclosed))),
        self_intersecting_rings=tuple(sorted(set(selfint))),
        clockwise_exterior_rings=tuple(clockwise),
        out_of_range_vertices=out_of_range,
        part_areas_km2=tuple(areas),
        overlaps=tuple(overlaps),
    )
