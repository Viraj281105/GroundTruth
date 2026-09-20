"""ADR-011's admission rules and the fixed search-region ladder.

This module is pure: it takes *measured facts* about candidate districts and
decides what ADR-011 says about them. It measures nothing itself. That split is
deliberate — the measurements need a geometry engine and pinned rasters
(:mod:`groundtruth.platform.units.provider`, issue #23), while the rules need to
be readable, testable and impossible to tune.

Two things here are the whole point of the ADR:

**Exclusion reasons are structured, not prose.** Every rejection carries a
category and a human-readable sentence with the numbers that caused it, so a
donor table can be challenged rather than trusted.

**The ladder has one stopping rule.** Advance a rung if and only if the current
rung yields fewer than ``pool_size`` eligible candidates *or* fewer than
``min_donors`` admitted donors; stop at the first rung satisfying both. Both
counts are recorded at every rung climbed, including rungs that were passed,
because that record is the only way a reader can check the rule was followed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from groundtruth.contracts.errors import DonorPoolError
from groundtruth.platform.units.spec import LADDER, Adr011Thresholds, Rung, RunParameters


class ExclusionCategory(StrEnum):
    """Why a district never became a donor candidate.

    These fire during candidate generation, before covariates exist, so they
    cannot be carried on ``DonorMatch``. They belong in the unit-set manifest.
    The matching stage has its own, separate exclusion reasons (leakage-belt
    membership, common-support caliper, pre-period coverage).
    """

    EMPTY_AFTER_MASK = "empty_after_mask"
    ECOREGION_SHARE = "ecoregion_share"
    AREA_FLOOR = "area_floor"
    AREA_BAND = "area_band"
    LEAKAGE_BELT = "leakage_belt"
    CARBON_PROJECT = "carbon_project"


@dataclass(frozen=True, slots=True)
class DistrictFacts:
    """Everything ADR-011's admission rules need to know about one district.

    Produced by the masking provider, never by this module. Areas are measured
    *after* the full eligibility mask and the 300 m inward buffer, because that
    is the quantity ADR-011's band and floor are defined on.
    """

    unit_id: str
    """``gaul2015:{ADM2_CODE}``."""

    adm2_code: str
    country: str
    eligible_area_km2: float
    """Area after masking and inward buffering. Zero if the mask emptied it."""

    forest_share_in_target_ecoregions: float
    """Share of the district's baseline-forest area inside the rung's ecoregions."""

    intersects_leakage_belt: bool
    """Whether the district meets the 10 km belt around the unmasked registry boundary."""

    contains_registered_project_without_geometry: bool
    """A registry point for another credited project falls inside this district."""

    fragments: int = 1
    """Disconnected pieces after masking. Recorded; never used to split or drop a unit."""

    geometry_hash: str = ""
    """Hash of the masked geometry, for the manifest."""


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One district, and the rule that rejected it."""

    unit_id: str
    category: ExclusionCategory
    reason: str


@dataclass(frozen=True, slots=True)
class Screening:
    """The outcome of applying the eligibility rules to one rung's districts."""

    rung: int
    eligible: tuple[DistrictFacts, ...]
    exclusions: tuple[Exclusion, ...]

    @property
    def eligible_count(self) -> int:
        """Districts that survived every eligibility rule."""
        return len(self.eligible)

    @property
    def screened_count(self) -> int:
        """Districts considered at this rung."""
        return self.eligible_count + len(self.exclusions)

    def counts_by_category(self) -> dict[str, int]:
        """Exclusions per category, with every category present, including zeros."""
        counts = {c.value: 0 for c in ExclusionCategory}
        for exclusion in self.exclusions:
            counts[exclusion.category.value] += 1
        return counts


def evaluate_district(
    facts: DistrictFacts,
    *,
    project_eligible_area_km2: float,
    thresholds: Adr011Thresholds,
) -> Exclusion | None:
    """Apply ADR-011's admission rules to one district.

    Rules are evaluated in a fixed order so that a district failing several of
    them always reports the same reason. The order runs from "there is nothing
    here" through contamination to comparability.

    Args:
        facts: Measured facts for the district.
        project_eligible_area_km2: The treated unit's eligible area, which sets
            the band.
        thresholds: ADR-011's fixed thresholds.

    Returns:
        ``None`` if the district is eligible, otherwise the :class:`Exclusion`
        that rejected it.
    """
    lower, upper = thresholds.area_band_km2(project_eligible_area_km2)

    if facts.eligible_area_km2 <= 0:
        return Exclusion(
            unit_id=facts.unit_id,
            category=ExclusionCategory.EMPTY_AFTER_MASK,
            reason="no eligible area remains after the pre-treatment mask and inward buffer",
        )

    if facts.contains_registered_project_without_geometry:
        return Exclusion(
            unit_id=facts.unit_id,
            category=ExclusionCategory.CARBON_PROJECT,
            reason=(
                "a registered carbon project is located in this district and no geometry is "
                "available to subtract, so the district is excluded whole (conservative)"
            ),
        )

    if facts.intersects_leakage_belt:
        return Exclusion(
            unit_id=facts.unit_id,
            category=ExclusionCategory.LEAKAGE_BELT,
            reason=(
                f"intersects the {thresholds.leakage_belt_km:g} km leakage belt around the "
                "project boundary (potential spillover contamination)"
            ),
        )

    if facts.forest_share_in_target_ecoregions < thresholds.ecoregion_min_forest_share:
        return Exclusion(
            unit_id=facts.unit_id,
            category=ExclusionCategory.ECOREGION_SHARE,
            reason=(
                f"only {facts.forest_share_in_target_ecoregions:.1%} of baseline forest falls in a "
                f"target ecoregion, below the "
                f"{thresholds.ecoregion_min_forest_share:.0%} rule"
            ),
        )

    if facts.eligible_area_km2 < thresholds.min_eligible_area_km2:
        return Exclusion(
            unit_id=facts.unit_id,
            category=ExclusionCategory.AREA_FLOOR,
            reason=(
                f"eligible area {facts.eligible_area_km2:,.0f} km² is below the "
                f"{thresholds.min_eligible_area_km2:,.0f} km² floor, so the zonal mean would be "
                "composition-driven"
            ),
        )

    if not (lower <= facts.eligible_area_km2 <= upper):
        return Exclusion(
            unit_id=facts.unit_id,
            category=ExclusionCategory.AREA_BAND,
            reason=(
                f"eligible area {facts.eligible_area_km2:,.0f} km² is outside the "
                f"[{lower:,.0f}, {upper:,.0f}] km² band around the project's eligible area of "
                f"{project_eligible_area_km2:,.0f} km²"
            ),
        )

    return None


def screen_rung(
    rung: int,
    districts: Sequence[DistrictFacts],
    *,
    project_eligible_area_km2: float,
    thresholds: Adr011Thresholds,
) -> Screening:
    """Apply the eligibility rules to every district considered at one rung.

    Eligible districts are returned in ``unit_id`` order so that the candidate
    set is a deterministic function of its inputs and not of dictionary or file
    ordering.
    """
    eligible: list[DistrictFacts] = []
    exclusions: list[Exclusion] = []
    for facts in sorted(districts, key=lambda d: d.unit_id):
        outcome = evaluate_district(
            facts,
            project_eligible_area_km2=project_eligible_area_km2,
            thresholds=thresholds,
        )
        if outcome is None:
            eligible.append(facts)
        else:
            exclusions.append(outcome)
    return Screening(rung=rung, eligible=tuple(eligible), exclusions=tuple(exclusions))


@dataclass(frozen=True, slots=True)
class RungRecord:
    """What happened at one rung of the ladder. Recorded whether or not it was used."""

    rung: int
    description: str
    countries: tuple[str, ...]
    ecoregions: tuple[str, ...]
    districts_screened: int
    eligible_candidates: int
    admitted_donors: int
    exclusions_by_category: dict[str, int]
    satisfied_stopping_rule: bool


@dataclass(frozen=True, slots=True)
class LadderOutcome:
    """The ladder's result: which rung was used, and the full climb record."""

    rung_used: int
    screening: Screening
    records: tuple[RungRecord, ...] = field(default=())

    @property
    def eligible_candidates(self) -> int:
        """Eligible candidate count at the rung finally used."""
        return self.screening.eligible_count


def climb_ladder(
    *,
    screen: Callable[[Rung], Screening],
    count_admitted: Callable[[Rung, Screening], int],
    parameters: RunParameters,
    ladder: Sequence[Rung] = LADDER,
) -> LadderOutcome:
    """Climb ADR-011's fixed search-region ladder.

    The stopping rule, stated once and applied without discretion:

        Advance to the next rung if and only if the current rung yields fewer
        than ``pool_size`` eligible candidates **or** fewer than ``min_donors``
        admitted donors. Stop at the first rung that satisfies both.

    Climbing costs a covariate pass per rung, because the admitted count is only
    knowable after matching. That is the price of a rule with no judgement in it.

    Args:
        screen: Applies the eligibility rules to one rung's districts.
        count_admitted: Runs matching for a rung's eligible candidates and
            returns how many donors were admitted.
        parameters: The run's pinned open parameters, including ``pool_size``
            and ``min_donors``.
        ladder: The rungs, in climb order. Defaults to ADR-011's three.

    Returns:
        The :class:`LadderOutcome` for the first rung satisfying both conditions.

    Raises:
        DonorPoolError: if the last rung still fails either condition. Refusing
            is the correct outcome, not a problem to engineer around.
    """
    parameters.validate()
    records: list[RungRecord] = []

    for rung in ladder:
        screening = screen(rung)
        admitted = count_admitted(rung, screening)
        satisfied = (
            screening.eligible_count >= parameters.pool_size and admitted >= parameters.min_donors
        )
        records.append(
            RungRecord(
                rung=rung.number,
                description=rung.description,
                countries=rung.countries,
                ecoregions=parameters.ecoregions_for(rung),
                districts_screened=screening.screened_count,
                eligible_candidates=screening.eligible_count,
                admitted_donors=admitted,
                exclusions_by_category=screening.counts_by_category(),
                satisfied_stopping_rule=satisfied,
            )
        )
        if satisfied:
            return LadderOutcome(rung_used=rung.number, screening=screening, records=tuple(records))

    last = records[-1]
    raise DonorPoolError(
        f"the search-region ladder was exhausted at rung {last.rung}: "
        f"{last.eligible_candidates} eligible candidates (need {parameters.pool_size}) and "
        f"{last.admitted_donors} admitted donors (need {parameters.min_donors}). "
        "ADR-011 refuses the case rather than widening the search further or relaxing a rule."
    )
