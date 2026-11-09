"""Per-project data loaders that read only provenance-checked caches.

Each loader returns an explicit ``status``. A project without usable data is ``unavailable``
with a human-readable reason; the loaders never raise for missing, corrupt or inconsistent
cache files, and never substitute another project's data or a synthetic series.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from groundtruth.contracts.errors import (
    DataUnavailableError,
    InsufficientDataError,
    ProvenanceError,
)
from groundtruth.platform.config import get_settings
from groundtruth.platform.store.models import ProjectRow

if TYPE_CHECKING:
    from groundtruth.data_access.aoi_pipeline import AOIObservationBundle
    from groundtruth.data_access.climate import KaribaClimateBundle

LoadStatus = Literal["available", "unavailable"]

NO_CLIMATE_REASON = "No climate series has been ingested for this project"


@dataclass(frozen=True)
class ObservationsResult:
    """Outcome of loading a project's annual observations for one indicator."""

    status: LoadStatus
    reason: str | None
    bundle: AOIObservationBundle | None


@dataclass(frozen=True)
class ClimateResult:
    """Outcome of loading a project's climate series."""

    status: LoadStatus
    reason: str | None
    bundle: KaribaClimateBundle | None


def _obs_unavailable(reason: str) -> ObservationsResult:
    return ObservationsResult(status="unavailable", reason=reason, bundle=None)


def _climate_unavailable(reason: str) -> ClimateResult:
    return ClimateResult(status="unavailable", reason=reason, bundle=None)


def load_observations(
    project: ProjectRow, indicator: str, *, data_dir: Path | None = None
) -> ObservationsResult:
    """Load the provenance-checked annual observations of ``project`` for ``indicator``.

    The cache is keyed by the project's case id, or by the project's own id when it has no case.
    Absent files, malformed JSON, a bundle that
    fails the real-provenance integrity check, and synthetic bundles all yield ``unavailable``
    with the specific reason, never an exception and never a fabricated series.

    ``data_dir`` overrides the configured data directory (used by computed readiness, which
    is handed its data directory explicitly).
    """
    case_id = project.case_id
    if not case_id:
        # A project defined by an uploaded boundary has no case. Observations ingested for it are
        # stored under its own id, so it can only ever read its own data (never another project's).
        return load_unit_observations(
            project.id, indicator, data_dir=data_dir, label="this project"
        )
    return load_unit_observations(case_id, indicator, data_dir=data_dir, label=repr(case_id))


def load_unit_observations(
    unit_id: str, indicator: str, *, data_dir: Path | None = None, label: str | None = None
) -> ObservationsResult:
    """Load the cached observations of one unit (a project's case or a donor) for ``indicator``.

    Same never-raises contract as :func:`load_observations`; ``label`` names the unit in the
    human-readable reasons.
    """
    from groundtruth.data_access.aoi_pipeline import AOIObservationCache

    case_id = unit_id
    label = label or repr(unit_id)
    root = data_dir if data_dir is not None else get_settings().data_dir
    cache_dir = root / "processed" / "stac_cache"
    if not cache_dir.is_dir():
        # AOIObservationCache creates its directory; a read must not write to disk.
        return _obs_unavailable(f"No observation cache has been ingested for {label}")
    try:
        bundle = AOIObservationCache(cache_dir).get(case_id, indicator)
    except FileNotFoundError:
        return _obs_unavailable(f"No {indicator} observations have been ingested for {label}")
    except ProvenanceError as exc:
        return _obs_unavailable(
            f"Cached {indicator} observations for {label} failed the provenance check: {exc}"
        )
    except (ValueError, KeyError) as exc:  # JSONDecodeError is a ValueError
        return _obs_unavailable(
            f"Cached {indicator} observations for {label} are unreadable or not servable: {exc!r}"
        )
    return ObservationsResult(status="available", reason=None, bundle=bundle)


def load_climate(project: ProjectRow, *, data_dir: Path | None = None) -> ClimateResult:
    """Load the climate series ingested for ``project``, or explain why there is none.

    Climate is Kariba-only today: any project whose case has no matching ingested bundle is
    ``unavailable``.
    """
    from groundtruth.data_access.climate import load_project_climate

    case_id = project.case_id
    if not case_id:
        return _climate_unavailable(NO_CLIMATE_REASON)
    root = data_dir if data_dir is not None else get_settings().data_dir
    cache_dir: Path = root / "processed" / "climate_cache"
    try:
        bundle = load_project_climate(case_id, cache_dir)
    except (DataUnavailableError, InsufficientDataError, ValueError, KeyError) as exc:
        return _climate_unavailable(
            f"The ingested climate cache for {case_id!r} is unreadable or incomplete: {exc!r}"
        )
    if bundle is None:
        return _climate_unavailable(NO_CLIMATE_REASON)
    return ClimateResult(status="available", reason=None, bundle=bundle)
