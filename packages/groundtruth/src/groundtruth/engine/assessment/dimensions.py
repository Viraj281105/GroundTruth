"""The eight assessment dimensions (spec section 6A).

Each function turns real inputs into one ``DimensionResult`` and is independent of
attribution: a project that cannot be attributed still receives every other dimension its
evidence supports. Findings are deterministic sentences built from the numbers; absent
evidence is stated as absent, never filled in.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

import numpy as np

from groundtruth.engine.assessment.rules import (
    CLIMATE_ADJUST_MIN_YEARS,
    COVERAGE_COMPLETE,
    DROUGHT_SPI,
    MIN_REFERENCE_DONORS,
    MIN_REFERENCE_OVERLAP_PERIODS,
    MIN_TREND_PERIODS,
    RISK_SIGNAL_LABEL,
    WET_SPI,
    TrendResult,
    classify_trend,
)
from groundtruth.engine.assessment.types import (
    ATTRIBUTION_VERDICTS,
    LIMITATIONS,
    AssessmentInputs,
    AttributionResult,
    ClimateYear,
    DimensionResult,
    Limitation,
    SeriesPoint,
    SpreadPoint,
)

DEFAULT_ATTRIBUTION_METHOD = (
    "Counterfactual comparison against eligible reference areas (synthetic control and "
    "difference-in-differences, with placebo tests). It needs pre-treatment observations, "
    "a donor panel with vegetation series and a completed real-data run."
)

# -- helpers ----------------------------------------------------------------------------


def clean_series(points: Sequence[SeriesPoint]) -> list[SeriesPoint]:
    """Sort by year, reject duplicate years, drop non-finite values.

    Duplicate years raise ``ValueError``: the platform adapter must de-duplicate
    (one value per year per series) before calling the engine.
    """
    ordered = sorted(points, key=lambda p: p.year)
    for a, b in pairwise(ordered):
        if a.year == b.year:
            raise ValueError(f"duplicate year {a.year} in a series")
    return [p for p in ordered if math.isfinite(p.value)]


def clean_all(series: Mapping[str, Sequence[SeriesPoint]]) -> dict[str, list[SeriesPoint]]:
    out = {k: clean_series(v) for k, v in series.items()}
    return {k: v for k, v in sorted(out.items()) if v}


def eligible_donors(
    project: Sequence[SeriesPoint], donors: Mapping[str, Sequence[SeriesPoint]]
) -> dict[str, list[SeriesPoint]]:
    """Donors whose series overlaps the project's observed years enough to compare."""
    years = {p.year for p in project}
    out: dict[str, list[SeriesPoint]] = {}
    for donor_id in sorted(donors):
        pts = clean_series(donors[donor_id])
        if len({p.year for p in pts} & years) >= MIN_REFERENCE_OVERLAP_PERIODS:
            out[donor_id] = pts
    return out


def _refs(points: Sequence[SeriesPoint]) -> tuple[str, ...]:
    return tuple(r for p in points for r in p.evidence_refs)


def _f(v: float) -> str:
    return f"{v:.3f}"


def _d(v: float) -> str:
    return f"{v:+.3f}"


def _span(first: int | None, last: int | None) -> str:
    return f"{first} to {last}"


def _combine(statuses: Sequence[str]) -> str:
    """Overall status over indicators: unanimity among those evaluated, else No clear change."""
    evaluated = [s for s in statuses if s != "Insufficient evidence"]
    if not evaluated:
        return "Insufficient evidence"
    return evaluated[0] if len(set(evaluated)) == 1 else "No clear change"


def _trend_of(points: Sequence[SeriesPoint]) -> TrendResult:
    return classify_trend([p.year for p in points], [p.value for p in points])


def _trend_sentence(label: str, t: TrendResult) -> str:
    if t.n < MIN_TREND_PERIODS:
        change = (
            f"first-to-last change {_d(t.change)} over {_span(t.first_year, t.last_year)}"
            if t.change is not None
            else "a single period, no change can be computed"
        )
        return f"{label}: {change} ({t.n} periods; a trend test needs at least {MIN_TREND_PERIODS})"
    assert t.slope is not None and t.ci_low is not None and t.ci_high is not None
    return (
        f"{label}: {t.status}, Theil-Sen slope {_d(t.slope)} per year "
        f"(90% CI {_d(t.ci_low)} to {_d(t.ci_high)}), Mann-Kendall p={t.p_value:.3f}, "
        f"n={t.n}, first-to-last change {_d(t.change or 0.0)}"
    )


def _confidence_for(status: str, n: int) -> str:
    if status in {"Improving", "Deteriorating"}:
        return "High" if n >= 10 else "Moderate"
    if status == "Stable":
        return "Moderate"
    return "Low"


def observed_years(series: Mapping[str, Sequence[SeriesPoint]]) -> list[int]:
    return sorted({p.year for pts in series.values() for p in pts})


def aligned_climate(inputs: AssessmentInputs, years: Sequence[int]) -> list[ClimateYear]:
    """Climate rows for observed years that carry at least one real value."""
    by_year = {c.year: c for c in (inputs.climate or [])}
    keep = []
    for y in years:
        c = by_year.get(y)
        if c is not None and (
            c.spi12 is not None or c.rainfall_mm is not None or c.temperature_c is not None
        ):
            keep.append(c)
    return keep


# -- 1. vegetation trajectory -----------------------------------------------------------


def vegetation_trajectory(inputs: AssessmentInputs) -> DimensionResult:
    series = clean_all(inputs.series)
    title = "Vegetation trajectory"
    if not series:
        return DimensionResult(
            id="vegetation_trajectory",
            title=title,
            status="Insufficient evidence",
            finding="No real index observations are available, so no trajectory can be described.",
            known=(),
            suggested=(),
            cannot_establish=("Whether vegetation is improving, stable or deteriorating.",),
            limitation="missing_data",
            evidence_needed=(
                f"Annual index observations inside the verified boundary; "
                f"at least {MIN_TREND_PERIODS} for a trend test."
            ),
            confidence="Low",
            evidence_refs=(),
            facts={"n_periods": 0, "trends": {}, "missing_years": ()},
        )
    trends = {ind: _trend_of(pts) for ind, pts in series.items()}
    status = _combine([t.status for t in trends.values()])
    n_max = max(t.n for t in trends.values())

    known: list[str] = []
    for ind, pts in series.items():
        values = ", ".join(f"{_f(p.value)} ({p.year})" for p in pts)
        known.append(f"{ind} annual values: {values}")
        known.append(_trend_sentence(ind, trends[ind]))
    suggested: list[str] = []
    cannot = ["Why vegetation changed: observed change is not a causal effect."]
    if status == "Insufficient evidence":
        for ind, t in trends.items():
            if t.change is not None:
                direction = "upward" if t.change > 0 else "downward" if t.change < 0 else "flat"
                suggested.append(
                    f"{ind} first-to-last change is {direction} ({_d(t.change)}); with "
                    f"{t.n} periods this suggests but does not establish a trend."
                )
        cannot.insert(0, "Whether vegetation is improving, stable or deteriorating over time.")
        limitation: Limitation = "weak_statistical_power"
        needed = (
            f"At least {MIN_TREND_PERIODS} annual periods; "
            f"{max(MIN_TREND_PERIODS - n_max, 0)} more than the {n_max} observed."
        )
    elif status == "No clear change":
        limitation = "weak_statistical_power"
        needed = "More annual periods or less noisy observations to narrow the slope interval."
    else:
        limitation = "none"
        needed = "None beyond routine monitoring."

    parts = [_trend_sentence(ind, t) for ind, t in trends.items()]
    finding = f"Vegetation trajectory: {status}. " + "; ".join(parts) + "."
    all_years = observed_years(series)
    missing = tuple(y for y in range(all_years[0], all_years[-1] + 1) if y not in set(all_years))
    return DimensionResult(
        id="vegetation_trajectory",
        title=title,
        status=status,
        finding=finding,
        known=tuple(known),
        suggested=tuple(suggested),
        cannot_establish=tuple(cannot),
        limitation=limitation,
        evidence_needed=needed,
        confidence=_confidence_for(status, n_max),
        evidence_refs=tuple(r for pts in series.values() for r in _refs(pts)),
        facts={
            "n_periods": n_max,
            "trends": dict(trends),
            "missing_years": missing,
            "observed_years": tuple(all_years),
        },
    )


# -- 2. spatial performance -------------------------------------------------------------


def spatial_performance(inputs: AssessmentInputs) -> DimensionResult:
    title = "Spatial performance"
    spread = inputs.zonal_spread or {}
    known: list[str] = []
    refs: list[str] = []
    for ind in sorted(spread):
        spread_pts = sorted(spread[ind], key=lambda p: p.year)
        if not spread_pts:
            continue
        last: SpreadPoint = spread_pts[-1]
        known.append(
            f"{ind} within-AOI spread in {last.year}: p10 {_f(last.p10)}, p90 {_f(last.p90)}, "
            f"std {_f(last.std)} ({last.n_valid_pixels} valid pixels)"
        )
        refs.extend(last.evidence_refs)

    zone_series = inputs.zone_series or {}
    classified: dict[str, str] = {}
    unclassified: list[str] = []
    for ind in sorted(zone_series):
        for zone in sorted(zone_series[ind]):
            pts = clean_series(zone_series[ind][zone])
            if not pts:
                continue
            t = _trend_of(pts)
            key = f"{ind}/{zone}"
            refs.extend(_refs(pts))
            if t.status == "Insufficient evidence":
                unclassified.append(key)
            else:
                classified[key] = t.status

    facts: dict[str, Any] = {
        "deteriorating_zones": tuple(k for k, s in classified.items() if s == "Deteriorating"),
        "improving_zones": tuple(k for k, s in classified.items() if s == "Improving"),
        "unclassified_zones": tuple(unclassified),
    }
    cannot = ["Which sub-areas of the boundary are improving or deteriorating."]
    if not classified:
        missing_zone_data = not zone_series
        known.append(
            "Only AOI-level means are available; no per-zone series are persisted."
            if missing_zone_data
            else "Per-zone series exist but none has enough periods for a trend test."
        )
        return DimensionResult(
            id="spatial_performance",
            title=title,
            status="Insufficient evidence",
            finding=(
                "Spatial performance cannot be classified: "
                + (
                    "per-zone or per-pixel series are not available."
                    if missing_zone_data
                    else f"no zone has {MIN_TREND_PERIODS} annual periods."
                )
            ),
            known=tuple(known),
            suggested=(),
            cannot_establish=tuple(cannot),
            limitation="missing_data" if missing_zone_data else "weak_statistical_power",
            evidence_needed=(
                "Per-zone or per-pixel annual composites with full tile coverage, "
                f"at least {MIN_TREND_PERIODS} periods."
            ),
            confidence="Low",
            evidence_refs=tuple(refs),
            facts=facts,
        )

    statuses = set(classified.values())
    if statuses == {"Improving"}:
        status = "Improving"
    elif statuses == {"Deteriorating"}:
        status = "Deteriorating"
    elif statuses <= {"Stable", "No clear change"}:
        status = "Stable" if statuses == {"Stable"} else "No clear change"
    else:
        status = "Mixed spatial performance"
    counts = ", ".join(f"{s}: {list(classified.values()).count(s)}" for s in sorted(statuses))
    known.append(f"Classified zones by status: {counts}")
    if unclassified:
        known.append("Zones without enough periods: " + ", ".join(unclassified))
    return DimensionResult(
        id="spatial_performance",
        title=title,
        status=status,
        finding=f"Spatial performance: {status} across {len(classified)} classified zone series.",
        known=tuple(known),
        suggested=(),
        cannot_establish=("Why zones differ.",),
        limitation="weak_statistical_power" if unclassified else "none",
        evidence_needed=(
            "Annual composites for the unclassified zones." if unclassified else "None."
        ),
        confidence="Moderate",
        evidence_refs=tuple(refs),
        facts=facts,
    )


# -- 3. climate context -----------------------------------------------------------------


def _regress_out_spi(
    points: Sequence[SeriesPoint], spi_by_year: Mapping[int, float]
) -> tuple[list[int], list[float], list[float]] | None:
    pairs = [(p.year, p.value, spi_by_year[p.year]) for p in points if p.year in spi_by_year]
    if len(pairs) < CLIMATE_ADJUST_MIN_YEARS:
        return None
    years = [p[0] for p in pairs]
    y = np.array([p[1] for p in pairs])
    s = np.array([p[2] for p in pairs])
    var = float(np.var(s))
    if var <= 0.0:
        return None
    beta = float(np.mean((s - s.mean()) * (y - y.mean())) / var)
    # Rounding removes floating-point residue so that an exactly explained series is "tied"
    # rather than a random walk of 1e-17 values.
    adjusted = np.round(y - beta * (s - s.mean()), 12)
    return years, [float(v) for v in y], [float(v) for v in adjusted]


def climate_context(inputs: AssessmentInputs) -> DimensionResult:
    title = "Climate context"
    series = clean_all(inputs.series)
    years = observed_years(series)
    rows = aligned_climate(inputs, years)
    per_year: list[dict[str, Any]] = []
    drought: list[int] = []
    wet: list[int] = []
    known: list[str] = []
    refs: list[str] = []
    for c in rows:
        flag = None
        if c.spi12 is not None and c.spi12 <= DROUGHT_SPI:
            flag = "drought"
            drought.append(c.year)
        elif c.spi12 is not None and c.spi12 >= WET_SPI:
            flag = "wet"
            wet.append(c.year)
        per_year.append(
            {
                "year": c.year,
                "rainfall_mm": c.rainfall_mm,
                "spi12": c.spi12,
                "temperature_c": c.temperature_c,
                "flag": flag,
            }
        )
        bits = []
        if c.rainfall_mm is not None:
            bits.append(f"rainfall {c.rainfall_mm:.0f} mm")
        if c.spi12 is not None:
            bits.append(f"SPI-12 {c.spi12:+.2f}")
        if c.temperature_c is not None:
            bits.append(f"mean temperature {c.temperature_c:.1f} C")
        label = {"drought": " (drought year)", "wet": " (wet year)"}.get(flag or "", "")
        known.append(f"{c.year}: {', '.join(bits)}{label}")
        refs.extend(c.evidence_refs)
    if inputs.readiness.climate_missing_months:
        known.append(
            "Climate months missing from the bundle: "
            + ", ".join(inputs.readiness.climate_missing_months)
        )

    spi_by_year = {c.year: c.spi12 for c in rows if c.spi12 is not None}
    adjusted_trends: dict[str, TrendResult] = {}
    raw_trends: dict[str, TrendResult] = {}
    for ind, pts in series.items():
        res = _regress_out_spi(pts, spi_by_year)
        if res is None:
            continue
        yrs, raw, adj = res
        raw_trends[ind] = classify_trend(yrs, raw)
        adjusted_trends[ind] = classify_trend(yrs, adj)
    estimable = bool(adjusted_trends)
    n_overlap = len(spi_by_year)
    facts: dict[str, Any] = {
        "estimable": estimable,
        "per_year": tuple(per_year),
        "drought_years": tuple(drought),
        "wet_years": tuple(wet),
        "overlap_years": n_overlap,
    }
    base_cannot = ["Whether a vegetation change is explained by climate beyond SPI-12."]
    if not rows:
        return DimensionResult(
            id="climate_context",
            title=title,
            status="Insufficient evidence",
            finding="No climate values overlap the observed years, so no climate context is given.",
            known=tuple(known),
            suggested=(),
            cannot_establish=tuple(base_cannot),
            limitation="missing_data",
            evidence_needed=(
                "Annual climate series (rainfall, SPI-12, temperature) for the observed years."
            ),
            confidence="Low",
            evidence_refs=(),
            facts=facts,
        )
    flags = []
    if drought:
        flags.append(f"drought year(s) {', '.join(map(str, drought))}")
    if wet:
        flags.append(f"wet year(s) {', '.join(map(str, wet))}")
    flag_text = "; ".join(flags) if flags else "no drought or wet years flagged"
    if not estimable:
        reason = (
            f"A climate-adjusted interpretation is not estimable: it needs at least "
            f"{CLIMATE_ADJUST_MIN_YEARS} overlapping years of the index and SPI-12; "
            f"{n_overlap} available."
        )
        return DimensionResult(
            id="climate_context",
            title=title,
            status="Insufficient evidence",
            finding=(
                f"Climate context reported for {len(rows)} observed year(s) ({flag_text}); "
                f"climate adjustment is not estimable with {n_overlap} overlapping year(s)."
            ),
            known=tuple(known),
            suggested=(),
            cannot_establish=(reason, *base_cannot),
            limitation="weak_statistical_power",
            evidence_needed=(
                f"At least {CLIMATE_ADJUST_MIN_YEARS} overlapping annual observations "
                f"(currently {n_overlap})."
            ),
            confidence="Low",
            evidence_refs=tuple(refs),
            facts={**facts, "reason": reason},
        )

    status = _combine([t.status for t in adjusted_trends.values()])
    raw_status = _combine([t.status for t in raw_trends.values()])
    limitation: Limitation = "none" if status == raw_status else "climate_confounding"
    known.append(
        "Climate-adjusted trend (index with its linear SPI-12 relationship removed): "
        + "; ".join(_trend_sentence(ind, t) for ind, t in adjusted_trends.items())
    )
    return DimensionResult(
        id="climate_context",
        title=title,
        status=status,
        finding=(f"Climate-adjusted trajectory: {status} (unadjusted: {raw_status}); {flag_text}."),
        known=tuple(known),
        suggested=(),
        cannot_establish=tuple(base_cannot),
        limitation=limitation,
        evidence_needed=(
            "None beyond routine monitoring."
            if limitation == "none"
            else "Climate-matched reference areas to separate climate from management."
        ),
        confidence="Moderate",
        evidence_refs=tuple(refs),
        facts={**facts, "reason": None, "raw_status": raw_status},
    )


# -- 4. ecological risk -----------------------------------------------------------------


def ecological_risk(inputs: AssessmentInputs) -> DimensionResult:
    title = "Ecological risk"
    series = clean_all(inputs.series)
    years = observed_years(series)
    rows = aligned_climate(inputs, years)
    spi_rows = [c for c in rows if c.spi12 is not None]

    signals: list[str] = []
    refs: list[str] = []
    known: list[str] = []
    drought_years = tuple(c.year for c in spi_rows if (c.spi12 or 0.0) <= DROUGHT_SPI)
    for c in spi_rows:
        if c.spi12 is not None and c.spi12 <= DROUGHT_SPI:
            signals.append(
                f"drought-stress signal in {c.year} (SPI-12 {c.spi12:+.2f} <= {DROUGHT_SPI:+.1f})"
            )
            refs.extend(c.evidence_refs)

    decline: list[tuple[str, int]] = []
    decline_evaluable = False
    spread = inputs.zonal_spread or {}
    for ind, pts in series.items():
        if len(pts) < 2:
            continue
        latest = pts[-1]
        sp = {s.year: s for s in spread.get(ind, [])}.get(latest.year)
        if sp is None or sp.n_valid_pixels <= 0:
            known.append(
                f"{ind}: vegetation-decline check not evaluable (no within-AOI spread for "
                f"{latest.year})."
            )
            continue
        decline_evaluable = True
        se = sp.std / math.sqrt(sp.n_valid_pixels)
        earlier = [p.value for p in pts[:-1]]
        drop = pts[-2].value - latest.value
        if latest.value <= min(earlier) and drop > se:
            decline.append((ind, latest.year))
            signals.append(
                f"vegetation-decline signal for {ind} in {latest.year} (record minimum "
                f"{_f(latest.value)}, {_f(drop)} below the previous period; within-AOI "
                f"standard error {_f(se)})"
            )
            refs.extend(latest.evidence_refs)
            refs.extend(sp.evidence_refs)
        else:
            known.append(
                f"{ind}: no vegetation-decline signal in {latest.year} (latest {_f(latest.value)}, "
                f"change from previous {_d(-drop)}, standard error {_f(se)})."
            )
    if spi_rows and not drought_years:
        known.append("No monitored year has SPI-12 at or below the drought threshold.")
    if signals:
        known.insert(0, "Risk signals: " + "; ".join(signals))

    evaluable = bool(spi_rows) or decline_evaluable
    facts: dict[str, Any] = {
        "drought_years": drought_years,
        "decline_signals": tuple(decline),
        "signals": tuple(signals),
    }
    cannot = [
        "Whether any signal reflects real damage: signals require field verification.",
        "Disturbance such as fire: no burned-area source is available to the engine.",
    ]
    needed = (
        "Field verification of any signal, and a burned-area or fire-activity source "
        "to assess disturbance."
    )
    if signals:
        status = "Elevated ecological risk"
        finding = "Elevated ecological risk: " + "; ".join(signals) + f" ({RISK_SIGNAL_LABEL})."
    elif evaluable:
        status = "No clear change"
        finding = (
            "No drought-stress or vegetation-decline signal fired in the checks that could "
            "be evaluated."
        )
    else:
        status = "Insufficient evidence"
        finding = (
            "Neither climate nor within-AOI spread is available, "
            "so no risk signal can be evaluated."
        )
    return DimensionResult(
        id="ecological_risk",
        title=title,
        status=status,
        finding=finding,
        known=tuple(known),
        suggested=(),
        cannot_establish=tuple(cannot),
        limitation="missing_data",
        evidence_needed=needed,
        confidence="Low",
        evidence_refs=tuple(dict.fromkeys(refs)),
        facts=facts,
    )


# -- 5. restoration progress ------------------------------------------------------------


def restoration_progress(inputs: AssessmentInputs, trajectory: DimensionResult) -> DimensionResult:
    """Observed change against inter-period variability; no claim without dimension 1."""
    series = clean_all(inputs.series)
    known: list[str] = []
    for ind, pts in series.items():
        if len(pts) < 2:
            known.append(f"{ind}: one period only, no change can be computed.")
            continue
        change = pts[-1].value - pts[0].value
        diffs = np.diff([p.value for p in pts])
        if diffs.size >= 2:
            variability = f"{float(np.std(diffs, ddof=1)):.3f} (std of year-to-year differences)"
        else:
            variability = "not estimable (needs 3 periods)"
        known.append(
            f"{ind}: observed change {_d(change)} over {_span(pts[0].year, pts[-1].year)}; "
            f"inter-period variability {variability}."
        )
    status = trajectory.status
    if status == "Improving":
        finding = (
            "Restoration progress: Improving, supported by a statistically significant "
            "vegetation trajectory (dimension 1)."
        )
        cannot = ["Whether the progress is due to the intervention (see attribution)."]
    else:
        finding = (
            f"Restoration progress: no progress claim is made; the vegetation trajectory is "
            f"{status} (dimension 1). Observed change is reported against variability."
        )
        cannot = ["Any claim of restoration progress without statistical support from dimension 1."]
    return DimensionResult(
        id="restoration_progress",
        title="Restoration progress",
        status=status,
        finding=finding,
        known=tuple(known),
        suggested=(),
        cannot_establish=tuple(cannot),
        limitation=trajectory.limitation,
        evidence_needed=trajectory.evidence_needed,
        confidence=trajectory.confidence,
        evidence_refs=trajectory.evidence_refs,
        facts={},
    )


# -- 6. comparative performance ---------------------------------------------------------


def comparative_performance(inputs: AssessmentInputs) -> DimensionResult:
    title = "Comparative performance"
    series = clean_all(inputs.series)
    reference = inputs.reference_series or {}
    needed = (
        "Vegetation series from eligible reference areas for the same indicator and years "
        f"(at least {MIN_REFERENCE_DONORS} areas, {MIN_TREND_PERIODS} periods for a trend)."
    )
    cannot = ["Whether differences from reference areas are caused by the intervention."]
    shared = [ind for ind in series if reference.get(ind)]
    if not shared:
        return DimensionResult(
            id="comparative_performance",
            title=title,
            status="Insufficient evidence",
            finding=(
                "No reference-area vegetation series exist for the observed indicators, "
                "so the project cannot be compared with reference areas."
            ),
            known=(),
            suggested=(),
            cannot_establish=tuple(cannot),
            limitation="missing_data",
            evidence_needed=needed,
            confidence="Low",
            evidence_refs=(),
            facts={"donor_count": 0},
        )

    statuses: list[str] = []
    limitations: list[str] = []
    known: list[str] = []
    refs: list[str] = []
    donor_count = 0
    for ind in shared:
        proj = series[ind]
        donors = eligible_donors(proj, reference[ind])
        if len(donors) < MIN_REFERENCE_DONORS:
            statuses.append("Insufficient evidence")
            limitations.append("poor_reference_comparability")
            known.append(
                f"{ind}: {len(donors)} reference area(s) overlap the observed years; "
                f"{MIN_REFERENCE_DONORS} are required for a comparison."
            )
            continue
        common = sorted(
            {p.year for p in proj}.intersection(*({p.year for p in d} for d in donors.values()))
        )
        if len(common) < MIN_REFERENCE_OVERLAP_PERIODS:
            statuses.append("Insufficient evidence")
            limitations.append("poor_reference_comparability")
            known.append(f"{ind}: reference areas share fewer than 2 years with the project.")
            continue
        donor_count = max(donor_count, len(donors))
        pv = {p.year: p.value for p in proj}
        dv = {k: {p.year: p.value for p in v} for k, v in donors.items()}
        project_change = pv[common[-1]] - pv[common[0]]
        donor_changes = [d[common[-1]] - d[common[0]] for d in dv.values()]
        median_change = float(np.median(donor_changes))
        rank = 1 + sum(1 for c in donor_changes if c > project_change)
        known.append(
            f"{ind}: project change {_d(project_change)} vs median reference change "
            f"{_d(median_change)} over {_span(common[0], common[-1])} (difference "
            f"{_d(project_change - median_change)}); rank {rank} of {len(donors) + 1} "
            "(1 = largest change)."
        )
        refs.extend(_refs([p for p in proj if p.year in common]))
        for d in donors.values():
            refs.extend(_refs([p for p in d if p.year in common]))
        diff_series = [pv[y] - float(np.median([d[y] for d in dv.values()])) for y in common]
        t = classify_trend(common, diff_series)
        statuses.append(t.status)
        limitations.append(t.limitation)
        if t.n >= MIN_TREND_PERIODS:
            known.append(_trend_sentence(f"{ind} project minus median reference", t))

    status = _combine(statuses)
    if status == "Insufficient evidence":
        for choice in ("poor_reference_comparability", "weak_statistical_power", "missing_data"):
            if choice in limitations:
                limitation: Limitation = choice  # type: ignore[assignment]
                break
        else:
            limitation = "missing_data"
    else:
        limitation = "none" if status != "No clear change" else "weak_statistical_power"
    if status == "Insufficient evidence":
        finding = (
            "Comparative performance cannot be established: the reference-area evidence is "
            f"insufficient ({limitation})."
        )
    else:
        finding = (
            f"Comparative performance: {status} relative to reference areas "
            "(project minus median reference), a comparison and not an effect estimate."
        )
    return DimensionResult(
        id="comparative_performance",
        title=title,
        status=status,
        finding=finding,
        known=tuple(known),
        suggested=(),
        cannot_establish=tuple(cannot),
        limitation=limitation,
        evidence_needed=needed if status == "Insufficient evidence" else "None beyond monitoring.",
        confidence=_confidence_for(status, 0 if status == "Insufficient evidence" else 6),
        evidence_refs=tuple(dict.fromkeys(refs)),
        facts={"donor_count": donor_count},
    )


# -- 7. evidence quality ----------------------------------------------------------------


def evidence_quality(
    inputs: AssessmentInputs, level: int, trajectory: DimensionResult
) -> DimensionResult:
    series = clean_all(inputs.series)
    years = observed_years(series)
    n_max = max((len(p) for p in series.values()), default=0)
    refs = tuple(r for pts in series.values() for r in _refs(pts))

    low_cov = tuple(
        (y, inputs.coverage_pct[y])
        for y in years
        if y in inputs.coverage_pct and inputs.coverage_pct[y] < COVERAGE_COMPLETE
    )
    unrecorded = tuple(y for y in years if y not in inputs.coverage_pct)
    sensor_set = {s for y in years for s in inputs.sensors.get(y, [])}
    sensors_unrecorded = [y for y in years if not inputs.sensors.get(y)]
    r = inputs.readiness

    rules: list[tuple[str, bool, str]] = [
        (
            "periods",
            n_max >= MIN_TREND_PERIODS,
            f"{n_max} annual period(s) observed; {MIN_TREND_PERIODS} needed for a trend test",
        ),
        (
            "coverage",
            bool(years) and not low_cov and not unrecorded,
            (
                f"AOI coverage at or above {COVERAGE_COMPLETE:.0f}% in every observed year"
                if years and not low_cov and not unrecorded
                else "coverage below "
                f"{COVERAGE_COMPLETE:.0f}% in "
                + (", ".join(f"{y} ({c:.0f}%)" for y, c in low_cov) or "no recorded year")
                + (f"; not recorded for {', '.join(map(str, unrecorded))}" if unrecorded else "")
            ),
        ),
        (
            "sensor continuity",
            bool(years) and len(sensor_set) <= 1 and not sensors_unrecorded,
            f"sensors across observed years: {', '.join(sorted(sensor_set)) or 'none recorded'}",
        ),
        (
            "climate completeness",
            bool(inputs.climate) and not r.climate_missing_months,
            (
                "climate bundle complete"
                if inputs.climate and not r.climate_missing_months
                else "climate missing months: "
                + (", ".join(r.climate_missing_months) or "no climate series")
            ),
        ),
        (
            "provenance guard",
            r.provenance_ok and r.boundary_verified,
            "boundary verified and provenance checks passed"
            if r.provenance_ok and r.boundary_verified
            else "boundary unverified or a provenance check failed",
        ),
        ("reached level", level >= 3, f"assessment level {level} (comparative needs 3)"),
        (
            "real (not simulated) data",
            inputs.data_mode == "observed",
            f"data mode: {inputs.data_mode}",
        ),
    ]
    failed = [name for name, ok, _ in rules if not ok]
    must_pass = {"provenance guard", "real (not simulated) data"}
    if not failed:
        rating = "High"
    elif len(failed) <= 2 and not (set(failed) & must_pass):
        rating = "Moderate"
    else:
        rating = "Low"
    known = tuple(f"{'PASS' if ok else 'FAIL'} - {name}: {detail}" for name, ok, detail in rules)
    missing_years = trajectory.facts.get("missing_years", ())
    return DimensionResult(
        id="evidence_quality",
        title="Evidence quality",
        status=rating,
        finding=(
            f"Evidence quality is rated {rating}: {len(rules) - len(failed)} of {len(rules)} "
            "rules pass (periods, coverage, sensor continuity, climate completeness, "
            "provenance, reached level, real data)."
        ),
        known=known,
        suggested=(),
        cannot_establish=(
            "A numeric score: the rating is the count of rules passed, not a measure.",
        ),
        limitation="missing_data" if failed else "none",
        evidence_needed=(
            "Resolve the failed rules: " + ", ".join(failed) + "." if failed else "None."
        ),
        confidence=rating,
        evidence_refs=refs,
        facts={
            "rating": rating,
            "rules": tuple((name, ok) for name, ok, _ in rules),
            "failed_rules": tuple(failed),
            "low_coverage_years": low_cov,
            "unrecorded_coverage_years": unrecorded,
            "missing_years": tuple(missing_years),
            "observed_years": tuple(years),
        },
    )


# -- 8. intervention attribution ---------------------------------------------------------


def intervention_attribution(
    inputs: AssessmentInputs, level: int, quality: DimensionResult
) -> tuple[AttributionResult, DimensionResult]:
    r = inputs.readiness
    series = clean_all(inputs.series)
    method = r.causal_methodology or DEFAULT_ATTRIBUTION_METHOD
    verdict = "Inconclusive"
    limitation: Limitation = "missing_data"
    refs: tuple[str, ...] = tuple(r.causal_evidence_refs)
    if level >= 4 and r.causal_verdict in ATTRIBUTION_VERDICTS:
        verdict = str(r.causal_verdict)
        given = r.causal_limitation if r.causal_limitation in LIMITATIONS else None
        if verdict == "Inconclusive":
            limitation = given if given not in (None, "none") else "missing_data"  # type: ignore[assignment]
        else:
            limitation = given or "none"  # type: ignore[assignment]

    missing: list[str] = []
    if not r.pre_treatment_observed:
        missing.append(
            f"observations from before the {inputs.treatment_start_year} treatment start"
        )
    has_reference = any(
        len(eligible_donors(series[ind], donors)) >= MIN_REFERENCE_DONORS
        for ind, donors in (inputs.reference_series or {}).items()
        if ind in series
    )
    if not (r.donor_panel_available and has_reference):
        missing.append("donor (reference-area) vegetation series for the same indicator and years")
    if (r.donor_panel_available and has_reference and r.pre_treatment_observed) and not (
        r.attribution_ready
    ):
        missing.append("all causal-readiness criteria met")
    if not r.causal_run_completed:
        missing.append("a completed real-data causal run")

    if verdict == "Inconclusive" and level >= 4:
        finding = f"Attribution is Inconclusive ({limitation}) after a completed causal run."
        needed = "Resolve the stated limitation and rerun the causal analysis."
    elif verdict == "Inconclusive":
        finding = (
            "Attribution is Inconclusive (missing_data): the evidence needed for a causal "
            "assessment is not available. No attribution claim is made."
        )
        needed = "Needed: " + "; ".join(missing) + "." if missing else "Needed: a completed run."
    else:
        finding = f"Attribution is {verdict} by the completed real-data causal run ({method})."
        needed = "None beyond field verification for Level 5."
    result = AttributionResult(
        verdict=verdict,
        methodology=method,
        limitation=limitation,
        finding=finding,
        evidence_needed=needed,
        evidence_refs=refs,
    )
    dim = DimensionResult(
        id="intervention_attribution",
        title="Intervention attribution",
        status=verdict,
        finding=finding,
        known=(f"Methodology: {method}", f"Limitation: {limitation}"),
        suggested=(),
        cannot_establish=(
            ()
            if verdict != "Inconclusive"
            else ("Whether the intervention caused the observed change.",)
        ),
        limitation=limitation,
        evidence_needed=needed,
        confidence="Low" if verdict == "Inconclusive" else quality.confidence,
        evidence_refs=refs,
        facts={"missing": tuple(missing), "donor_panel_has_series": has_reference},
    )
    return result, dim
