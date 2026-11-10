"""Backward-compatible re-export of :mod:`groundtruth.contracts.geodesic`.

Pure dependency-free geodesic geometry helpers live in :mod:`groundtruth.contracts.geodesic`
so both :mod:`groundtruth.engine` and :mod:`groundtruth.platform` can consume them without
violating the unidirectional engine-platform boundary.
"""

from groundtruth.contracts.geodesic import (
    GeometryReport,
    OverlapFinding,
    as_ring,
    bbox,
    describe_multipolygon,
    intersection_area_km2,
    is_closed,
    is_counter_clockwise,
    point_in_ring,
    polygon_area_m2,
    ring_area_m2,
    segments_intersect,
    self_intersections,
    signed_planar_area,
)

__all__ = [
    "GeometryReport",
    "OverlapFinding",
    "as_ring",
    "bbox",
    "describe_multipolygon",
    "intersection_area_km2",
    "is_closed",
    "is_counter_clockwise",
    "point_in_ring",
    "polygon_area_m2",
    "ring_area_m2",
    "segments_intersect",
    "self_intersections",
    "signed_planar_area",
]
