"""The committed run settings, and the gate that refuses a real generation.

ADR-011 lists parameters that must be fixed and committed **before any candidate
count is seen**. ``cases/run_parameters/<case>.yaml`` is where they live. A setting
that nobody has decided is ``null`` in that file, and :func:`generation_blockers`
turns every ``null`` into a named blocker with the question behind it. There are no
defaults anywhere on this path: a guessed projection or a guessed road source would
produce a unit set nobody can reproduce, and produce it silently.

The check runs before any Earth Engine call, so a run that cannot go ahead costs
nothing and reveals nothing.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from groundtruth.contracts.errors import ConfigurationError, DataUnavailableError
from groundtruth.platform.cases.registry import CaseDefinition
from groundtruth.platform.config import REPO_ROOT
from groundtruth.platform.datasets.covariates import (
    MASK_RULES,
    ROAD_SOURCE_OSM,
    ROAD_SOURCES,
    RoadSource,
)
from groundtruth.platform.units.carbon_projects import CarbonProjectSnapshot, load_carbon_snapshot
from groundtruth.platform.units.spec import LADDER, RunParameters

ENGINE_TRANSFORMS_CAPABILITY = "covariate_transforms_in_matching"
"""The ``describe_engine()["implemented"]`` flag V9(a) waits for."""

RASTER_RESAMPLING = ("nearest",)
"""Only nearest-neighbour is implemented: Earth Engine's default, and exact for 0/1 layers."""

_RELEASE = re.compile(r"^\d{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_SETTINGS: Mapping[str, str] = {
    "projection": (
        "ADR-011 open parameter: the equal-area CRS for every buffer and area, as an EPSG code "
        "or WKT. Proposed: Africa Albers Equal Area. Fix before any candidate count."
    ),
    "raster_scale_m": "V6: the mask's pixel size. Agreed value is 30.",
    "raster_reducer": (
        "ADR-011 open parameter: how rasters resample onto the mask's grid. Implemented: nearest."
    ),
    "simplification_max_error_m": (
        "ADR-011 open parameter: maxError for the leakage-belt buffer, in metres."
    ),
    "ecoregion_names.rung1": "V5: literal ECO_NAME strings, copied from the names-only listing.",
    "ecoregion_names.rung2": "V5: literal ECO_NAME strings, copied from the names-only listing.",
    "ecoregion_names.rung3": "V5: rung 2's ecoregions, in more countries (MWI, TZA).",
    "treated_ecoregion_rung": (
        "New question for Viraj: which rung's ecoregions define the TREATED unit's mask. ADR-011 "
        "measures the treated area once, before the ladder, so it cannot follow the rung."
    ),
    "wdpa_release": "B6: the dated WDPA snapshot, YYYYMM, from the names-only listing.",
    "carbon_project_snapshot": "B3: path to the committed snapshot file.",
    "road_source": f"V1: which road layer is used, one of {list(ROAD_SOURCES)}.",
    "road_asset": "V1: the id of the uploaded Earth Engine asset. See docs/data/groads-upload.md.",
    "road_source_sha256": "V1: sha256 of the source file that was uploaded.",
    "road_upload_date": "V1: the upload date, YYYY-MM-DD.",
    "road_distance_scale_m": (
        "New question for Viraj: V4 says native scale, but a vector road layer has none. The "
        "pixel size of the distance raster, in metres."
    ),
    "road_search_radius_km": (
        "New question for Viraj: how far to search for a road. A pixel beyond this makes the "
        "unit's road distance refuse rather than understate."
    ),
    "native_scale_mask_rule": (
        "New question for Viraj: V4 fixes the native scale but not how a 30 m mask meets a "
        f"coarser pixel. One of {list(MASK_RULES)}."
    ),
}


@dataclass(frozen=True, slots=True)
class Blocker:
    """One thing standing between the current state and a real generation run."""

    name: str
    question: str

    def __str__(self) -> str:
        return f"{self.name}: {self.question}"


def _is_unset(value: Any) -> bool:
    return value is None or (isinstance(value, str | list | tuple) and not value)


def _lookup(raw: Mapping[str, Any], dotted: str) -> Any:
    value: Any = raw
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, Mapping) else None
    return value


@dataclass(frozen=True, slots=True)
class RunSettings:
    """A case's committed run settings, as written."""

    path: Path
    content_sha256: str
    raw: Mapping[str, Any]

    def missing(self) -> list[Blocker]:
        """Every required setting that is still unset, and every invalid one."""
        blockers = [
            Blocker(name, question)
            for name, question in REQUIRED_SETTINGS.items()
            if _is_unset(_lookup(self.raw, name))
        ]
        blockers.extend(self._invalid())
        return blockers

    def _invalid(self) -> list[Blocker]:
        problems: list[Blocker] = []

        def check(name: str, ok: bool, expected: str) -> None:
            value = _lookup(self.raw, name)
            if not _is_unset(value) and not ok:
                problems.append(Blocker(name, f"{value!r} is not valid: {expected}."))

        raw = self.raw
        release = str(raw.get("wdpa_release"))
        check("wdpa_release", bool(_RELEASE.fullmatch(release)), "expected YYYYMM")
        check("road_source", raw.get("road_source") in ROAD_SOURCES, f"one of {ROAD_SOURCES}")
        sha = str(raw.get("road_source_sha256")).lower()
        check("road_source_sha256", bool(_SHA256.fullmatch(sha)), "expected 64 hex characters")
        check("road_upload_date", _is_iso_date(raw.get("road_upload_date")), "expected YYYY-MM-DD")
        check(
            "native_scale_mask_rule",
            raw.get("native_scale_mask_rule") in MASK_RULES,
            f"one of {MASK_RULES}",
        )
        check(
            "raster_reducer",
            raw.get("raster_reducer") in RASTER_RESAMPLING,
            f"one of {RASTER_RESAMPLING}",
        )
        for name in (
            "raster_scale_m",
            "road_distance_scale_m",
            "road_search_radius_km",
        ):
            check(name, _is_positive(raw.get(name)), "expected a positive number")
        check(
            "simplification_max_error_m",
            _is_positive(raw.get("simplification_max_error_m")),
            "expected a positive number",
        )
        rung_keys = {rung.ecoregion_key for rung in LADDER}
        check(
            "treated_ecoregion_rung",
            raw.get("treated_ecoregion_rung") in rung_keys,
            f"one of {sorted(rung_keys)}",
        )
        if raw.get("road_source") == ROAD_SOURCE_OSM and _is_unset(raw.get("road_fallback_reason")):
            # V1: the fallback is allowed only as a recorded departure.
            problems.append(
                Blocker(
                    "road_fallback_reason",
                    "V1: current OSM is a fallback, only if the gROADS upload proved impossible. "
                    "Say why here, and record the departure in docs/science/limitations.md.",
                )
            )
        return problems

    def parameters(self, case: CaseDefinition, snapshot: CarbonProjectSnapshot) -> RunParameters:
        """The validated :class:`RunParameters`.

        Raises:
            ConfigurationError: if any setting is unset or invalid. Nothing is defaulted.
        """
        missing = self.missing()
        if missing:
            raise ConfigurationError(
                f"{self.path} is not complete: " + "; ".join(str(b) for b in missing)
            )
        if case.min_donors is None or case.max_donors is None:
            raise ConfigurationError(
                f"case {case.case_id!r} must set min_donors and max_donors (ADR-011)"
            )
        raw = self.raw
        names = raw["ecoregion_names"]
        parameters = RunParameters(
            projection=str(raw["projection"]),
            raster_scale_m=float(raw["raster_scale_m"]),
            raster_reducer=str(raw["raster_reducer"]),
            simplification_max_error_m=float(raw["simplification_max_error_m"]),
            ecoregion_names={key: tuple(str(n) for n in values) for key, values in names.items()},
            wdpa_release=str(raw["wdpa_release"]),
            carbon_registry_snapshot_date=snapshot.snapshot_date,
            pool_size=case.donor_pool_size,
            min_donors=case.min_donors,
            max_donors=case.max_donors,
            excluded_carbon_project_districts=snapshot.excluded_districts,
        )
        parameters.validate()
        return parameters

    def road_source(self) -> RoadSource:
        """The explicitly named road source.

        Raises:
            ConfigurationError: if any road setting is unset.
        """
        names = (
            "road_source",
            "road_asset",
            "road_source_sha256",
            "road_upload_date",
            "road_distance_scale_m",
            "road_search_radius_km",
        )
        unset = [name for name in names if _is_unset(self.raw.get(name))]
        if unset:
            raise ConfigurationError(f"{self.path}: road settings are unset: {unset}")
        return RoadSource(
            source=str(self.raw["road_source"]),
            asset=str(self.raw["road_asset"]),
            source_sha256=str(self.raw["road_source_sha256"]).lower(),
            upload_date=str(self.raw["road_upload_date"]),
            distance_scale_m=float(self.raw["road_distance_scale_m"]),
            search_radius_km=float(self.raw["road_search_radius_km"]),
        )

    def covariate_settings(self) -> dict[str, Any]:
        """The covariate settings as executed, for the manifest."""
        return {
            name: self.raw.get(name)
            for name in (
                "road_source",
                "road_asset",
                "road_source_sha256",
                "road_upload_date",
                "road_distance_scale_m",
                "road_search_radius_km",
                "road_fallback_reason",
                "native_scale_mask_rule",
                "treated_ecoregion_rung",
            )
        }


def _is_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        return False
    return True


def _is_positive(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and float(value) > 0.0


def run_settings_path(case_id: str) -> Path:
    """Where a case's committed run settings live."""
    return REPO_ROOT / "cases" / "run_parameters" / f"{case_id}.yaml"


def load_run_settings(path: str | Path) -> RunSettings:
    """Read a run-settings file. Unset values are fine here; the gate reports them.

    Raises:
        ConfigurationError: if the file is missing or is not a YAML mapping.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise ConfigurationError(f"no run settings at {resolved}")
    data = resolved.read_bytes()
    try:
        raw = yaml.safe_load(data.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError):
        raise ConfigurationError(f"{resolved} is not valid YAML") from None
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{resolved} must be a YAML mapping")
    return RunSettings(path=resolved, content_sha256=hashlib.sha256(data).hexdigest(), raw=raw)


def engine_transforms_applied(engine: Mapping[str, Any], settings: RunSettings) -> bool:
    """V9(a): are covariate transforms part of the engine's runs yet?

    ``run.py`` does not call ``engineer_covariates`` today (Viraj's #3). Matching on raw
    values during the ladder and on log values in the run would admit different donors,
    so the ladder waits for the engine to report it, or for an explicit confirmation.
    """
    implemented = engine.get("implemented")
    reported = isinstance(implemented, Mapping) and (
        implemented.get(ENGINE_TRANSFORMS_CAPABILITY) is True
    )
    return reported or settings.raw.get("engine_transforms_confirmed") is True


def generation_blockers(
    settings: RunSettings,
    *,
    case: CaseDefinition,
    engine: Mapping[str, Any],
    earth_engine_key_set: bool,
    sensor: str | None,
) -> list[Blocker]:
    """Everything that stops a real unit set being generated. Empty means go.

    Makes no Earth Engine call, so a blocked run costs nothing and reveals nothing.
    """
    blockers = settings.missing()

    snapshot_path = settings.raw.get("carbon_project_snapshot")
    if not _is_unset(snapshot_path):
        try:
            load_carbon_snapshot(str(snapshot_path))
        except DataUnavailableError as exc:
            blockers.append(Blocker("carbon_project_snapshot", f"B3: {exc}"))

    if case.min_donors is None or case.max_donors is None:
        blockers.append(
            Blocker("min_donors/max_donors", f"V8: set both in cases/{case.case_id}.yaml.")
        )

    if not engine_transforms_applied(engine, settings):
        blockers.append(
            Blocker(
                "engine_transforms_confirmed",
                "V9(a): run.py does not apply engineer_covariates yet (Viraj, #3), so the ladder "
                "would match on a different scale than the run. Refusing until the engine reports "
                f"{ENGINE_TRANSFORMS_CAPABILITY} or this setting confirms it.",
            )
        )
    if not earth_engine_key_set:
        blockers.append(
            Blocker("GEE_SERVICE_ACCOUNT_JSON", "The Earth Engine service-account key is not set.")
        )
    if sensor is None:
        blockers.append(
            Blocker("EARTH_ENGINE_SENSOR", "The agreed sensor (C3) must be named: landsat7.")
        )
    return blockers


__all__ = [
    "ENGINE_TRANSFORMS_CAPABILITY",
    "REQUIRED_SETTINGS",
    "Blocker",
    "RunSettings",
    "engine_transforms_applied",
    "generation_blockers",
    "load_run_settings",
    "run_settings_path",
]
