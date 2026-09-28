"""End-to-end ADR-011 candidate generation.

The order is the ADR's and is not negotiable:

1. Load the registry boundary (#2) and validate it.
2. Measure the treated unit's eligible area under the full mask. This sets the
   area band, so it must be measured before any candidate is screened.
3. Climb the fixed three-rung ladder. At each rung: screen districts against the
   eligibility rules, count admitted donors, record both counts.
4. Stop at the first rung yielding both enough eligible candidates and enough
   admitted donors, or refuse.
5. Materialise the unit set as a manifest that pins what produced it.

Nothing in this module reads a candidate count before fixing a parameter. The
thresholds arrive frozen from :mod:`groundtruth.platform.units.spec`, the open
parameters arrive from the caller and are validated before the first rung is
screened, and the ladder's stopping rule is evaluated identically at every rung.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from groundtruth.contracts.errors import DonorPoolError
from groundtruth.contracts.request import AnalysisRequest, UnitRef
from groundtruth.logging import get_logger
from groundtruth.platform.units.boundary import RegistryBoundary, load_registry_boundary
from groundtruth.platform.units.manifest import UnitSetManifest, build_manifest
from groundtruth.platform.units.provider import UnitConstructionService
from groundtruth.platform.units.rules import (
    DistrictFacts,
    Exclusion,
    LadderOutcome,
    Screening,
    climb_ladder,
    screen_rung,
)
from groundtruth.platform.units.spec import LADDER, Adr011Thresholds, Rung, RunParameters

logger = get_logger("units.generator")

HECTARES_PER_KM2 = 100.0

AdmittedCounter = Callable[[Rung, Screening], int]
"""Runs matching over a rung's eligible candidates and returns the admitted count.

Supplied by the caller because it needs covariates (#23) and the engine's
matching stage. ADR-011's stopping rule tests admitted donors as well as
eligible candidates, so the ladder cannot be climbed without it.
"""


@dataclass(frozen=True, slots=True)
class UnitSet:
    """A generated donor-candidate set, with the record of how it was produced."""

    case_id: str
    treated_unit: UnitRef
    treated_eligible_area_km2: float
    candidates: tuple[DistrictFacts, ...]
    exclusions: tuple[Exclusion, ...]
    outcome: LadderOutcome
    manifest: UnitSetManifest

    @property
    def rung_used(self) -> int:
        """Which ladder rung produced this pool."""
        return self.outcome.rung_used

    def candidate_unit_refs(self) -> tuple[UnitRef, ...]:
        """Candidates as contract units, ordered deterministically by ``unit_id``.

        ``area_ha`` carries the **eligible** area after masking, per ADR-011,
        not the administrative area. Descriptors that a reviewer needs — country,
        ecoregion, district name — cannot travel here until #60 widens
        ``UnitRef.attributes`` beyond floats; the manifest carries them meanwhile.
        """
        return tuple(
            UnitRef(
                unit_id=facts.unit_id,
                area_ha=facts.eligible_area_km2 * HECTARES_PER_KM2,
                attributes={
                    "eligible_area_km2": facts.eligible_area_km2,
                    "forest_share_in_target_ecoregions": (facts.forest_share_in_target_ecoregions),
                    "fragments": float(facts.fragments),
                },
            )
            for facts in self.candidates
        )


def generate_unit_set(
    *,
    boundary_path: str | Path,
    service: UnitConstructionService,
    parameters: RunParameters,
    count_admitted: AdmittedCounter,
    thresholds: Adr011Thresholds | None = None,
    case_id: str | None = None,
    engine_version: str = "unknown",
    git_sha: str | None = None,
) -> UnitSet:
    """Build the ADR-011 donor-candidate set for one case.

    Args:
        boundary_path: Committed registry boundary artifact (#2).
        service: Masking provider that measures eligible areas and district facts.
        parameters: The run's pinned open parameters. Validated before anything
            is screened, so an incomplete set fails before it can see a count.
        count_admitted: Returns the admitted-donor count for a rung's eligible
            candidates, which ADR-011's stopping rule needs.
        thresholds: ADR-011's fixed thresholds. Defaults to the ADR's values.
        case_id: Overrides the case id in the boundary artifact.
        engine_version: Recorded in the manifest.
        git_sha: Recorded in the manifest.

    Returns:
        The :class:`UnitSet`, including the manifest.

    Raises:
        MissingRunParameterError: if an open parameter was not pinned.
        DataUnavailableError: if the boundary or the masking inputs are missing.
        DonorPoolError: if the ladder is exhausted without meeting the minimum.
    """
    fixed = thresholds or Adr011Thresholds()
    parameters.validate()

    boundary = load_registry_boundary(boundary_path, case_id=case_id)
    logger.info(
        "registry boundary loaded",
        extra={
            "case_id": boundary.case_id,
            "parts": boundary.report.parts,
            "boundary_area_km2": round(boundary.boundary_area_km2, 1),
            "sha256": boundary.content_sha256[:12],
        },
    )

    treated_area = service.treated_eligible_area_km2(
        boundary, parameters=parameters, thresholds=fixed
    )
    if treated_area <= 0:
        raise DonorPoolError(
            f"the treated unit for {boundary.case_id!r} has no eligible area after the ADR-011 "
            "mask; the area band cannot be derived and no donor pool is definable"
        )

    def screen(rung: Rung) -> Screening:
        districts = service.districts_for_rung(
            rung, boundary, parameters=parameters, thresholds=fixed
        )
        return screen_rung(
            rung.number,
            districts,
            project_eligible_area_km2=treated_area,
            thresholds=fixed,
        )

    outcome = climb_ladder(
        screen=screen,
        count_admitted=count_admitted,
        parameters=parameters,
        ladder=LADDER,
    )

    manifest = build_manifest(
        boundary=boundary,
        treated_eligible_area_km2=treated_area,
        thresholds=fixed,
        parameters=parameters,
        dataset_refs=service.dataset_refs(parameters),
        rung_records=outcome.records,
        rung_used=outcome.rung_used,
        units=outcome.screening.eligible,
        exclusions=outcome.screening.exclusions,
        engine_version=engine_version,
        git_sha=git_sha,
    )

    logger.info(
        "unit set generated",
        extra={
            "case_id": boundary.case_id,
            "rung_used": outcome.rung_used,
            "eligible_candidates": outcome.eligible_candidates,
            "manifest_hash": manifest.content_hash,
        },
    )

    return UnitSet(
        case_id=boundary.case_id,
        treated_unit=_treated_unit_ref(boundary, treated_area),
        treated_eligible_area_km2=treated_area,
        candidates=outcome.screening.eligible,
        exclusions=outcome.screening.exclusions,
        outcome=outcome,
        manifest=manifest,
    )


def _treated_unit_ref(boundary: RegistryBoundary, eligible_area_km2: float) -> UnitRef:
    """The treated unit, carrying its **eligible** area as ADR-011 requires."""
    return UnitRef(
        unit_id=boundary.case_id,
        geometry=boundary.geometry,
        area_ha=eligible_area_km2 * HECTARES_PER_KM2,
        attributes={
            "eligible_area_km2": eligible_area_km2,
            "boundary_area_km2": boundary.boundary_area_km2,
        },
    )


class Adr011DonorCandidates:
    """``DonorCandidateAccess`` backed by ADR-011 unit construction.

    Satisfies the existing contract port without changing it: the engine asks
    for candidates, this returns the masked districts that survived the
    eligibility rules at the rung the ladder stopped on.
    """

    def __init__(
        self,
        *,
        boundary_path: str | Path,
        service: UnitConstructionService,
        parameters: RunParameters,
        count_admitted: AdmittedCounter,
        thresholds: Adr011Thresholds | None = None,
    ) -> None:
        self.boundary_path = boundary_path
        self.service = service
        self.parameters = parameters
        self.count_admitted = count_admitted
        self.thresholds = thresholds
        self.last_unit_set: UnitSet | None = None

    def candidates(self, request: AnalysisRequest) -> list[UnitRef]:
        """Generate candidates for a request.

        Raises:
            DataUnavailableError: if the masking inputs are unavailable. The
                engine surfaces this as a typed failure; it never receives
                fabricated units.
            DonorPoolError: if the ladder is exhausted.
        """
        unit_set = generate_unit_set(
            boundary_path=self.boundary_path,
            service=self.service,
            parameters=self.parameters,
            count_admitted=self.count_admitted,
            thresholds=self.thresholds,
            case_id=request.case_id,
        )
        self.last_unit_set = unit_set
        return list(unit_set.candidate_unit_refs())
