"""Loading and validating a committed registry boundary artifact.

The treated unit starts here. ADR-011 builds it as
``registry_boundary ∩ mask ⊖ inward_buffer(300 m)``, and this module supplies
the first term: the polygon as the registry published it, with its provenance
and with the checks that decide whether it can be used at all.

It does not mask anything. Masking needs pinned rasters and a geometry engine
(:mod:`groundtruth.platform.units.provider`).

**The boundary is the boundary.** Nothing here trims, simplifies, dissolves or
rescales a registry geometry. Where a boundary has a defect — the Kariba
artifact has a 0.29 km² overlap between two adjacent parcels — it is reported
and carried, never repaired, because a repaired boundary is no longer the one
the registry published and no longer audits against it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.request import UnitRef
from groundtruth.logging import get_logger
from groundtruth.platform.units.geodesic import GeometryReport, describe_multipolygon

logger = get_logger("units.boundary")

HECTARES_PER_KM2 = 100.0


@dataclass(frozen=True, slots=True)
class RegistryBoundary:
    """A project boundary as published by a registry, with its checks attached."""

    case_id: str
    path: Path
    geometry: dict[str, Any]
    properties: dict[str, Any]
    report: GeometryReport
    content_sha256: str

    @property
    def boundary_area_km2(self) -> float:
        """Union area of the boundary, with any part overlap removed once."""
        return self.report.union_area_km2

    @property
    def boundary_area_ha(self) -> float:
        """Union area in hectares, the unit registries publish."""
        return self.boundary_area_km2 * HECTARES_PER_KM2

    def as_unit_ref(self) -> UnitRef:
        """The treated unit *before* masking.

        ``area_ha`` is the boundary area, not an eligible area: ADR-011 defines
        ``UnitRef.area_ha`` as the eligible area after masking, and that is set
        by the masking provider once it has run. Handing this to matching as if
        it were the eligible area would put the wrong number in the area band.
        """
        return UnitRef(
            unit_id=self.case_id,
            geometry=self.geometry,
            area_ha=self.boundary_area_ha,
            attributes={
                "boundary_area_km2": self.boundary_area_km2,
                "parts": float(self.report.parts),
                "vertices": float(self.report.vertices),
            },
        )


def _multipolygon_coordinates(geometry: dict[str, Any]) -> list[list[list[tuple[float, float]]]]:
    kind = geometry.get("type")
    if kind == "MultiPolygon":
        return geometry["coordinates"]
    if kind == "Polygon":
        return [geometry["coordinates"]]
    raise DataUnavailableError(f"boundary geometry must be a Polygon or MultiPolygon, got {kind!r}")


def load_registry_boundary(path: str | Path, *, case_id: str | None = None) -> RegistryBoundary:
    """Load a committed boundary artifact and validate its geometry.

    Args:
        path: Path to the GeoJSON artifact, e.g.
            ``cases/boundaries/kariba-redd.geojson``.
        case_id: Overrides the ``case_id`` property in the file.

    Returns:
        The boundary with a full :class:`GeometryReport`.

    Raises:
        DataUnavailableError: if the file is missing, unparseable, carries no
            feature, or fails a geometry check that makes masking ambiguous.
            Issue #2 owns obtaining boundaries; a missing one is a data
            dependency, not a bug here.
    """
    p = Path(path)
    if not p.exists():
        raise DataUnavailableError(
            f"no boundary artifact at {p}. Boundaries come from the registry record and are "
            "obtained under issue #2; they are never redrawn to unblock a run."
        )

    raw = p.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DataUnavailableError(f"{p} is not valid GeoJSON: {exc}") from exc

    if payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
        if len(features) != 1:
            raise DataUnavailableError(
                f"{p} carries {len(features)} features; a case boundary must be exactly one"
            )
        feature = features[0]
    elif payload.get("type") == "Feature":
        feature = payload
    else:
        raise DataUnavailableError(f"{p} must be a Feature or FeatureCollection")

    geometry = feature.get("geometry") or {}
    properties = feature.get("properties") or {}
    coordinates = _multipolygon_coordinates(geometry)
    report = describe_multipolygon(coordinates)

    if not report.is_valid:
        raise DataUnavailableError(
            f"{p} fails geometry validation: "
            f"unclosed rings {report.unclosed_rings}, "
            f"self-intersecting rings {report.self_intersecting_rings}, "
            f"{report.out_of_range_vertices} out-of-range vertices"
        )

    if report.overlaps:
        shared = sum(o.area_km2 for o in report.overlaps)
        logger.warning(
            "boundary parts overlap; area computed on the union, geometry left as delivered",
            extra={
                "path": str(p),
                "overlapping_pairs": len(report.overlaps),
                "shared_area_km2": round(shared, 4),
            },
        )

    resolved = case_id or properties.get("case_id")
    if not resolved:
        raise DataUnavailableError(f"{p} has no case_id property and none was supplied")

    return RegistryBoundary(
        case_id=str(resolved),
        path=p,
        geometry=geometry,
        properties=properties,
        report=report,
        content_sha256=hashlib.sha256(raw).hexdigest(),
    )
