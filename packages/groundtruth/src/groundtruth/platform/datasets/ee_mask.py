"""The ADR-011 eligibility mask as an Earth Engine raster.

**Owner: Bhumi.** The rule is ADR-011's; the raster form of it, with the erosion
and area conventions below, is
``docs/decisions/ADR-011-amendment-1-raster-units.md``, agreed by both owners
(V6, agreed with Viraj (C4), 2026-11-05).

A masked district at 30 m would be millions of polygon vertices, too large to carry
in a request. So a unit keeps its **outline** as ordinary GeoJSON, and the mask
travels beside it as a small plain-data **recipe** in a foreign GeoJSON member
(:data:`MASK_MEMBER`). The recipe names every pinned input and threshold, so it is
enough to rebuild the same raster, and because it sits inside ``UnitRef.geometry``
it enters every geometry hash without a contract change.

The chain, in ADR-011's order:

1. ``inside``: 1 within the outline, 0 elsewhere.
2. ``inside AND ecoregions AND forest AND NOT water AND NOT protected AND NOT
   carbon-projects``, on the pinned grid. Pixels outside the outline are therefore
   already 0.
3. Erode with a circular kernel of ``radius_pixels``, applied **last**. Because
   step 2 set the outside to 0, district edges erode exactly as mask edges do.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from groundtruth.contracts.identifiers import spec_hash
from groundtruth.platform.config import REPO_ROOT
from groundtruth.platform.datasets.resilience import PermanentError

MASK_MEMBER = "groundtruth_mask"
"""Foreign GeoJSON member carrying a unit's mask recipe."""

MASK_KIND = "adr011-raster-mask"
MASK_VERSION = 1


def unit_geometry(outline: Mapping[str, Any], recipe: Mapping[str, Any]) -> dict[str, Any]:
    """An outline plus the recipe of the mask applied inside it."""
    return {"type": outline["type"], "coordinates": outline["coordinates"], MASK_MEMBER: recipe}


def split_unit_geometry(
    geometry: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any] | None]:
    """Separate plain GeoJSON, which Earth Engine accepts, from the mask recipe.

    Returns:
        ``(outline, recipe)``. ``recipe`` is ``None`` for a plain geometry, such as a
        registry boundary observed without the mask.
    """
    outline = {key: value for key, value in geometry.items() if key != MASK_MEMBER}
    return outline, geometry.get(MASK_MEMBER)


def geometry_file_fingerprint(path: str | Path) -> str:
    """Hash of the single geometry in a committed GeoJSON file."""
    return spec_hash(_load_geometry(path))


def _load_geometry(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = REPO_ROOT / resolved
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise PermanentError(f"carbon-project geometry {path} could not be read") from None
    if payload.get("type") == "FeatureCollection":
        features = payload.get("features") or []
        if len(features) != 1:
            raise PermanentError(f"carbon-project geometry {path} must hold exactly one feature")
        payload = features[0]
    if payload.get("type") == "Feature":
        payload = payload.get("geometry") or {}
    if payload.get("type") not in ("Polygon", "MultiPolygon"):
        raise PermanentError(f"carbon-project geometry {path} must be a Polygon or MultiPolygon")
    return dict(payload)


def _painted(ee: Any, features: Any) -> Any:
    """1 where any of ``features`` falls, 0 elsewhere."""
    return ee.Image.constant(0).byte().paint(features, 1)


def _carbon_projects(ee: Any, projects: list[Mapping[str, Any]]) -> Any:
    features = []
    for project in projects:
        geometry = _load_geometry(project["path"])
        if spec_hash(geometry) != project["blake2b"]:
            raise PermanentError(
                f"carbon-project geometry {project['path']} no longer matches the hash pinned in "
                "the unit's mask recipe"
            )
        features.append(ee.Feature(ee.Geometry(geometry, None, True, False)))
    return ee.FeatureCollection(features)


def protected_areas(ee: Any, spec: Mapping[str, Any]) -> Any:
    """The WDPA polygons ADR-011 subtracts.

    ``STATUS_YR <= 2000`` includes ``0``, which means *unknown* and is subtracted on
    purpose. Only the listed statuses count: ``Proposed``, ``Not Reported`` and
    ``Adopted`` are not subtracted (V7, agreed with Viraj (C4), 2026-11-05).
    """
    return (
        ee.FeatureCollection(spec["asset"])
        .filter(ee.Filter.lte("STATUS_YR", int(spec["status_year_max"])))
        .filter(ee.Filter.inList("STATUS", list(spec["status_values"])))
    )


def baseline_layers(ee: Any, recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Each input layer as a 0/1 image, before any combination."""
    forest = recipe["baseline_forest"]
    water = recipe["permanent_water"]
    ecoregions = recipe["target_ecoregions"]
    layers = {
        "forest": ee.Image(forest["asset"])
        .select(forest["band"])
        .unmask(0)
        .gte(float(forest["min_percent"])),
        # Water is masked where GSW has no data; that is "not water", not "unknown".
        "water": ee.Image(water["asset"])
        .select(water["band"])
        .unmask(0)
        .gte(float(water["min_percent"])),
        "ecoregions": _painted(
            ee,
            ee.FeatureCollection(ecoregions["asset"]).filter(
                ee.Filter.inList(ecoregions["property"], list(ecoregions["names"]))
            ),
        ),
        "protected": _painted(ee, protected_areas(ee, recipe["protected_areas"])),
    }
    projects = list(recipe.get("carbon_projects") or [])
    layers["carbon"] = (
        _painted(ee, _carbon_projects(ee, projects)) if projects else ee.Image.constant(0).byte()
    )
    return layers


def _inside(ee: Any, region: Any) -> Any:
    return _painted(ee, ee.FeatureCollection([ee.Feature(region)]))


def forest_images(ee: Any, region: Any, recipe: Mapping[str, Any]) -> tuple[Any, Any]:
    """``(forest in the region, forest in the region and the target ecoregions)``.

    Evaluated before any subtraction, as ADR-011's >=50% rule requires.
    """
    layers = baseline_layers(ee, recipe)
    forest = _inside(ee, region).And(layers["forest"])
    in_ecoregions = forest.And(layers["ecoregions"])
    return _on_grid(forest, recipe), _on_grid(in_ecoregions, recipe)


def _on_grid(image: Any, recipe: Mapping[str, Any]) -> Any:
    return image.reproject(crs=recipe["crs"], scale=float(recipe["scale_m"]))


def adr011_mask(ee: Any, region: Any, recipe: Mapping[str, Any]) -> Any:
    """The eroded eligibility mask: 1 for an eligible pixel, 0 otherwise.

    Raises:
        PermanentError: if the recipe is not one this code can build.
    """
    if recipe.get("kind") != MASK_KIND or recipe.get("version") != MASK_VERSION:
        raise PermanentError(
            f"unknown unit mask recipe {recipe.get('kind')!r} version {recipe.get('version')!r}"
        )
    layers = baseline_layers(ee, recipe)
    eligible = (
        _inside(ee, region)
        .And(layers["ecoregions"])
        .And(layers["forest"])
        .And(layers["water"].Not())
        .And(layers["protected"].Not())
        .And(layers["carbon"].Not())
    )
    erosion = recipe["erosion"]
    eroded = _on_grid(eligible.unmask(0), recipe).focalMin(
        radius=int(erosion["radius_pixels"]),
        kernelType=str(erosion["kernel"]),
        units="pixels",
    )
    return _on_grid(eroded, recipe)


__all__ = [
    "MASK_KIND",
    "MASK_MEMBER",
    "MASK_VERSION",
    "adr011_mask",
    "baseline_layers",
    "forest_images",
    "geometry_file_fingerprint",
    "protected_areas",
    "split_unit_geometry",
    "unit_geometry",
]
