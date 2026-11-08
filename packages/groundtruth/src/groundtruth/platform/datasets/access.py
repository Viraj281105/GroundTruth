"""DataAccess implementations: the platform side of the engine's ports.

**Owner: Bhumi.**

This module is where dataset choice, version pinning, credentials, caching and
retries live. The engine states what it needs through
:mod:`groundtruth.contracts.ports`; this module decides where it comes from.

Two bundles are provided today:

- :func:`synthetic_access` — deterministic fixtures for offline development,
  CI and the demo. Every series it returns is pinned to a dataset reference
  whose provider is ``synthetic``, which propagates into the result's
  ``is_simulated`` flag and from there into the UI banner.
- :func:`earth_engine_access` — the real path. Not implemented; it raises
  rather than falling back to fixtures, because a silent fallback would let
  simulated numbers be published under a real-data label.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.identifiers import DatasetRef
from groundtruth.contracts.ports import DataAccess, ObservationSpec
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import AnalysisRequest, UnitRef
from groundtruth.contracts.types import Indicator, TimeSeries
from groundtruth.platform.datasets.synthetic import (
    SyntheticCovariateProvider,
    SyntheticDonorPoolProvider,
    SyntheticObservationProvider,
)

SYNTHETIC_OBSERVATION_DATASET = DatasetRef(
    dataset_id="synthetic-latent-factor",
    version="1.0",
    provider="synthetic",
    source_uri=None,
)

SYNTHETIC_COVARIATE_DATASET = DatasetRef(
    dataset_id="synthetic-covariates",
    version="1.0",
    provider="synthetic",
)


class SyntheticObservationAccess:
    """Observation port backed by the deterministic fixture simulator.

    **Returns simulated data.** Pinned to a dataset reference whose provider is
    ``synthetic``, so the result carries ``is_simulated=True`` and the UI shows
    its banner without anyone having to remember to set a flag.
    """

    def __init__(
        self,
        *,
        seed: int = 20260101,
        treated_unit_id: str | None = None,
        true_effect: float = 0.0,
        treatment_period: int | None = None,
    ) -> None:
        self._provider = SyntheticObservationProvider(
            seed=seed,
            treated_unit_id=treated_unit_id,
            true_effect=true_effect,
            treatment_period=treatment_period,
        )

    def series(self, spec: ObservationSpec) -> TimeSeries:
        """Return a simulated indicator series for the requested unit."""
        return self._provider.fetch_series(
            unit_id=spec.unit.unit_id,
            indicator=spec.indicator,
            start_period=spec.start_period,
            end_period=spec.end_period,
        )

    def dataset(self, indicator: Indicator) -> DatasetRef:
        """Return the pinned dataset backing this indicator."""
        return SYNTHETIC_OBSERVATION_DATASET

    def provenance(self, spec: ObservationSpec) -> Provenance:
        """Provenance that unambiguously marks the data as simulated."""
        return self._provider.provenance_for(spec.indicator)


class SyntheticCovariateAccess:
    """Covariate port backed by the fixture generator. **Simulated values.**"""

    def __init__(self, *, seed: int = 20260101, project_unit_id: str | None = None) -> None:
        self._provider = SyntheticCovariateProvider(seed=seed, project_unit_id=project_unit_id)

    def covariates(self, unit: UnitRef, keys: tuple[str, ...]) -> dict[str, float]:
        """Return simulated covariates, restricted to the requested keys."""
        values = self._provider.covariates_for(unit.unit_id, dict(unit.attributes))
        return {k: values[k] for k in keys if k in values}

    def dataset(self, key: str) -> DatasetRef:
        """Return the pinned dataset backing one covariate."""
        return SYNTHETIC_COVARIATE_DATASET


class SyntheticDonorAccess:
    """Donor-candidate port backed by the fixture generator."""

    def __init__(self, prefix: str = "donor") -> None:
        self._provider = SyntheticDonorPoolProvider(prefix=prefix)

    def candidates(self, request: AnalysisRequest) -> list[UnitRef]:
        """Return synthetic donor candidates for a request."""
        return [
            UnitRef(unit_id=uid) for uid in self._provider.candidate_ids(request.donors.pool_size)
        ]


def synthetic_access(
    request: AnalysisRequest,
    *,
    true_effect: float = 0.0,
) -> DataAccess:
    """Build a complete simulated DataAccess bundle for a request.

    Args:
        request: The analysis request the bundle will serve.
        true_effect: Effect injected into the simulated treated unit, so the
            estimator's ability to recover a known value can be exercised.
    """
    return DataAccess(
        observations=SyntheticObservationAccess(
            seed=request.seed,
            treated_unit_id=request.project.unit_id,
            true_effect=true_effect,
            treatment_period=request.window.post_start,
        ),
        covariates=SyntheticCovariateAccess(
            seed=request.seed, project_unit_id=request.project.unit_id
        ),
        donors=SyntheticDonorAccess(),
    )


SYNTHETIC_KARIBA_FIXTURE_DATASET = DatasetRef(
    dataset_id="synthetic-kariba-benchmark-fixture",
    version="1.0",
    provider="synthetic",
    source_uri=None,
)
"""Dataset reference for the precomputed Kariba benchmark fixture. SYNTHETIC."""

SYNTHETIC_FIXTURE_CASES = ("kariba-redd",)
"""Cases for which a precomputed SYNTHETIC fixture exists."""

SYNTHETIC_FIXTURE_FILENAME = "kariba_synthetic_benchmark.json"


def synthetic_fixture_paths() -> list[Path]:
    """Candidate locations of the synthetic Kariba benchmark fixture."""
    from groundtruth.platform.config import get_settings

    return [
        get_settings().data_dir / "synthetic_fixtures" / SYNTHETIC_FIXTURE_FILENAME,
        Path("data/synthetic_fixtures") / SYNTHETIC_FIXTURE_FILENAME,
        Path(__file__).resolve().parents[6]
        / "data"
        / "synthetic_fixtures"
        / SYNTHETIC_FIXTURE_FILENAME,
    ]


def synthetic_fixture_available(case_id: str) -> bool:
    """True if a precomputed SYNTHETIC fixture file exists for ``case_id``."""
    return case_id in SYNTHETIC_FIXTURE_CASES and any(
        p.is_file() for p in synthetic_fixture_paths()
    )


def real_observation_cases() -> tuple[str, ...]:
    """Cases with genuine satellite observations available. Currently none."""
    return ()


@functools.lru_cache(maxsize=1)
def _load_kariba_synthetic_fixture() -> dict[str, Any]:
    for p in synthetic_fixture_paths():
        if p.is_file():
            with open(p, encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
            if (
                data.get("synthetic") is not True
                or data.get("dataset_ref", {}).get("provider") != "synthetic"
            ):
                raise DataUnavailableError(
                    f"{p} is not labelled SYNTHETIC; refusing to load it as a fixture."
                )
            return data
    raise DataUnavailableError(
        "SYNTHETIC Kariba fixture not found at any of: "
        f"{[str(c) for c in synthetic_fixture_paths()]}"
    )


class SyntheticFixtureObservationAccess:
    """Observation port backed by the precomputed **SYNTHETIC** Kariba fixture.

    These are NOT satellite observations. The dataset reference is pinned to
    provider ``synthetic`` so results carry ``is_simulated=True``.
    """

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data if data is not None else _load_kariba_synthetic_fixture()

    def series(self, spec: ObservationSpec) -> TimeSeries:
        """Return the SYNTHETIC indicator series for the requested unit."""
        unit_id = spec.unit.unit_id
        units = self._data.get("units", {})
        if unit_id not in units:
            raise DataUnavailableError(f"No synthetic fixture series found for unit {unit_id!r}")
        unit_series = units[unit_id]["series"]
        all_periods = unit_series["periods"]
        all_values = unit_series["values"]
        all_obs = unit_series.get("n_valid_observations")

        indices = [
            i for i, p in enumerate(all_periods) if spec.start_period <= p <= spec.end_period
        ]
        if not indices:
            raise DataUnavailableError(
                f"No fixture periods available for unit {unit_id!r} in window "
                f"[{spec.start_period}, {spec.end_period}]"
            )
        return TimeSeries(
            unit_id=unit_id,
            indicator=spec.indicator,
            periods=tuple(int(all_periods[i]) for i in indices),
            values=tuple(float(all_values[i]) for i in indices),
            n_valid_observations=tuple(int(all_obs[i]) for i in indices) if all_obs else None,
        )

    def dataset(self, indicator: Indicator) -> DatasetRef:
        """Return the pinned (synthetic) dataset backing this indicator."""
        return SYNTHETIC_KARIBA_FIXTURE_DATASET

    def provenance(self, spec: ObservationSpec) -> Provenance:
        """Provenance that unambiguously marks the data as SYNTHETIC."""
        return Provenance(
            source="synthetic",
            method="synthetic-fixture-replay",
            stage="ingestion",
            source_uri=None,
            notes=(
                "SYNTHETIC FIXTURE: precomputed series replayed from disk. Not satellite "
                "observations; no imagery was retrieved or processed."
            ),
        )


class SyntheticFixtureCovariateAccess:
    """Covariate port backed by the SYNTHETIC Kariba fixture. **Simulated values.**"""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data if data is not None else _load_kariba_synthetic_fixture()

    def covariates(self, unit: UnitRef, keys: tuple[str, ...]) -> dict[str, float]:
        """Return SYNTHETIC covariates for one unit, restricted to requested keys."""
        unit_id = unit.unit_id
        units = self._data.get("units", {})
        if unit_id not in units:
            raise DataUnavailableError(f"No synthetic fixture covariates for unit {unit_id!r}")
        covs = dict(units[unit_id].get("covariates", {}))
        if unit.attributes:
            covs.update(dict(unit.attributes))

        aliases = {
            "rainfall_mm": "annual_rainfall_mm",
            "annual_rainfall_mm": "rainfall_mm",
            "road_distance_km": "distance_to_road_km",
            "distance_to_road_km": "road_distance_km",
            "population_density": "settlement_density",
            "settlement_density": "population_density",
        }
        for k in keys:
            if k not in covs and k in aliases and aliases[k] in covs:
                covs[k] = covs[aliases[k]]
        return {k: float(covs[k]) for k in keys if k in covs}

    def dataset(self, key: str) -> DatasetRef:
        """Return the pinned (synthetic) dataset backing one covariate."""
        return SYNTHETIC_KARIBA_FIXTURE_DATASET


@functools.lru_cache(maxsize=1)
def _load_kariba_donor_feature_map() -> dict[str, dict[str, Any]]:
    from groundtruth.platform.config import REPO_ROOT, get_settings

    candidates = [
        get_settings().cases_dir / "boundaries" / "kariba-donors.geojson",
        Path("cases/boundaries/kariba-donors.geojson"),
        REPO_ROOT / "cases" / "boundaries" / "kariba-donors.geojson",
    ]
    for p in candidates:
        if p.is_file():
            raw = json.loads(p.read_text(encoding="utf-8"))
            return {
                str(f.get("id") or f.get("properties", {}).get("unit_id")): f
                for f in raw.get("features", [])
                if isinstance(f, dict)
            }
    return {}


class SyntheticFixtureDonorAccess:
    """Donor-candidate port backed by the SYNTHETIC Kariba fixture."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data = data if data is not None else _load_kariba_synthetic_fixture()

    def candidates(self, request: AnalysisRequest) -> list[UnitRef]:
        """Return candidate donor units for a request, attaching verified ADM2 boundaries."""
        project_id = request.project.unit_id
        donor_ids = [uid for uid in self._data.get("units", {}) if uid != project_id]
        if request.donors.pool_size and len(donor_ids) > request.donors.pool_size:
            donor_ids = donor_ids[: request.donors.pool_size]
        feature_map = _load_kariba_donor_feature_map() if self._data is not None else {}
        refs: list[UnitRef] = []
        for uid in donor_ids:
            feat = feature_map.get(uid)
            if feat is not None:
                props = feat.get("properties") or {}
                refs.append(
                    UnitRef(
                        unit_id=uid,
                        geometry=feat,
                        centroid_lat=props.get("centroid_lat"),
                        centroid_lon=props.get("centroid_lon"),
                        area_ha=props.get("area_ha"),
                    )
                )
            else:
                refs.append(UnitRef(unit_id=uid))
        return refs


def synthetic_fixture_access(request: AnalysisRequest) -> DataAccess:
    """Build a DataAccess bundle over the precomputed SYNTHETIC fixture.

    Raises:
        DataUnavailableError: If no fixture exists for the request's case.
    """
    if request.case_id not in SYNTHETIC_FIXTURE_CASES:
        raise DataUnavailableError(
            f"No synthetic fixture exists for case '{request.case_id}'. "
            f"Fixtures: {', '.join(SYNTHETIC_FIXTURE_CASES)}."
        )
    return DataAccess(
        observations=SyntheticFixtureObservationAccess(),
        covariates=SyntheticFixtureCovariateAccess(),
        donors=SyntheticFixtureDonorAccess(),
    )


PLANETARY_COMPUTER_S2_DATASET = DatasetRef(
    dataset_id="sentinel-2-l2a",
    version="05.10",
    provider="microsoft-planetary-computer",
    source_uri="https://planetarycomputer.microsoft.com/api/stac/v1",
)
"""Dataset reference for real Sentinel-2 L2A STAC observations."""


class StacCachedObservationAccess:
    """Observation port backed by real STAC observations stored in :class:`AOIObservationCache`.

    Refuses ``SYNTHETIC`` cache entries (`require_real=True`) and never falls back
    to synthetic fixtures when a unit or period is unavailable.
    """

    def __init__(self, cache_dir: Path | str) -> None:
        from groundtruth.data_access.aoi_pipeline import AOIObservationCache

        self._cache = AOIObservationCache(cache_dir)

    def _load_bundle(self, unit_id: str, indicator: Indicator) -> Any:
        from groundtruth.data_access.aoi_pipeline import DataOrigin

        try:
            bundle = self._cache.get(unit_id, indicator, require_real=True)
        except FileNotFoundError as exc:
            raise DataUnavailableError(
                f"No cached real STAC observation bundle for unit {unit_id!r} "
                f"(indicator={indicator.value!r}) in {self._cache.cache_dir}"
            ) from exc
        except ValueError as exc:
            raise DataUnavailableError(str(exc)) from exc

        if bundle.data_origin not in (DataOrigin.REAL_STAC, DataOrigin.CACHED_REAL_STAC):
            raise DataUnavailableError(
                f"Refusing non-real bundle origin {bundle.data_origin!r} for unit {unit_id!r}"
            )
        return bundle

    def series(self, spec: ObservationSpec) -> TimeSeries:
        """Return the cached real STAC indicator series for the requested unit and window."""
        bundle = self._load_bundle(spec.unit.unit_id, spec.indicator)
        full_ts = bundle.to_time_series(drop_nan=True)
        indices = [
            i for i, p in enumerate(full_ts.periods) if spec.start_period <= p <= spec.end_period
        ]
        if len(indices) < 2:
            raise DataUnavailableError(
                f"Insufficient real STAC periods for unit {spec.unit.unit_id!r} in window "
                f"[{spec.start_period}, {spec.end_period}] (found {len(indices)})"
            )
        return TimeSeries(
            unit_id=spec.unit.unit_id,
            indicator=spec.indicator,
            periods=tuple(full_ts.periods[i] for i in indices),
            values=tuple(full_ts.values[i] for i in indices),
            unit=full_ts.unit,
            n_valid_observations=(
                tuple(full_ts.n_valid_observations[i] for i in indices)
                if full_ts.n_valid_observations is not None
                else None
            ),
        )

    def dataset(self, indicator: Indicator) -> DatasetRef:
        """Return the pinned dataset reference for real Sentinel-2 L2A STAC data."""
        return PLANETARY_COMPUTER_S2_DATASET

    def provenance(self, spec: ObservationSpec) -> Provenance:
        """Return the provenance record from the real STAC observation bundle."""
        bundle = self._load_bundle(spec.unit.unit_id, spec.indicator)
        return bundle.provenance


def earth_engine_access(request: AnalysisRequest) -> DataAccess:
    """Build a real Earth-observation DataAccess bundle.

    **Not implemented.** No real satellite ingestion pipeline has been executed in
    this repository, so this always raises rather than returning fixtures. A
    silent fallback would let simulated numbers be published under a real-data
    label. Use :func:`synthetic_fixture_access` or :func:`synthetic_access` for
    explicitly SYNTHETIC runs.
    """
    raise DataUnavailableError(
        f"Real Earth-observation data access is not implemented for case '{request.case_id}' "
        f"(unit '{request.project.unit_id}'): no satellite scenes have been ingested. "
        "Genuine observations are not available for any case. "
        "See docs/product/roadmap-detail.md milestone M1."
    )
