"""The recommendation engine: a rule table that fires only on actual findings.

Each rule is ``(id, trigger, text_template, priority, personas)``. A trigger reads the
computed dimension results and returns a ``TriggerHit`` (the rationale, the evidence it
cites and the template values) or ``None``. With no hit there is no recommendation: there is
never generic filler. Personas see the same recommendations; their wording never changes a
finding.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from groundtruth.engine.assessment.dimensions import clean_all
from groundtruth.engine.assessment.rules import (
    COVERAGE_COMPLETE,
    COVERAGE_REVIEW,
    MIN_REFERENCE_DONORS,
    MIN_TREND_PERIODS,
)
from groundtruth.engine.assessment.types import (
    PERSONAS,
    AssessmentInputs,
    DimensionResult,
    Recommendation,
)


@dataclass(frozen=True, slots=True)
class RuleContext:
    inputs: AssessmentInputs
    level: int
    dims: Mapping[str, DimensionResult]


@dataclass(frozen=True, slots=True)
class TriggerHit:
    rationale: str
    source_dimensions: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()
    params: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecommendationRule:
    id: str
    trigger: Callable[[RuleContext], TriggerHit | None]
    text_template: str
    priority: int  # 1 is the most urgent
    personas: tuple[str, ...]


def _years(values: Sequence[int]) -> str:
    return ", ".join(str(v) for v in values)


# -- triggers ---------------------------------------------------------------------------


def _field_verification(ctx: RuleContext) -> TriggerHit | None:
    if ctx.level >= 5:
        return None
    d1, d5 = ctx.dims["vegetation_trajectory"], ctx.dims["restoration_progress"]
    sources = [d for d in (d1, d5) if d.status == "Improving"]
    if not sources:
        return None
    basis = " and ".join(d.title.lower() for d in sources)
    return TriggerHit(
        rationale=sources[0].finding,
        source_dimensions=tuple(d.id for d in sources),
        evidence_refs=tuple(dict.fromkeys(r for d in sources for r in d.evidence_refs)),
        params={"basis": basis, "level": str(ctx.level)},
    )


def _drought_explanation(ctx: RuleContext) -> TriggerHit | None:
    d4 = ctx.dims["ecological_risk"]
    drought = set(d4.facts.get("drought_years", ()))
    hits = [(ind, yr) for ind, yr in d4.facts.get("decline_signals", ()) if yr in drought]
    if not hits:
        return None
    spi = {
        row["year"]: row["spi12"] for row in ctx.dims["climate_context"].facts.get("per_year", ())
    }
    detail = "; ".join(
        f"{ind} in {yr} (SPI-12 {spi[yr]:+.2f})" if spi.get(yr) is not None else f"{ind} in {yr}"
        for ind, yr in hits
    )
    return TriggerHit(
        rationale=f"A vegetation-decline signal coincides with a drought-stress year: {detail}.",
        source_dimensions=("ecological_risk", "climate_context"),
        evidence_refs=d4.evidence_refs,
        params={"detail": detail},
    )


def _more_observations(ctx: RuleContext) -> TriggerHit | None:
    d1, d7 = ctx.dims["vegetation_trajectory"], ctx.dims["evidence_quality"]
    weak = d1.limitation == "weak_statistical_power"
    low_cov = tuple(d7.facts.get("low_coverage_years", ()))
    if not weak and not low_cov:
        return None
    parts: list[str] = []
    rationale: list[str] = []
    observed = tuple(d1.facts.get("observed_years", ()))
    n = int(d1.facts.get("n_periods", 0))
    if weak:
        if n < MIN_TREND_PERIODS:
            parts.append(
                f"only {n} annual period(s) are observed ({_years(observed) or 'none'}) and a "
                f"trend test needs at least {MIN_TREND_PERIODS}, so at least "
                f"{MIN_TREND_PERIODS - n} more year(s) of observations are needed"
            )
        else:
            parts.append(
                "extend the monitoring record: the slope interval is too wide to call the "
                "trajectory stable or changing"
            )
        rationale.append(d1.finding)
    missing = tuple(d1.facts.get("missing_years", ()))
    if missing:
        parts.append(f"years with no observation inside the monitored span: {_years(missing)}")
    if low_cov:
        cov = ", ".join(f"{y} ({c:.0f}%)" for y, c in low_cov)
        parts.append(
            f"AOI coverage is below {COVERAGE_COMPLETE:.0f}% in {cov}; recover the missing tiles"
        )
        rationale.append(f"AOI coverage is below {COVERAGE_COMPLETE:.0f}% in {cov}.")
    return TriggerHit(
        rationale=" ".join(rationale),
        source_dimensions=("vegetation_trajectory", "evidence_quality"),
        evidence_refs=tuple(dict.fromkeys((*d1.evidence_refs, *d7.evidence_refs))),
        params={"detail": "; ".join(parts)},
    )


def _reference_series(ctx: RuleContext) -> TriggerHit | None:
    d6, d8 = ctx.dims["comparative_performance"], ctx.dims["intervention_attribution"]
    no_donor_series = d6.limitation == "missing_data" and d6.status == "Insufficient evidence"
    attribution_needs_donors = (
        d8.limitation == "missing_data" and not ctx.inputs.readiness.donor_panel_available
    )
    if not no_donor_series and not attribution_needs_donors:
        return None
    sources = [d for d in (d6, d8) if d.limitation == "missing_data"]
    return TriggerHit(
        rationale=" ".join(d.finding for d in sources),
        source_dimensions=tuple(d.id for d in sources),
        evidence_refs=tuple(dict.fromkeys(r for d in sources for r in d.evidence_refs)),
        params={"min_donors": str(MIN_REFERENCE_DONORS)},
    )


def _deteriorating_zones(ctx: RuleContext) -> TriggerHit | None:
    d2 = ctx.dims["spatial_performance"]
    zones = tuple(d2.facts.get("deteriorating_zones", ()))
    if d2.status not in {"Deteriorating", "Mixed spatial performance"} or not zones:
        return None
    return TriggerHit(
        rationale=d2.finding,
        source_dimensions=("spatial_performance",),
        evidence_refs=d2.evidence_refs,
        params={"zones": ", ".join(zones)},
    )


def _review_boundary_or_period(ctx: RuleContext) -> TriggerHit | None:
    series = clean_all(ctx.inputs.series)
    observed = sorted({p.year for pts in series.values() for p in pts})
    if not observed:
        return None
    reasons: list[str] = []
    refs: list[str] = []
    low = [
        (y, ctx.inputs.coverage_pct[y])
        for y in observed
        if y in ctx.inputs.coverage_pct and ctx.inputs.coverage_pct[y] < COVERAGE_REVIEW
    ]
    if low:
        reasons.append(
            f"AOI coverage is below {COVERAGE_REVIEW:.0f}% in "
            + ", ".join(f"{y} ({c:.0f}%)" for y, c in low)
        )
        bad = {y for y, _ in low}
        refs += [
            r for pts in series.values() for p in pts if p.year in bad for r in p.evidence_refs
        ]
    start = ctx.inputs.treatment_start_year
    if observed[0] > start:
        reasons.append(
            f"the observed period starts in {observed[0]}, after the {start} treatment start, "
            "so no pre-treatment baseline is observed"
        )
        refs += [
            r
            for pts in series.values()
            for p in pts
            if p.year == observed[0]
            for r in p.evidence_refs
        ]
    if not reasons:
        return None
    detail = "; ".join(reasons)
    return TriggerHit(
        rationale=detail[0].upper() + detail[1:] + ".",
        source_dimensions=("evidence_quality",),
        evidence_refs=tuple(dict.fromkeys(refs)),
        params={"detail": detail},
    )


def _increase_oversight(ctx: RuleContext) -> TriggerHit | None:
    d7 = ctx.dims["evidence_quality"]
    if d7.status != "Low" or not ctx.inputs.claim_present:
        return None
    return TriggerHit(
        rationale=f"An attribution claim exists, and {d7.finding[0].lower()}{d7.finding[1:]}",
        source_dimensions=("evidence_quality",),
        evidence_refs=d7.evidence_refs,
    )


_ALL = PERSONAS

RULES: tuple[RecommendationRule, ...] = (
    RecommendationRule(
        "field_verification_before_claims",
        _field_verification,
        "Commission independent field verification before any restoration or recovery claim "
        "is made. Basis: {basis} is Improving, and no independent field observations are "
        "attached (assessment level {level} of 5).",
        1,
        _ALL,
    ),
    RecommendationRule(
        "investigate_drought_explanation",
        _drought_explanation,
        "Investigate drought as an explanation before attributing the decline to management "
        "or land use: {detail}. Verify in the field.",
        2,
        _ALL,
    ),
    RecommendationRule(
        "inspect_deteriorating_zones",
        _deteriorating_zones,
        "Prioritise field inspection of the deteriorating zones: {zones}.",
        2,
        _ALL,
    ),
    RecommendationRule(
        "increase_oversight",
        _increase_oversight,
        "Increase oversight of this claim: evidence quality is Low while an attribution "
        "claim is being made. Request accredited review before relying on it.",
        2,
        ("funder", "government"),
    ),
    RecommendationRule(
        "review_boundary_or_period",
        _review_boundary_or_period,
        "Review the project boundary or the monitoring period: {detail}.",
        3,
        _ALL,
    ),
    RecommendationRule(
        "acquire_more_observations",
        _more_observations,
        "Acquire additional observations: {detail}.",
        3,
        _ALL,
    ),
    RecommendationRule(
        "acquire_reference_series",
        _reference_series,
        "Acquire vegetation series from at least {min_donors} eligible reference areas "
        "covering the same indicator and years; without them neither a comparison nor an "
        "attribution assessment is possible.",
        4,
        _ALL,
    ),
)


def recommend(
    inputs: AssessmentInputs, level: int, dims: Mapping[str, DimensionResult]
) -> tuple[Recommendation, ...]:
    ctx = RuleContext(inputs=inputs, level=level, dims=dims)
    out: list[Recommendation] = []
    for rule in RULES:
        hit = rule.trigger(ctx)
        if hit is None:
            continue
        refs = hit.evidence_refs or tuple(f"dimension:{d}" for d in hit.source_dimensions)
        out.append(
            Recommendation(
                id=rule.id,
                text=rule.text_template.format(**hit.params),
                rationale=hit.rationale,
                priority=rule.priority,
                personas=rule.personas,
                evidence_refs=refs,
            )
        )
    return tuple(sorted(out, key=lambda r: (r.priority, r.id)))


def recommendations_for_persona(
    recommendations: Sequence[Recommendation], persona: str
) -> tuple[Recommendation, ...]:
    """The same recommendations, filtered to those addressed to the persona."""
    if persona not in PERSONAS:
        raise ValueError(f"unknown persona {persona!r}; expected one of {PERSONAS}")
    return tuple(
        sorted(
            (r for r in recommendations if persona in r.personas),
            key=lambda r: (r.priority, r.id),
        )
    )
