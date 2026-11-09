"""``assess``: levels, the eight dimensions, layered conclusions, recommendations."""

from __future__ import annotations

import dataclasses

from groundtruth.engine.assessment.dimensions import (
    aligned_climate,
    clean_all,
    climate_context,
    comparative_performance,
    ecological_risk,
    eligible_donors,
    evidence_quality,
    intervention_attribution,
    restoration_progress,
    spatial_performance,
    vegetation_trajectory,
)
from groundtruth.engine.assessment.recommendations import recommend
from groundtruth.engine.assessment.rules import (
    LEVEL_NAMES,
    MIN_CLIMATE_OVERLAP_YEARS,
    MIN_LEVEL_PERIODS,
    MIN_REFERENCE_DONORS,
)
from groundtruth.engine.assessment.types import (
    Assessment,
    AssessmentInputs,
    Conclusion,
    DimensionResult,
)

SIMULATED_BANNER = (
    "SIMULATED DATA: these inputs are synthetic. Nothing here is evidence about a real project."
)


def compute_level(inputs: AssessmentInputs) -> int:
    """The strongest level every one of whose conditions is computed from the inputs.

    Levels never skip: each requires the one below. A single period is not Level 1 and
    there is no lower level, so it stays at 0.
    """
    r = inputs.readiness
    series = clean_all(inputs.series)
    if not r.boundary_verified or not series:
        return 0
    l1 = {ind: pts for ind, pts in series.items() if len(pts) >= MIN_LEVEL_PERIODS}
    if not l1:
        return 0
    years = sorted({p.year for pts in l1.values() for p in pts})
    if len(aligned_climate(inputs, years)) < MIN_CLIMATE_OVERLAP_YEARS:
        return 1
    reference = inputs.reference_series or {}
    has_reference = any(
        len(eligible_donors(pts, reference[ind])) >= MIN_REFERENCE_DONORS
        for ind, pts in l1.items()
        if ind in reference
    )
    if not has_reference:
        return 2
    if not (r.attribution_ready and r.causal_run_completed):
        return 3
    return 5 if inputs.field_evidence else 4


def _mark(text: str) -> str:
    return f"[SIMULATED DATA] {text}"


def _observed_outcome(d1: DimensionResult) -> Conclusion:
    trends = d1.facts.get("trends", {})
    lines = [
        f"{ind} {t.change:+.3f} from {t.first_year} to {t.last_year} ({t.n} periods)"
        for ind, t in trends.items()
        if t.change is not None
    ]
    if not lines:
        return Conclusion(
            summary="No change can be reported: fewer than two real observations exist.",
            dimension_ids=(d1.id,),
            estimable=False,
            reason="Needs at least two annual observations.",
        )
    return Conclusion(
        summary="Observed change (not a causal effect): " + "; ".join(lines) + ".",
        dimension_ids=(d1.id, "restoration_progress"),
    )


def assess(inputs: AssessmentInputs) -> Assessment:
    level = compute_level(inputs)
    simulated = inputs.data_mode == "simulated"

    d1 = vegetation_trajectory(inputs)
    d2 = spatial_performance(inputs)
    d3 = climate_context(inputs)
    d4 = ecological_risk(inputs)
    d5 = restoration_progress(inputs, d1)
    d6 = comparative_performance(inputs)
    d7 = evidence_quality(inputs, level, d1)
    attribution, d8 = intervention_attribution(inputs, level, d7)
    if attribution.verdict == "Supported" and level < 4:  # defensive: never reachable
        raise AssertionError("attribution Supported requires assessment level >= 4")

    dims = [d1, d2, d3, d4, d5, d6, d7, d8]
    observed_outcome = _observed_outcome(d1)
    ecological = Conclusion(
        summary=(
            f"Vegetation trajectory: {d1.status}. Spatial performance: {d2.status}. "
            f"Ecological risk: {d4.status}."
            + (
                " Risk findings are signals that require field verification."
                if d4.status == "Elevated ecological risk"
                else ""
            )
        ),
        dimension_ids=(d1.id, d2.id, d4.id),
    )
    if d3.facts.get("estimable"):
        climate = Conclusion(summary=d3.finding, dimension_ids=(d3.id,))
    else:
        climate = Conclusion(
            summary="A climate-adjusted interpretation is not estimable.",
            dimension_ids=(d3.id,),
            estimable=False,
            reason=str(d3.facts.get("reason") or d3.finding),
        )
    comparable = d6.status != "Insufficient evidence"
    comparative = Conclusion(
        summary=d6.finding,
        dimension_ids=(d6.id,),
        estimable=comparable,
        reason=None if comparable else d6.finding,
    )

    if simulated:
        dims = [dataclasses.replace(d, finding=_mark(d.finding)) for d in dims]
        observed_outcome = dataclasses.replace(
            observed_outcome, summary=_mark(observed_outcome.summary)
        )
        ecological = dataclasses.replace(ecological, summary=_mark(ecological.summary))
        climate = dataclasses.replace(climate, summary=_mark(climate.summary))
        comparative = dataclasses.replace(comparative, summary=_mark(comparative.summary))
        attribution = dataclasses.replace(attribution, finding=_mark(attribution.finding))

    by_id = {d.id: d for d in dims}
    return Assessment(
        level=level,
        level_name=LEVEL_NAMES[level] + (" (simulated)" if simulated else ""),
        dimensions=tuple(dims),
        observed_outcome=observed_outcome,
        ecological_assessment=ecological,
        climate_adjusted_interpretation=climate,
        comparative_assessment=comparative,
        attribution=attribution,
        evidence_confidence=d7.status,
        recommendations=recommend(inputs, level, by_id),
        data_mode=inputs.data_mode,
        simulated_banner=SIMULATED_BANNER if simulated else None,
    )
