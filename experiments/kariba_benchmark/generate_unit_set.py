"""Generate a case's ADR-011 unit set and materialise its manifest (#23).

This is the one place real candidate generation is driven from, and it refuses until
every required setting is decided. It sits outside ``platform/`` because the ladder's
stopping rule needs Viraj's ``match_donors``, which the platform may not import. It
calls that function unchanged and fetches only **pre-period** NDVI, so no
post-treatment outcome is touched before the pool is fixed.

Three modes, in the order they are meant to be used::

    python experiments/kariba_benchmark/generate_unit_set.py --list
    python experiments/kariba_benchmark/generate_unit_set.py --timing-trial
    python experiments/kariba_benchmark/generate_unit_set.py --write

``--list`` prints literal names to fix the open parameters from, and no count of
anything. ``--timing-trial`` prints the seconds each step takes on one district, and
no count of anything. Running with neither generates the unit set; ``--write`` also
writes the manifest under ``data/manifests/``, to be reviewed and committed.

Exit codes: 0 done, 2 blocked by an undecided setting (nothing contacted Earth Engine).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from groundtruth.contracts.errors import DonorPoolError, GroundTruthError
from groundtruth.contracts.ports import ObservationSpec
from groundtruth.contracts.request import DonorSpec, UnitRef
from groundtruth.engine import ENGINE_VERSION, describe_engine
from groundtruth.engine.features import engineer_covariates
from groundtruth.engine.matching.donors import MatchingConfig, match_donors
from groundtruth.engine.observation.alignment import pre_period_coverage
from groundtruth.platform.cases.registry import CaseDefinition, get_case
from groundtruth.platform.config import REPO_ROOT, Settings, get_settings
from groundtruth.platform.datasets.access import (
    earth_engine_cache,
    earth_engine_covariates,
    earth_engine_observations,
    earth_engine_session,
)
from groundtruth.platform.datasets.covariates import covariate_datasets
from groundtruth.platform.units import (
    LADDER,
    Adr011Thresholds,
    Blocker,
    EarthEngineUnitConstruction,
    ManifestContext,
    RunSettings,
    UnitSet,
    district_unit_ref,
    generate_unit_set,
    generation_blockers,
    load_carbon_snapshot,
    load_registry_boundary,
    load_run_settings,
    run_settings_path,
)
from groundtruth.platform.units.rules import Screening
from groundtruth.platform.units.spec import Rung


class GenerationBlockedError(GroundTruthError):
    """A required setting is undecided. Nothing has contacted Earth Engine."""

    def __init__(self, blockers: list[Blocker]) -> None:
        super().__init__("; ".join(str(b) for b in blockers))
        self.blockers = blockers


@dataclass(frozen=True)
class Services:
    """Everything a generation run talks to, on one shared session."""

    provider: EarthEngineUnitConstruction
    covariates: Any
    observations: Any


def blockers_for(
    case: CaseDefinition,
    run_settings: RunSettings,
    settings: Settings,
    *,
    engine: Mapping[str, Any] | None = None,
) -> list[Blocker]:
    """Everything standing in the way of a real run, checked before any Earth Engine call."""
    return generation_blockers(
        run_settings,
        case=case,
        engine=engine if engine is not None else describe_engine(),
        earth_engine_key_set=settings.gee_service_account_json is not None,
        sensor=settings.earth_engine_sensor,
    )


def build_services(
    case: CaseDefinition,
    run_settings: RunSettings,
    settings: Settings,
    *,
    backend: Any = None,
) -> Services:
    """One session, shared by the unit, covariate and observation services."""
    session, client = earth_engine_session(settings, backend=backend)
    snapshot = load_carbon_snapshot(str(run_settings.raw["carbon_project_snapshot"]))
    provider = EarthEngineUnitConstruction(
        session=session,
        backend=client,
        cache=earth_engine_cache(settings),
        carbon_projects=snapshot,
        case_registry_id=case.claim.registry_id,
        treated_ecoregion_key=str(run_settings.raw["treated_ecoregion_rung"]),
    )
    covariates = earth_engine_covariates(
        settings,
        road=run_settings.road_source(),
        mask_rule=str(run_settings.raw["native_scale_mask_rule"]),
        session=session,
        backend=client,
    )
    observations = earth_engine_observations(settings, session=session, backend=client)
    return Services(provider=provider, covariates=covariates, observations=observations)


def admitted_counter(case: CaseDefinition, treated_unit: UnitRef, services: Services) -> Any:
    """The ladder's admitted count: real covariates and pre-period NDVI, through ``match_donors``.

    ``min_donors`` is 0 here so a shortfall comes back as a count instead of a refusal.
    The stopping rule compares that count against the real ``min_donors`` itself, and
    records it at every rung, including the ones it passes.
    """
    keys = case.covariates or DonorSpec().covariates
    defaults = DonorSpec()

    def count(rung: Rung, screening: Screening) -> int:
        units = [district_unit_ref(facts) for facts in screening.eligible]
        if not units:
            return 0
        candidates = {u.unit_id: services.covariates.covariates(u, keys) for u in units}
        project = services.covariates.covariates(treated_unit, keys)
        series = {
            u.unit_id: services.observations.series(
                ObservationSpec(
                    unit=u,
                    indicator=case.indicator,
                    start_period=case.window.pre_start,
                    end_period=case.window.pre_end,
                )
            )
            for u in units
        }
        engineered = engineer_covariates(project, candidates, keys)
        try:
            pool = match_donors(
                case.case_id,
                engineered.project,
                engineered.candidates,
                MatchingConfig(
                    covariates=tuple(keys),
                    max_donors=case.max_donors or defaults.max_donors,
                    min_donors=0,
                    caliper_sd=defaults.caliper_sd,
                    excluded_unit_ids=frozenset(case.excluded_donor_ids),
                    min_pre_observations=defaults.min_pre_observations,
                ),
                candidate_pre_observations=pre_period_coverage(case.window, series),
            )
        except DonorPoolError:
            return 0
        return len(pool.admitted)

    return count


def generate(
    case: CaseDefinition,
    run_settings: RunSettings,
    settings: Settings,
    *,
    backend: Any = None,
    engine: Mapping[str, Any] | None = None,
) -> UnitSet:
    """Climb the ladder and build the unit set.

    Raises:
        GenerationBlockedError: before any Earth Engine call, if anything is undecided.
        DonorPoolError: if the ladder is exhausted, which refuses the case.
    """
    blockers = blockers_for(case, run_settings, settings, engine=engine)
    if blockers:
        raise GenerationBlockedError(blockers)

    snapshot = load_carbon_snapshot(str(run_settings.raw["carbon_project_snapshot"]))
    parameters = run_settings.parameters(case, snapshot)
    thresholds = Adr011Thresholds()
    services = build_services(case, run_settings, settings, backend=backend)

    boundary_path = REPO_ROOT / str(case.claim.boundary_path)
    boundary = load_registry_boundary(boundary_path, case_id=case.case_id)
    treated = services.provider.treated_unit(boundary, parameters=parameters, thresholds=thresholds)
    road = run_settings.road_source()
    refs = covariate_datasets(road)
    context = ManifestContext(
        belt_geometry_hash=services.provider.leakage_belt_hash(
            boundary, parameters=parameters, thresholds=thresholds
        ),
        covariate_refs=tuple({ref.dataset_id: ref for ref in refs.values()}.values()),
        run_settings_sha256=run_settings.content_sha256,
        carbon_snapshot_sha256=snapshot.content_sha256,
        covariate_settings=run_settings.covariate_settings(),
    )
    return generate_unit_set(
        boundary_path=boundary_path,
        service=services.provider,
        parameters=parameters,
        count_admitted=admitted_counter(case, treated, services),
        thresholds=thresholds,
        case_id=case.case_id,
        engine_version=ENGINE_VERSION,
        git_sha=settings.git_sha,
        treated_geometry=treated.geometry,
        manifest_context=context,
    )


def timing_trial(
    case: CaseDefinition,
    run_settings: RunSettings,
    settings: Settings,
    *,
    backend: Any = None,
    engine: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Seconds per step on one district (B6). Reports no count of any kind.

    V9(a) concerns matching, which the trial does not do, so it alone does not block.
    """
    blockers = [
        b
        for b in blockers_for(case, run_settings, settings, engine=engine)
        if b.name != "engine_transforms_confirmed"
    ]
    if blockers:
        raise GenerationBlockedError(blockers)
    snapshot = load_carbon_snapshot(str(run_settings.raw["carbon_project_snapshot"]))
    parameters = run_settings.parameters(case, snapshot)
    services = build_services(case, run_settings, settings, backend=backend)
    boundary = load_registry_boundary(
        REPO_ROOT / str(case.claim.boundary_path), case_id=case.case_id
    )
    return services.provider.timing_trial(
        LADDER[0],
        boundary,
        parameters=parameters,
        thresholds=Adr011Thresholds(),
        covariates=services.covariates,
    )


def study_area_listing(settings: Settings, *, backend: Any = None) -> dict[str, list[str]]:
    """Literal names to fix the open parameters from. Needs only the Earth Engine key."""
    session, client = earth_engine_session(settings, backend=backend)
    return EarthEngineUnitConstruction(session=session, backend=client).study_area_listing()


def _print_blockers(blockers: list[Blocker]) -> None:
    print(f"REFUSED: {len(blockers)} required setting(s) are not decided. Nothing was fetched.")
    for blocker in blockers:
        print(f"  - {blocker}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="kariba-redd")
    parser.add_argument("--list", action="store_true", help="print literal names; no counts")
    parser.add_argument("--timing-trial", action="store_true", help="seconds only; no counts")
    parser.add_argument("--write", action="store_true", help="write the manifest")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.list:
        for name, values in study_area_listing(settings).items():
            print(f"{name}:")
            for value in values:
                print(f"  {value}")
        return 0

    case = get_case(args.case)
    run_settings = load_run_settings(run_settings_path(args.case))
    try:
        if args.timing_trial:
            for step, seconds in timing_trial(case, run_settings, settings).items():
                print(f"{step:<36} {seconds:>9.1f} s")
            return 0
        unit_set = generate(case, run_settings, settings)
    except GenerationBlockedError as blocked:
        _print_blockers(blocked.blockers)
        return 2

    print(f"rung used: {unit_set.rung_used}, candidates: {len(unit_set.candidates)}")
    for record in unit_set.outcome.records:
        print(
            f"  rung {record.rung}: {record.eligible_candidates} candidates, "
            f"{record.admitted_donors} admitted"
        )
    if args.write:
        path: Path = unit_set.manifest.write(REPO_ROOT / "data" / "manifests")
        print(f"manifest written to {path}; review it with Viraj before committing (C7).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
