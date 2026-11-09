"""Donor-pool construction and covariate matching.

The counterfactual is only as credible as the donor pool. This module builds
that pool explicitly and records why each candidate was admitted or excluded, so
a reviewer can challenge the pool rather than the black box.

Three eligibility rules are applied before any distance is computed:

1. **Spillover exclusion.** Regions inside the project's leakage belt are
   excluded: if the project displaced deforestation into them, they are treated
   units in disguise and would bias the effect upward.
2. **Common support.** Candidates outside the covariate range considered
   plausible for the project are excluded rather than extrapolated over.
3. **Pre-treatment coverage.** Candidates lacking enough clear pre-period
   observations are excluded, because synthetic control weights are fitted on
   the pre-period.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from groundtruth.contracts.errors import DonorPoolError
from groundtruth.contracts.types import DonorMatch

DEFAULT_COVARIATES: tuple[str, ...] = (
    "rainfall_mm",
    "elevation_m",
    "slope_deg",
    "road_distance_km",
    "population_density",
)

VALID_WGS84_CRS_NAMES: frozenset[str] = frozenset(
    {
        "OGC:CRS84",
        "CRS84",
        "EPSG:4326",
        "WGS84",
        "URN:OGC:DEF:CRS:OGC:1.3:CRS84",
        "URN:OGC:DEF:CRS:EPSG::4326",
    }
)

SUTVA_SPATIAL_CAVEAT: str = (
    "Spatial boundary verification, host-district exclusion, and the outward leakage buffer "
    "prevent direct treatment overlap and local edge spillover, but geometric non-intersection "
    "does not prove SUTVA globally (e.g. market-mediated timber/charcoal displacement or "
    "country-level macroeconomic shocks). Conversely, sharing an outer administrative border "
    "with a large host district far outside the project buffer does not automatically prove "
    "contamination and is recorded as a spatial diagnostic."
)


@dataclass(frozen=True)
class DonorSpatialDiagnostic:
    """Per-candidate spatial, topological, and provenance diagnostic record."""

    unit_id: str
    admitted: bool
    exclusion_reason: str | None = None
    official_name: str | None = None
    country_iso3: str | None = None
    adm_level: str | None = None
    shape_id: str | None = None
    source_dataset_id: str | None = None
    license: str | None = None
    verified_geometry: bool = False
    topology_valid: bool = False
    area_km2: float | None = None
    project_overlap_km2: float = 0.0
    distance_to_project_km: float | None = None
    distance_to_host_district_km: float | None = None
    is_host_district: bool = False
    overlaps_project_boundary: bool = False
    within_spatial_buffer: bool = False
    touches_host_district: bool = False
    duplicate_of_unit_id: str | None = None
    overlapping_donor_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpatialDonorAssessment:
    """Comprehensive spatial eligibility and contamination assessment for a donor pool."""

    project_unit_id: str
    spatial_buffer_km: float | None
    diagnostics: tuple[DonorSpatialDiagnostic, ...]
    exclusions: dict[str, str]
    eligible_unit_ids: tuple[str, ...]
    host_unit_ids: tuple[str, ...]
    boundary_overlapping_unit_ids: tuple[str, ...]
    buffer_excluded_unit_ids: tuple[str, ...]
    unverified_unit_ids: tuple[str, ...]
    invalid_geometry_unit_ids: tuple[str, ...]
    overlapping_donor_unit_ids: tuple[str, ...]
    host_adjacent_admitted_unit_ids: tuple[str, ...]
    sutva_caveat: str = SUTVA_SPATIAL_CAVEAT


@dataclass
class MatchingConfig:
    """Parameters controlling donor admission and ranking."""

    covariates: tuple[str, ...] = DEFAULT_COVARIATES
    weights: dict[str, float] = field(default_factory=dict)
    max_donors: int = 50
    min_donors: int = 10
    caliper_sd: float | None = 3.0
    """Exclude candidates further than this many pooled SDs on any covariate."""
    excluded_unit_ids: frozenset[str] = frozenset()
    """Units inside the leakage belt or otherwise contaminated by the treatment."""
    min_pre_observations: int = 4
    host_unit_ids: frozenset[str] = frozenset()
    """Host administrative units overlapping the project area."""
    donor_geometries: Mapping[str, Any] | None = None
    """Optional mapping from candidate unit ID to GeoJSON geometry or Feature."""
    project_geometry: Mapping[str, Any] | None = None
    """Optional GeoJSON geometry or Feature for the treated project boundary."""
    spatial_buffer_km: float | None = None
    """Outward spatial exclusion buffer (km) around the project boundary."""
    require_spatial_provenance: bool = False
    """Whether to reject candidates lacking verified spatial boundary provenance."""
    max_donor_overlap_km2: float = 1.0
    """Maximum shared area (km2) permitted between two candidate donor polygons."""
    exclude_host_adjacent: bool = False
    """Whether to exclude districts touching a host district even outside spatial_buffer_km."""

    def covariate_weights(self) -> np.ndarray:
        """Per-covariate weights as an array, defaulting to equal weighting."""
        return np.asarray([self.weights.get(c, 1.0) for c in self.covariates], dtype=float)


@dataclass(frozen=True)
class DonorPool:
    """The outcome of matching: admitted donors, exclusions, and diagnostics."""

    project_unit_id: str
    matches: tuple[DonorMatch, ...]
    covariates: tuple[str, ...]
    standardised_mean_differences: dict[str, float]

    @property
    def admitted(self) -> tuple[DonorMatch, ...]:
        """Donors that passed every eligibility rule, closest first."""
        return tuple(m for m in self.matches if m.admitted)

    @property
    def excluded(self) -> tuple[DonorMatch, ...]:
        """Candidates that were rejected, with reasons."""
        return tuple(m for m in self.matches if not m.admitted)

    @property
    def unit_ids(self) -> tuple[str, ...]:
        """Ids of admitted donors."""
        return tuple(m.unit_id for m in self.admitted)

    @property
    def worst_balance(self) -> float:
        """Largest absolute standardised mean difference after matching.

        Values above roughly 0.25 are conventionally treated as poor balance and
        should be reported as a limitation of the estimate.
        """
        if not self.standardised_mean_differences:
            return float("nan")
        return max(abs(v) for v in self.standardised_mean_differences.values())

    @property
    def is_balanced(self) -> bool:
        """True if every covariate is balanced within the conventional 0.25 SMD."""
        return bool(self.standardised_mean_differences) and self.worst_balance <= 0.25


def _standardise(
    project: np.ndarray, donors: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Z-score covariates using the pooled donor scale.

    Returns the standardised project vector, standardised donor matrix, and the
    scale used (so degenerate zero-variance covariates can be reported).
    """
    scale = donors.std(axis=0, ddof=1) if donors.shape[0] > 1 else np.ones(donors.shape[1])
    scale = np.where(scale < 1e-12, 1.0, scale)
    centre = donors.mean(axis=0)
    return (project - centre) / scale, (donors - centre) / scale, scale


def standardised_mean_difference(
    project_value: float, donor_values: np.ndarray, pooled_sd: float
) -> float:
    """Cohen-style standardised mean difference between project and donor pool."""
    if pooled_sd < 1e-12:
        return 0.0
    return float((project_value - float(np.mean(donor_values))) / pooled_sd)


def _extract_donor_geometry_and_props(
    entry: Any,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Extract a GeoJSON Geometry dict and metadata properties from a donor entry."""
    if entry is None:
        return None, {}
    if isinstance(entry, Mapping):
        etype = entry.get("type")
        if etype == "Feature":
            geom = entry.get("geometry")
            props = dict(entry.get("properties") or {})
            if isinstance(entry.get("crs"), Mapping) and "crs" not in props:
                props["crs"] = entry["crs"].get("properties", {}).get("name")
            return (dict(geom) if isinstance(geom, Mapping) else None), props
        if etype == "FeatureCollection":
            feats = entry.get("features") or []
            if len(feats) == 1 and isinstance(feats[0], Mapping):
                return _extract_donor_geometry_and_props(feats[0])
            return None, {"invalid_feature_collection": True}
        if etype in ("Polygon", "MultiPolygon"):
            props = dict(entry.get("properties") or {})
            if "crs" in entry and "crs" not in props:
                crs_val = entry["crs"]
                if isinstance(crs_val, Mapping):
                    props["crs"] = crs_val.get("properties", {}).get("name")
                else:
                    props["crs"] = str(crs_val)
            return dict(entry), props
        if "geometry" in entry:
            geom = entry.get("geometry")
            props = {k: v for k, v in entry.items() if k != "geometry"}
            if isinstance(entry.get("properties"), Mapping):
                props.update(entry["properties"])
            return (dict(geom) if isinstance(geom, Mapping) else None), props
        return dict(entry), {}
    geom_attr = getattr(entry, "geometry", None)
    props_attr = getattr(entry, "properties", None)
    return (
        dict(geom_attr) if isinstance(geom_attr, Mapping) else None,
        dict(props_attr) if isinstance(props_attr, Mapping) else {},
    )


def _validate_donor_geometry_and_provenance(
    geom: Mapping[str, Any] | None,
    props: Mapping[str, Any],
    *,
    require_spatial_provenance: bool = False,
) -> tuple[bool, bool, str | None, float]:
    """Validate donor CRS, provenance, ring closure, coordinate range, and topology.

    Returns:
        ``(has_verified_geometry, topology_valid, exclusion_reason, geodesic_area_km2)``.
    """
    if props.get("invalid_feature_collection"):
        return False, False, "invalid donor geometry: FeatureCollection must contain 1 feature", 0.0
    if geom is None or props.get("verified_geometry") is False:
        if require_spatial_provenance:
            return False, False, "missing donor spatial boundary provenance", 0.0
        return False, False, None, 0.0

    # CRS check if declared on properties or geometry
    declared_crs = props.get("crs")
    if declared_crs is not None:
        norm_crs = str(declared_crs).strip().upper().replace(" ", "")
        if not any(tok in norm_crs for tok in VALID_WGS84_CRS_NAMES):
            return (
                False,
                False,
                f"invalid donor CRS: expected OGC:CRS84 / EPSG:4326, got {declared_crs!r}",
                0.0,
            )

    # Provenance metadata check when provenance dictionary is attached
    if require_spatial_provenance and props:
        has_any_prov_key = any(
            k in props
            for k in (
                "source_dataset_id",
                "source",
                "adm_level",
                "official_name",
                "shape_name",
                "shape_id",
                "license",
            )
        )
        if has_any_prov_key:
            missing_keys: list[str] = []
            if not (props.get("source_dataset_id") or props.get("source")):
                missing_keys.append("source_dataset_id")
            if not props.get("adm_level"):
                missing_keys.append("adm_level")
            if not (props.get("official_name") or props.get("shape_name")):
                missing_keys.append("official_name")
            if not props.get("shape_id"):
                missing_keys.append("shape_id")
            if missing_keys:
                return (
                    False,
                    False,
                    f"insufficient donor boundary provenance: missing {', '.join(missing_keys)}",
                    0.0,
                )

    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype not in ("Polygon", "MultiPolygon") or not isinstance(coords, Sequence) or not coords:
        return (
            True,
            False,
            f"invalid donor geometry: expected Polygon or MultiPolygon, got {gtype!r}",
            0.0,
        )

    multipolygon: list[Any] = [coords] if gtype == "Polygon" else list(coords)
    try:
        for poly in multipolygon:
            if not isinstance(poly, Sequence) or not poly:
                return True, False, "invalid donor geometry: empty polygon ring list", 0.0
            for ring in poly:
                if not isinstance(ring, Sequence) or len(ring) < 4:
                    return (
                        True,
                        False,
                        "invalid donor geometry: ring has fewer than 4 vertices",
                        0.0,
                    )
                pts = [(float(pt[0]), float(pt[1])) for pt in ring]
                if not all(math.isfinite(x) and math.isfinite(y) for x, y in pts):
                    return True, False, "invalid donor geometry: non-finite coordinates", 0.0
                if pts[0] != pts[-1]:
                    return True, False, "invalid donor geometry: unclosed polygon ring", 0.0
                if any(abs(x) > 180.0 or abs(y) > 90.0 for x, y in pts):
                    return (
                        True,
                        False,
                        "invalid donor geometry: coordinates out of WGS84 range",
                        0.0,
                    )
    except (TypeError, ValueError, IndexError) as exc:
        return True, False, f"invalid donor geometry: malformed coordinates ({exc})", 0.0

    from groundtruth.platform.units.geodesic import describe_multipolygon

    report = describe_multipolygon(multipolygon, overlap_bands=200)
    if report.unclosed_rings:
        return True, False, "invalid donor geometry: unclosed polygon ring", 0.0
    if report.out_of_range_vertices > 0:
        return True, False, "invalid donor geometry: coordinates out of WGS84 range", 0.0
    if report.self_intersecting_rings:
        return True, False, "invalid donor geometry: self-intersecting polygon topology", 0.0
    if report.union_area_km2 <= 0.0:
        return True, False, "invalid donor geometry: zero or degenerate polygon area", 0.0

    try:
        import shapely.geometry as _shapely_geom

        sh = _shapely_geom.shape(dict(geom))
        if not sh.is_valid or sh.is_empty:
            return True, False, "invalid donor geometry: failed GEOS topological validity", 0.0
    except ImportError:
        pass
    except Exception as exc:
        return True, False, f"invalid donor geometry: topology error ({exc})", 0.0

    area_km2 = float(props.get("area_km2") or report.union_area_km2)
    return True, True, None, area_km2


def _metric_project_shape(project_geometry: Mapping[str, Any] | None) -> Any:
    """Convert a GeoJSON project geometry into a dissolved UTM 35S (EPSG:32735) shapely shape."""
    if project_geometry is None:
        return None
    geom_dict, _ = _extract_donor_geometry_and_props(project_geometry)
    if geom_dict is None:
        return None
    try:
        import pyproj
        import shapely
        import shapely.geometry as _shapely_geom
        import shapely.ops as _shapely_ops

        raw_sh = _shapely_geom.shape(geom_dict)
        if hasattr(raw_sh, "geoms"):
            dissolved = _shapely_ops.unary_union(list(raw_sh.geoms))
        else:
            dissolved = raw_sh
        proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32735", always_xy=True).transform
        return shapely.transform(dissolved, proj, interleaved=False)
    except Exception:
        return None


def _metric_donor_shape(geom_dict: Mapping[str, Any] | None) -> Any:
    """Convert a validated donor GeoJSON geometry into a UTM 35S (EPSG:32735) shapely shape."""
    if geom_dict is None:
        return None
    try:
        import pyproj
        import shapely
        import shapely.geometry as _shapely_geom

        sh = _shapely_geom.shape(dict(geom_dict))
        proj = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32735", always_xy=True).transform
        return shapely.transform(sh, proj, interleaved=False)
    except Exception:
        return None


def assess_donor_spatial_eligibility(
    project_unit_id: str,
    candidate_ids: Sequence[str],
    *,
    excluded_unit_ids: frozenset[str] = frozenset(),
    host_unit_ids: frozenset[str] = frozenset(),
    donor_geometries: Mapping[str, Any] | None = None,
    require_spatial_provenance: bool = False,
    project_geometry: Mapping[str, Any] | None = None,
    spatial_buffer_km: float | None = None,
    host_overlap_threshold_km2: float = 100.0,
    project_overlap_tolerance_km2: float = 0.001,
    max_donor_overlap_km2: float = 1.0,
    exclude_host_adjacent: bool = False,
) -> SpatialDonorAssessment:
    """Evaluate candidate donors on geometry validity, provenance, SUTVA overlap, and buffers."""
    proj_m = _metric_project_shape(project_geometry)
    parsed: dict[str, tuple[dict[str, Any] | None, dict[str, Any]]] = {}
    donor_shapes_m: dict[str, Any] = {}
    validity: dict[str, tuple[bool, bool, str | None, float]] = {}

    for uid in candidate_ids:
        entry = donor_geometries.get(uid) if donor_geometries is not None else None
        geom_dict, props = _extract_donor_geometry_and_props(entry)
        parsed[uid] = (geom_dict, props)
        has_ver, topo_ok, err_msg, area_km2 = _validate_donor_geometry_and_provenance(
            geom_dict,
            props,
            require_spatial_provenance=require_spatial_provenance,
        )
        validity[uid] = (has_ver, topo_ok, err_msg, area_km2)
        if has_ver and topo_ok and geom_dict is not None:
            donor_shapes_m[uid] = _metric_donor_shape(geom_dict)

    # Compute host district union in metric space if host shapes are available
    host_id_set = {
        uid
        for uid, sh in donor_shapes_m.items()
        if sh is not None
        and (
            uid in host_unit_ids
            or parsed[uid][1].get("is_host_district") is True
            or (
                proj_m is not None
                and (proj_m.intersection(sh).area / 1e6) >= host_overlap_threshold_km2
            )
        )
    } | set(host_unit_ids)
    host_shapes = [
        donor_shapes_m[uid] for uid in host_id_set if donor_shapes_m.get(uid) is not None
    ]
    host_union_m: Any = None
    if host_shapes:
        try:
            import shapely.ops as _shapely_ops

            host_union_m = _shapely_ops.unary_union(host_shapes)
        except Exception:
            host_union_m = None

    # Pairwise donor-to-donor overlap / duplicate detection among non-host candidates
    overlapping_map: dict[str, list[tuple[str, float]]] = {uid: [] for uid in candidate_ids}
    valid_uids = [uid for uid in candidate_ids if validity[uid][1] and uid not in host_id_set]
    for idx_a, uid_a in enumerate(valid_uids):
        props_a = parsed[uid_a][1]
        sh_a = donor_shapes_m.get(uid_a)
        area_a = float(validity[uid_a][3] or (sh_a.area / 1e6 if sh_a is not None else 0.0))
        for uid_b in valid_uids[idx_a + 1 :]:
            props_b = parsed[uid_b][1]
            sh_b = donor_shapes_m.get(uid_b)
            area_b = float(validity[uid_b][3] or (sh_b.area / 1e6 if sh_b is not None else 0.0))
            shared_km2 = 0.0
            is_explicit_dup = bool(
                props_b.get("duplicate_of_unit_id") == uid_a
                or props_a.get("duplicate_of_unit_id") == uid_b
                or (props_a.get("shape_id") and props_a.get("shape_id") == props_b.get("shape_id"))
            )
            if is_explicit_dup:
                shared_km2 = float(area_b or area_a or 100.0)
            elif sh_a is not None and sh_b is not None:
                country_a = props_a.get("country_iso3")
                country_b = props_b.get("country_iso3")
                if country_a and country_b and country_a != country_b:
                    continue
                try:
                    if sh_a.intersects(sh_b):
                        raw_shared = float(sh_a.intersection(sh_b).area / 1e6)
                        min_area = max(min(area_a, area_b), 1e-6)
                        if raw_shared > max_donor_overlap_km2 and (raw_shared / min_area) >= 0.05:
                            shared_km2 = raw_shared
                except Exception:
                    shared_km2 = 0.0
            if shared_km2 > max_donor_overlap_km2:
                overlapping_map[uid_b].append((uid_a, shared_km2))

    diagnostics: list[DonorSpatialDiagnostic] = []
    exclusions: dict[str, str] = {}
    eligible_ids: list[str] = []
    detected_hosts: list[str] = []
    boundary_overlapping_ids: list[str] = []
    buffer_excluded_ids: list[str] = []
    unverified_ids: list[str] = []
    invalid_geom_ids: list[str] = []
    overlapping_donor_ids_list: list[str] = []
    host_adjacent_admitted: list[str] = []

    for uid in candidate_ids:
        geom_dict, props = parsed[uid]
        has_ver, topo_ok, geom_err, area_km2 = validity[uid]
        sh_m = donor_shapes_m.get(uid)

        ov_km2 = float(props.get("project_overlap_km2", 0.0) or 0.0)
        dist_proj_km: float | None = (
            float(props["distance_to_project_km"])
            if props.get("distance_to_project_km") is not None
            else None
        )
        dist_host_km: float | None = (
            float(props["distance_to_host_district_km"])
            if props.get("distance_to_host_district_km") is not None
            else None
        )

        if proj_m is not None and sh_m is not None:
            try:
                ov_km2 = float(proj_m.intersection(sh_m).area / 1e6)
                dist_proj_km = float(proj_m.distance(sh_m) / 1000.0)
                area_km2 = float(sh_m.area / 1e6)
            except Exception:
                pass

        if host_union_m is not None and sh_m is not None:
            try:
                dist_host_km = float(host_union_m.distance(sh_m) / 1000.0)
            except Exception:
                dist_host_km = None

        is_host = bool(
            uid in host_unit_ids
            or props.get("is_host_district") is True
            or (proj_m is not None and sh_m is not None and ov_km2 >= host_overlap_threshold_km2)
        )
        overlaps_proj = bool(not is_host and ov_km2 > project_overlap_tolerance_km2)
        within_buffer = bool(
            not is_host
            and not overlaps_proj
            and spatial_buffer_km is not None
            and dist_proj_km is not None
            and dist_proj_km <= spatial_buffer_km
        )
        touches_host = bool(
            not is_host
            and (
                props.get("touches_host_district") is True
                or (dist_host_km is not None and dist_host_km < 0.5)
            )
        )
        dup_of = props.get("duplicate_of_unit_id")
        donor_overlaps = overlapping_map.get(uid, [])

        reason: str | None = None
        explicitly_in_geoms = donor_geometries is not None and uid in donor_geometries
        if uid == project_unit_id:
            reason = "candidate is the treated project unit itself (SUTVA violation)"
        elif is_host:
            detected_hosts.append(uid)
            reason = "candidate is a host district overlapping the project area (SUTVA violation)"
        elif geom_err is not None and (explicitly_in_geoms or uid not in excluded_unit_ids):
            if not has_ver:
                unverified_ids.append(uid)
            else:
                invalid_geom_ids.append(uid)
            reason = geom_err
        elif donor_overlaps:
            other_uid, shared_area = donor_overlaps[0]
            overlapping_donor_ids_list.append(uid)
            if overlaps_proj:
                boundary_overlapping_ids.append(uid)
            reason = (
                f"overlapping donor geometry with {other_uid!r} "
                f"({shared_area:.2f} km2 shared; duplicate or non-disjoint control unit)"
            )
        elif overlaps_proj:
            boundary_overlapping_ids.append(uid)
            reason = (
                f"candidate boundary overlaps project area by {ov_km2:.2f} km2 (SUTVA violation)"
            )
        elif within_buffer and dist_proj_km is not None and spatial_buffer_km is not None:
            buffer_excluded_ids.append(uid)
            reason = (
                f"inside {spatial_buffer_km:g} km spatial exclusion buffer of project boundary "
                f"(distance {dist_proj_km:.2f} km; potential spillover contamination)"
            )
        elif uid in excluded_unit_ids:
            buffer_excluded_ids.append(uid)
            reason = "inside project leakage belt (potential spillover contamination)"
        elif geom_err is not None:
            if not has_ver:
                unverified_ids.append(uid)
            else:
                invalid_geom_ids.append(uid)
            reason = geom_err
        elif exclude_host_adjacent and touches_host:
            buffer_excluded_ids.append(uid)
            reason = (
                "adjacent to a project host district (excluded under strict host-adjacency setting)"
            )

        admitted = reason is None
        if admitted:
            eligible_ids.append(uid)
            if touches_host:
                host_adjacent_admitted.append(uid)
        else:
            assert reason is not None
            exclusions[uid] = reason

        diagnostics.append(
            DonorSpatialDiagnostic(
                unit_id=uid,
                admitted=admitted,
                exclusion_reason=reason,
                official_name=props.get("official_name") or props.get("shape_name"),
                country_iso3=props.get("country_iso3"),
                adm_level=props.get("adm_level"),
                shape_id=props.get("shape_id"),
                source_dataset_id=props.get("source_dataset_id") or props.get("source"),
                license=props.get("license"),
                verified_geometry=has_ver,
                topology_valid=topo_ok,
                area_km2=round(area_km2, 3) if area_km2 > 0 else None,
                project_overlap_km2=round(ov_km2, 3),
                distance_to_project_km=(
                    round(dist_proj_km, 3) if dist_proj_km is not None else None
                ),
                distance_to_host_district_km=(
                    round(dist_host_km, 3) if dist_host_km is not None else None
                ),
                is_host_district=is_host,
                overlaps_project_boundary=overlaps_proj or is_host,
                within_spatial_buffer=within_buffer,
                touches_host_district=touches_host,
                duplicate_of_unit_id=str(dup_of) if dup_of else None,
                overlapping_donor_ids=tuple(o[0] for o in donor_overlaps),
            )
        )

    return SpatialDonorAssessment(
        project_unit_id=project_unit_id,
        spatial_buffer_km=spatial_buffer_km,
        diagnostics=tuple(diagnostics),
        exclusions=exclusions,
        eligible_unit_ids=tuple(eligible_ids),
        host_unit_ids=tuple(detected_hosts),
        boundary_overlapping_unit_ids=tuple(boundary_overlapping_ids),
        buffer_excluded_unit_ids=tuple(buffer_excluded_ids),
        unverified_unit_ids=tuple(unverified_ids),
        invalid_geometry_unit_ids=tuple(invalid_geom_ids),
        overlapping_donor_unit_ids=tuple(overlapping_donor_ids_list),
        host_adjacent_admitted_unit_ids=tuple(host_adjacent_admitted),
    )


def validate_donor_eligibility(
    project_unit_id: str,
    candidate_ids: Sequence[str],
    *,
    excluded_unit_ids: frozenset[str] = frozenset(),
    host_unit_ids: frozenset[str] = frozenset(),
    donor_geometries: Mapping[str, Any] | None = None,
    require_spatial_provenance: bool = False,
    project_geometry: Mapping[str, Any] | None = None,
    spatial_buffer_km: float | None = None,
    host_overlap_threshold_km2: float = 100.0,
    project_overlap_tolerance_km2: float = 0.001,
    max_donor_overlap_km2: float = 1.0,
    exclude_host_adjacent: bool = False,
) -> dict[str, str]:
    """Validate candidate donor units against SUTVA, geometry topology, and provenance rules.

    Checks that no candidate is the treated project unit itself, a host district
    overlapping the project boundary, overlapping the project area, within the
    configurable spatial exclusion buffer, inside the project leakage belt,
    overlapping another donor polygon, or lacking verified spatial boundary
    provenance when required.

    Args:
        project_unit_id: Identifier of the treated project unit.
        candidate_ids: Candidate donor unit identifiers to validate.
        excluded_unit_ids: Units inside the project leakage belt.
        host_unit_ids: Host administrative units overlapping the project area.
        donor_geometries: Optional mapping from unit ID to spatial geometry/Feature.
        require_spatial_provenance: Whether to reject candidates without verified geometry.
        project_geometry: Optional GeoJSON geometry/Feature of the treated project boundary.
        spatial_buffer_km: Optional outward spatial exclusion buffer (km) around the project.
        host_overlap_threshold_km2: Overlap area (km2) above which a unit is a host district.
        project_overlap_tolerance_km2: Overlap area (km2) above which boundary overlap fires.
        max_donor_overlap_km2: Max shared area (km2) before flagging overlapping donor polygons.
        exclude_host_adjacent: Whether to exclude units touching a host district outside buffer.

    Returns:
        Mapping of ``unit_id -> exclusion_reason`` for every ineligible candidate.
    """
    assessment = assess_donor_spatial_eligibility(
        project_unit_id=project_unit_id,
        candidate_ids=candidate_ids,
        excluded_unit_ids=excluded_unit_ids,
        host_unit_ids=host_unit_ids,
        donor_geometries=donor_geometries,
        require_spatial_provenance=require_spatial_provenance,
        project_geometry=project_geometry,
        spatial_buffer_km=spatial_buffer_km,
        host_overlap_threshold_km2=host_overlap_threshold_km2,
        project_overlap_tolerance_km2=project_overlap_tolerance_km2,
        max_donor_overlap_km2=max_donor_overlap_km2,
        exclude_host_adjacent=exclude_host_adjacent,
    )
    return assessment.exclusions


def match_donors(
    project_unit_id: str,
    project_covariates: dict[str, float],
    candidate_covariates: dict[str, dict[str, float]],
    config: MatchingConfig | None = None,
    *,
    candidate_pre_observations: dict[str, int] | None = None,
) -> DonorPool:
    """Rank and filter candidate control regions for a project.

    Args:
        project_unit_id: Id of the treated unit.
        project_covariates: Covariate values for the project.
        candidate_covariates: Covariate values per candidate donor.
        config: Matching parameters.
        candidate_pre_observations: Clear pre-period observation counts per
            candidate, used to enforce the coverage rule.

    Returns:
        A :class:`DonorPool` with admitted donors sorted by covariate distance
        and every exclusion recorded with its reason.

    Raises:
        DonorPoolError: if fewer than ``config.min_donors`` candidates survive.
            Refusing to estimate is the correct behaviour here; an estimate
            built on three donors is not defensible.
    """
    cfg = config or MatchingConfig()
    if not candidate_covariates:
        raise DonorPoolError(f"no candidate donors supplied for {project_unit_id!r}")

    missing = [c for c in cfg.covariates if c not in project_covariates]
    if missing:
        raise DonorPoolError(f"project is missing covariates: {missing}")

    usable_ids = [
        uid for uid, cov in candidate_covariates.items() if all(c in cov for c in cfg.covariates)
    ]
    if not usable_ids:
        raise DonorPoolError("no candidate has the full covariate set required for matching")

    spatial_ineligible = validate_donor_eligibility(
        project_unit_id=project_unit_id,
        candidate_ids=tuple(usable_ids),
        excluded_unit_ids=cfg.excluded_unit_ids,
        host_unit_ids=cfg.host_unit_ids,
        donor_geometries=cfg.donor_geometries,
        require_spatial_provenance=cfg.require_spatial_provenance,
        project_geometry=cfg.project_geometry,
        spatial_buffer_km=cfg.spatial_buffer_km,
        max_donor_overlap_km2=cfg.max_donor_overlap_km2,
        exclude_host_adjacent=cfg.exclude_host_adjacent,
    )

    project_vec = np.asarray([project_covariates[c] for c in cfg.covariates], dtype=float)
    donor_mat = np.asarray(
        [[candidate_covariates[uid][c] for c in cfg.covariates] for uid in usable_ids],
        dtype=float,
    )
    z_project, z_donors, scale = _standardise(project_vec, donor_mat)
    weights = cfg.covariate_weights()

    deltas = z_donors - z_project
    distances = np.sqrt(np.sum(weights * deltas**2, axis=1))

    matches: list[DonorMatch] = []
    for i, uid in enumerate(usable_ids):
        cov = {c: float(candidate_covariates[uid][c]) for c in cfg.covariates}
        reason: str | None = None

        if uid in spatial_ineligible:
            reason = spatial_ineligible[uid]
        elif cfg.caliper_sd is not None and np.max(np.abs(deltas[i])) > cfg.caliper_sd:
            worst = cfg.covariates[int(np.argmax(np.abs(deltas[i])))]
            reason = (
                f"outside common support: {worst} differs by "
                f"{abs(deltas[i][int(np.argmax(np.abs(deltas[i])))]):.2f} SD "
                f"(caliper {cfg.caliper_sd:.2f})"
            )
        elif (
            candidate_pre_observations is not None
            and candidate_pre_observations.get(uid, 0) < cfg.min_pre_observations
        ):
            reason = (
                f"insufficient clear pre-treatment observations "
                f"({candidate_pre_observations.get(uid, 0)} < {cfg.min_pre_observations})"
            )

        matches.append(
            DonorMatch(
                unit_id=uid,
                distance=float(distances[i]),
                covariates=cov,
                admitted=reason is None,
                exclusion_reason=reason,
            )
        )

    matches.sort(key=lambda m: (not m.admitted, m.distance))

    admitted = [m for m in matches if m.admitted]
    if len(admitted) > cfg.max_donors:
        capped: list[DonorMatch] = []
        for rank, m in enumerate(admitted):
            if rank < cfg.max_donors:
                capped.append(m)
            else:
                capped.append(
                    m.model_copy(
                        update={
                            "admitted": False,
                            "exclusion_reason": (
                                f"ranked {rank + 1} by covariate distance, beyond the "
                                f"max_donors cap of {cfg.max_donors}"
                            ),
                        }
                    )
                )
        matches = capped + [m for m in matches if not m.admitted]
        admitted = [m for m in matches if m.admitted]

    if len(admitted) < cfg.min_donors:
        raise DonorPoolError(
            f"only {len(admitted)} admissible donors for {project_unit_id!r}; "
            f"{cfg.min_donors} required. Widen the search region or relax the caliper, but "
            "do not estimate on an under-powered pool."
        )

    smd = {
        c: standardised_mean_difference(
            project_covariates[c],
            np.asarray([m.covariates[c] for m in admitted], dtype=float),
            float(scale[j]),
        )
        for j, c in enumerate(cfg.covariates)
    }

    return DonorPool(
        project_unit_id=project_unit_id,
        matches=tuple(matches),
        covariates=cfg.covariates,
        standardised_mean_differences=smd,
    )
