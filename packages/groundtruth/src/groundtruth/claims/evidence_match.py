"""Match a claim against the evidence the platform actually holds for the project.

Pure computation: no I/O, no database, no network. The caller supplies an
:class:`EvidenceContext` (the project's boundary area, its ingested observation series) and gets
back a :class:`ClaimOutcome`. Nothing is estimated and nothing is assumed: where the evidence
cannot establish a claim the outcome is ``UNVERIFIED`` and says exactly why and what would be
needed. A claim is never "verified" by this module, only *supported*, *partially supported*,
*contradicted* or *insufficiently evidenced*, and every outcome carries its limitations.

What can and cannot be matched
------------------------------
* **Area**: the claimed area is compared with the area of the project boundary the user uploaded
  (a measurement of that polygon). It can show a claim is consistent with, or larger than, the
  drawn boundary. It cannot show how much of the boundary has actually been restored.
* **Vegetation index change** (NDVI, EVI, ...): the claimed change is compared with the observed
  change between two annual satellite composites. This is an *observation* of greenness. It is not
  evidence of tree survival, carbon, biodiversity, or that the project caused the change (R1, R3).
* **Tree survival, trees planted, carbon, biodiversity, ecosystem recovery, causal attribution,
  absolute wording ("fully recovered")**: the platform holds no evidence that can establish these
  (they need field plots, a calibrated biomass model, a counterfactual, or are not observable from
  imagery). They are reported as insufficiently evidenced with the reason.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

SUPPORTED = "SUPPORTED"
PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
CONTRADICTED = "CONTRADICTED"
UNVERIFIED = "UNVERIFIED"

AREA_TOLERANCE = 0.05
"""A claimed area within +/-5% of the boundary area is treated as the same area."""
CHANGE_ABS_TOLERANCE = 0.02
CHANGE_REL_TOLERANCE = 0.25
"""An observed index change within max(0.02, 25% of the claimed change) matches the claim."""
CONTRADICTED_RATIO = 0.5
"""Observed change below half the claimed change contradicts the claim."""
COVERAGE_OK_PCT = 95.0

_AREA_TO_HA = {
    "ha": 1.0,
    "hectare": 1.0,
    "hectares": 1.0,
    "km2": 100.0,
    "sq km": 100.0,
    "square kilometre": 100.0,
    "square kilometres": 100.0,
    "square kilometer": 100.0,
    "square kilometers": 100.0,
    "acre": 0.404686,
    "acres": 0.404686,
}
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

OBSERVATION_METHOD = (
    "Difference between two annual composites of cloud-masked Sentinel-2 scenes, averaged inside "
    "the project boundary and restricted to one season each year."
)
GREENNESS_LIMITS = (
    "A vegetation index measures greenness. It does not measure tree survival, carbon, "
    "biodiversity or ecosystem condition.",
    "A change between two years is an observation. It does not show that the project caused it; "
    "rainfall and season timing also move greenness.",
)


@dataclass(frozen=True)
class ObservationSeries:
    """Annual observed values of one index: only years that carry a real value."""

    indicator: str
    values: Mapping[int, float]
    coverage_pct: Mapping[int, float | None] = field(default_factory=dict)
    source: str = "Sentinel-2 L2A annual composite inside the project boundary"


@dataclass(frozen=True)
class EvidenceContext:
    boundary_area_ha: float | None = None
    boundary_ref: str | None = None
    series: Mapping[str, ObservationSeries] = field(default_factory=dict)
    treatment_start_year: int | None = None


@dataclass(frozen=True)
class ClaimOutcome:
    status: str
    headline: str
    """One plain sentence stating the outcome."""
    reasons: list[str]
    """Why this outcome, and (for UNVERIFIED) why the claim cannot be established."""
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    available_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    observed_value: float | None = None
    observed_unit: str | None = None
    discrepancy_percentage: float | None = None
    methodology: str = ""


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}"


def _unverified(
    headline: str,
    reasons: list[str],
    *,
    required: list[str],
    missing: list[str],
    limitations: list[str] | None = None,
    method: str = "No platform check can establish this claim.",
) -> ClaimOutcome:
    return ClaimOutcome(
        status=UNVERIFIED,
        headline=headline,
        reasons=reasons,
        required_evidence=required,
        missing_evidence=missing,
        limitations=limitations or [],
        methodology=method,
    )


# --- area --------------------------------------------------------------------------------------


def _match_area(value: float | None, unit: str | None, ctx: EvidenceContext) -> ClaimOutcome:
    required = [
        "The project boundary as an uploaded polygon",
        "Field or imagery evidence of restored extent",
    ]
    if value is None or value <= 0:
        return _unverified(
            "The claimed area has no usable number.",
            ["A number such as 1,200 hectares is needed to compare with the boundary."],
            required=required,
            missing=["A numeric claimed area"],
        )
    factor = _AREA_TO_HA.get((unit or "ha").strip().lower())
    if factor is None:
        return _unverified(
            f"The area unit {unit!r} is not understood.",
            ["Use hectares (ha), square kilometres (km2) or acres."],
            required=required,
            missing=["A recognised area unit"],
        )
    if ctx.boundary_area_ha is None:
        return _unverified(
            "The project has no readable boundary to compare the area with.",
            ["Upload the project boundary first."],
            required=required,
            missing=["A readable project boundary"],
        )
    claimed_ha = value * factor
    boundary = ctx.boundary_area_ha
    diff_pct = (claimed_ha - boundary) / boundary * 100.0
    avail = [
        f"Project boundary area: {_fmt(boundary)} ha"
        + (f" ({ctx.boundary_ref})" if ctx.boundary_ref else "")
    ]
    limits = [
        "The boundary is a polygon drawn by the project. It shows where the project says it "
        "works, not how much of that land has actually been restored.",
    ]
    method = "Geodesic (equal-area) area of the uploaded boundary compared with the claimed area."
    common: dict[str, Any] = {
        "required_evidence": required,
        "available_evidence": avail,
        "limitations": limits,
        "observed_value": round(boundary, 2),
        "observed_unit": "ha",
        "discrepancy_percentage": round(diff_pct, 2),
        "methodology": method,
        "missing_evidence": ["Evidence of how much of the area was actually restored"],
    }
    if abs(diff_pct) <= AREA_TOLERANCE * 100:
        return ClaimOutcome(
            status=SUPPORTED,
            headline=f"The claimed {_fmt(claimed_ha)} ha matches the project boundary ({_fmt(boundary)} ha).",
            reasons=["The claimed area equals the boundary area within 5%."],
            supporting=[
                f"Claimed {_fmt(claimed_ha)} ha vs boundary {_fmt(boundary)} ha ({diff_pct:+.1f}%)."
            ],
            **common,
        )
    if claimed_ha > boundary:
        return ClaimOutcome(
            status=CONTRADICTED,
            headline=f"The claimed {_fmt(claimed_ha)} ha is larger than the whole project boundary ({_fmt(boundary)} ha).",
            reasons=[
                "Land cannot be restored outside the project boundary. Either the boundary or the claim is wrong."
            ],
            contradicting=[
                f"Claimed {_fmt(claimed_ha)} ha exceeds the boundary by {diff_pct:.1f}%."
            ],
            **common,
        )
    return ClaimOutcome(
        status=PARTIALLY_SUPPORTED,
        headline=f"The claimed {_fmt(claimed_ha)} ha fits inside the boundary ({_fmt(boundary)} ha), but how much was restored is not shown.",
        reasons=[
            "The claim is consistent with the boundary, but the boundary alone cannot confirm the claimed extent."
        ],
        supporting=[
            f"Claimed {_fmt(claimed_ha)} ha is {abs(diff_pct):.1f}% smaller than the boundary."
        ],
        **common,
    )


# --- vegetation index change ----------------------------------------------------------------------


def _indicator_of(unit: str | None) -> str:
    u = (unit or "").lower()
    for ind in ("evi", "ndmi", "nbr", "ndvi"):
        if ind in u:
            return ind
    return "ndvi"


def _period_years(period: str | None, observed: list[int]) -> tuple[int | None, int | None, str]:
    """Baseline and end year from the stated period, and a note on how they were chosen."""
    years = [int(y) for y in _YEAR_RE.findall(period or "")]
    lo, hi = min(observed), max(observed)
    if len(years) >= 2:
        return min(years), max(years), "Used the years stated in the claim."
    if len(years) == 1 and re.search(r"since|from|after|starting", period or "", re.I):
        return (
            years[0],
            hi,
            f"The claim says 'since {years[0]}', so it was compared with the latest observed year ({hi}).",
        )
    if len(years) == 1:
        return (
            years[0],
            hi,
            f"One year ({years[0]}) was stated; it was compared with the latest observed year ({hi}).",
        )
    return (
        lo,
        hi,
        f"No period was stated, so the earliest ({lo}) and latest ({hi}) observed years were compared.",
    )


def _match_index_change(
    value: float | None, unit: str | None, period: str | None, ctx: EvidenceContext
) -> ClaimOutcome:
    ind = _indicator_of(unit)
    required = [
        f"Annual {ind.upper()} observations inside the project boundary for the baseline year and a later year",
        "Observations from the same season each year, with the area covered",
    ]
    series = ctx.series.get(ind)
    if value is None:
        return _unverified(
            "The claimed change has no usable number.",
            [
                "A number such as 'NDVI increased by 0.15' is needed to compare with the observations."
            ],
            required=required,
            missing=["A numeric claimed change"],
        )
    if series is None or len(series.values) < 2:
        have = sorted(series.values) if series else []
        return _unverified(
            f"There are not enough {ind.upper()} observations to test this change.",
            [
                "Testing a change over time needs at least two years of observations inside the project boundary."
                + (
                    f" Only {have} {'is' if len(have) == 1 else 'are'} available."
                    if have
                    else " None have been ingested."
                ),
            ],
            required=required,
            missing=[
                f"{ind.upper()} observations for at least two years (request satellite data on the Earth observation tab)"
            ],
            limitations=list(GREENNESS_LIMITS),
            method=OBSERVATION_METHOD,
        )
    observed_years = sorted(series.values)
    base, end, note = _period_years(period, observed_years)
    missing_years = [y for y in (base, end) if y is not None and y not in series.values]
    if missing_years or base == end:
        return ClaimOutcome(
            status=UNVERIFIED,
            headline="The observations do not cover the years this claim compares.",
            reasons=[
                note,
                f"No {ind.upper()} value exists for {', '.join(map(str, sorted(set(missing_years)))) or 'a second year'}; available years: {observed_years}.",
            ],
            required_evidence=required,
            available_evidence=[f"{ind.upper()} observed for {observed_years}"],
            missing_evidence=[
                f"{ind.upper()} observations for {', '.join(map(str, sorted(set(missing_years))))}"
                if missing_years
                else "A second observed year"
            ],
            limitations=list(GREENNESS_LIMITS),
            methodology=OBSERVATION_METHOD,
        )
    assert base is not None and end is not None
    obs = series.values[end] - series.values[base]
    ratio = obs / value if value else float("inf")
    diff_pct = (obs - value) / abs(value) * 100.0 if value else None
    cov_base, cov_end = series.coverage_pct.get(base), series.coverage_pct.get(end)
    low_cov = [
        y for y, c in ((base, cov_base), (end, cov_end)) if c is not None and c < COVERAGE_OK_PCT
    ]
    avail = [
        f"{ind.upper()} {base}: {series.values[base]:.3f}; {end}: {series.values[end]:.3f} ({series.source})",
    ]
    limits = list(GREENNESS_LIMITS)
    all_vals = [series.values[y] for y in observed_years]
    if len(all_vals) >= 3:
        lo_v, hi_v = min(all_vals), max(all_vals)
        by_year = ", ".join(f"{y} {series.values[y]:.3f}" for y in observed_years)
        avail.append(f"All observed years: {by_year}")
        if hi_v - lo_v >= abs(value):
            limits.append(
                f"Across all {len(all_vals)} observed years {ind.upper()} ranged from {lo_v:.3f} to "
                f"{hi_v:.3f} (a spread of {hi_v - lo_v:.3f}), as large as the claimed change. A "
                "difference between two years can reflect year-to-year variation rather than a trend."
            )
    if low_cov:
        limits.append(
            f"The project area was covered below {COVERAGE_OK_PCT:g}% in {', '.join(map(str, low_cov))}, "
            "so the comparison rests on part of the area."
        )
    common: dict[str, Any] = {
        "required_evidence": required,
        "available_evidence": avail,
        "missing_evidence": [
            "Evidence that the change was caused by the project (a comparison with similar untreated land)"
        ],
        "limitations": limits,
        "observed_value": round(obs, 4),
        "observed_unit": f"{ind}_units",
        "discrepancy_percentage": round(diff_pct, 2) if diff_pct is not None else None,
        "methodology": OBSERVATION_METHOD,
    }
    summary = f"observed {ind.upper()} change {base}->{end}: {obs:+.3f} (claimed {value:+.3f})"
    tol = max(CHANGE_ABS_TOLERANCE, CHANGE_REL_TOLERANCE * abs(value))
    if (value > 0 and obs <= 0) or (value < 0 and obs >= 0):
        return ClaimOutcome(
            status=CONTRADICTED,
            headline=f"The observations show the opposite direction: {summary}.",
            reasons=[note, "The satellite record moves in the opposite direction to the claim."],
            contradicting=[summary],
            **common,
        )
    if abs(obs - value) <= tol:
        status = PARTIALLY_SUPPORTED if low_cov else SUPPORTED
        reasons = [note, f"The observed change is within {tol:.3f} of the claimed change."]
        if low_cov:
            reasons.append(
                "Supported only in part because the area was not fully covered in every year."
            )
        return ClaimOutcome(
            status=status,
            headline=f"The observed greenness change matches the claim: {summary}.",
            reasons=reasons,
            supporting=[summary],
            **common,
        )
    if ratio < CONTRADICTED_RATIO:
        return ClaimOutcome(
            status=CONTRADICTED,
            headline=f"The observed change is less than half of what is claimed: {summary}.",
            reasons=[note, "The claim overstates the change the satellite record shows."],
            contradicting=[summary],
            **common,
        )
    return ClaimOutcome(
        status=PARTIALLY_SUPPORTED,
        headline=f"The observed change is in the same direction but does not match the claimed size: {summary}.",
        reasons=[
            note,
            "Same direction as the claim, but the size differs by more than the tolerance.",
        ],
        supporting=[f"Same direction: {summary}."],
        **common,
    )


# --- claims no available evidence can establish ---------------------------------------------------------

_CANNOT: dict[str, tuple[str, list[str], list[str], list[str]]] = {
    "survival_rate": (
        "Tree survival cannot be established from satellite greenness.",
        [
            "Survival means counting which planted trees are still alive. Satellite greenness cannot tell planted trees from other vegetation.",
        ],
        ["Dated field survey of sample plots (planted vs surviving stems, with locations)"],
        ["A field survey with plot locations and stem counts"],
    ),
    "trees_planted": (
        "The number of trees planted cannot be established from satellite data.",
        ["Planting counts come from nursery, purchase and planting records, not from imagery."],
        ["Planting records: dates, locations, species, quantities"],
        ["Planting records"],
    ),
    "carbon_tco2e": (
        "Carbon cannot be established: a vegetation index is not carbon.",
        [
            "Converting greenness to tonnes of CO2e needs a site-calibrated biomass model built from field measurements. None is available, so no carbon figure is produced (NDVI is not carbon).",
        ],
        [
            "Site-calibrated biomass/allometry from field plots",
            "A verified baseline and additionality assessment",
        ],
        ["A calibrated biomass model and field plots"],
    ),
    "index_to_carbon_conflation": (
        "A vegetation index cannot be converted to carbon.",
        [
            "NDVI/EVI measure greenness. Treating them as carbon stock is not supported by any evidence here."
        ],
        ["Site-calibrated biomass model from field plots"],
        ["A calibrated biomass model"],
    ),
    "biodiversity_recovery": (
        "Biodiversity recovery cannot be established from satellite imagery.",
        [
            "Biodiversity is measured by species surveys. Greenness cannot show which species are present, so it cannot show recovery.",
        ],
        ["Dated species surveys against a baseline or reference site"],
        ["Species survey data"],
    ),
    "ecosystem_recovery": (
        "Ecosystem recovery cannot be established from greenness alone.",
        [
            "Recovery covers soil, water, species and structure. A greenness series covers none of these directly."
        ],
        ["Field monitoring of structure, species and soil against a reference ecosystem"],
        ["Field monitoring data"],
    ),
    "causal_attribution": (
        "Attributing a change to the project cannot be established without a counterfactual.",
        [
            "Showing the project caused a change needs a comparison with similar land that was not treated. None has been ingested for this project."
        ],
        ["Vegetation series for comparable untreated areas covering the same years"],
        ["A comparison (donor) panel of untreated areas"],
    ),
    "unsupported_conclusion": (
        "This statement goes further than any available evidence can establish.",
        [
            "Absolute wording such as 'proves' or 'fully recovered' cannot be established by remote-sensing evidence, and no field evidence is available.",
        ],
        ["Independent field evidence that directly supports the stated conclusion"],
        ["Evidence for the stated conclusion"],
    ),
}


KIND_LABELS: dict[str, str] = {
    "area_hectares": "Area (hectares)",
    "vegetation_index_change": "Greenness change (vegetation index)",
    "survival_rate": "Tree survival rate",
    "carbon_tco2e": "Carbon (tCO2e)",
    "index_to_carbon_conflation": "Index converted to carbon",
    "biodiversity_recovery": "Biodiversity recovery",
    "ecosystem_recovery": "Ecosystem recovery",
    "causal_attribution": "Caused by the project",
    "unsupported_conclusion": "Absolute conclusion",
}
CHECKABLE_KINDS = frozenset({"area_hectares", "vegetation_index_change"})


def kind_note(kind: str) -> str:
    """Plain-language statement of whether, and how, the platform can check this kind of claim."""
    if kind == "area_hectares":
        return "Checked against the area of your uploaded boundary."
    if kind == "vegetation_index_change":
        return "Checked against the satellite greenness record, once observations are ingested."
    cannot = _CANNOT.get(kind)
    return "Cannot be established with the evidence the platform holds. " + (
        cannot[1][0] if cannot else ""
    )


def match_claim(
    kind: str,
    value: float | None,
    unit: str | None,
    period: str | None,
    ctx: EvidenceContext,
) -> ClaimOutcome:
    """Match one claim against ``ctx``. ``kind`` is a statement kind such as ``area_hectares``."""
    if kind == "area_hectares":
        return _match_area(value, unit, ctx)
    if kind == "vegetation_index_change":
        return _match_index_change(value, unit, period, ctx)
    if kind in _CANNOT:
        headline, reasons, required, missing = _CANNOT[kind]
        return _unverified(headline, reasons, required=required, missing=missing)
    return _unverified(
        "This kind of claim has no platform check.",
        [f"The claim type {kind!r} is not one the platform can match against evidence."],
        required=["Evidence appropriate to the claim"],
        missing=["A supported claim type"],
    )


__all__ = [
    "CHECKABLE_KINDS",
    "CONTRADICTED",
    "KIND_LABELS",
    "PARTIALLY_SUPPORTED",
    "SUPPORTED",
    "UNVERIFIED",
    "ClaimOutcome",
    "EvidenceContext",
    "ObservationSeries",
    "kind_note",
    "match_claim",
]
