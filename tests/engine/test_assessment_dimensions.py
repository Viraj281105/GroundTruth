"""The eight dimensions, the levels and the layered conclusions."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from assessment_builders import (
    build_inputs,
    full_coverage,
    make_climate,
    make_points,
    make_spread,
    quiet_inputs,
    readiness,
    reference_panel,
    sensors,
)

pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from groundtruth.engine.assessment import assess
from groundtruth.engine.assessment.types import (
    ATTRIBUTION_VERDICTS,
    EVIDENCE_RATINGS,
    LIMITATIONS,
    STATUSES,
    Assessment,
)


def dim(a: Assessment, dim_id: str):
    return next(d for d in a.dimensions if d.id == dim_id)


def _walk(obj: Any):
    """Yield every field name, mapping key and string value in a nested structure."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield f.name
            yield from _walk(getattr(obj, f.name))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk(v)
    elif isinstance(obj, list | tuple | set | frozenset):
        for v in obj:
            yield from _walk(v)
    elif isinstance(obj, str):
        yield obj


# --- dimension 1: trajectory --------------------------------------------------------


def test_trajectory_insufficient_below_min_periods_but_reports_change():
    a = assess(build_inputs())
    d = dim(a, "vegetation_trajectory")
    assert d.status == "Insufficient evidence"
    assert d.limitation == "weak_statistical_power"
    known = " ".join(d.known)
    assert "2021" in known and "2023" in known
    assert "-0.003" in known  # 0.301 - 0.304: first-to-last change is always reported
    assert d.evidence_refs  # cites the points it used


def test_trajectory_improving_only_when_significant():
    n = 8
    rising = build_inputs(
        series={"NDVI": make_points("NDVI", 2016, [0.30 + 0.01 * i for i in range(n)])},
        climate=make_climate(2016, [0.0] * n),
        coverage_pct=full_coverage(2016, n),
        sensors=sensors(2016, n),
    )
    assert dim(assess(rising), "vegetation_trajectory").status == "Improving"

    noisy = build_inputs(
        series={
            "NDVI": make_points("NDVI", 2016, [0.30, 0.34, 0.28, 0.33, 0.29, 0.35, 0.30, 0.31])
        },
        climate=make_climate(2016, [0.0] * n),
        coverage_pct=full_coverage(2016, n),
        sensors=sensors(2016, n),
    )
    assert dim(assess(noisy), "vegetation_trajectory").status in {"Stable", "No clear change"}


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.floats(min_value=-1, max_value=1, allow_nan=False), min_size=0, max_size=5))
def test_no_improving_status_without_statistical_rule(values):
    inputs = build_inputs(
        series={"NDVI": make_points("NDVI", 2018, values)} if values else {},
        climate=None,
        coverage_pct={},
        sensors={},
    )
    a = assess(inputs)
    for d in a.dimensions:
        if d.id in {"vegetation_trajectory", "restoration_progress"}:
            assert d.status not in {"Improving", "Deteriorating"}


# --- dimension 2: spatial -----------------------------------------------------------


def test_spatial_insufficient_without_zone_series():
    d = dim(assess(build_inputs()), "spatial_performance")
    assert d.status == "Insufficient evidence"
    assert d.limitation == "missing_data"


def test_spatial_reports_within_aoi_spread_as_known_but_stays_insufficient():
    inputs = build_inputs(zonal_spread={"NDVI": make_spread(2021, 3)})
    d = dim(assess(inputs), "spatial_performance")
    assert d.status == "Insufficient evidence"
    assert d.limitation == "missing_data"
    assert "p10" in " ".join(d.known)


def test_spatial_mixed_when_zones_diverge():
    n = 8
    zones = {
        "NDVI": {
            "zone-a": make_points("NDVI:a", 2016, [0.30 + 0.01 * i for i in range(n)]),
            "zone-b": make_points("NDVI:b", 2016, [0.50 - 0.01 * i for i in range(n)]),
        }
    }
    d = dim(assess(build_inputs(zone_series=zones)), "spatial_performance")
    assert d.status == "Mixed spatial performance"
    assert d.facts["deteriorating_zones"] == ("NDVI/zone-b",)


# --- dimension 3: climate -----------------------------------------------------------


def test_climate_adjustment_not_estimable_below_8_years():
    a = assess(build_inputs())
    d = dim(a, "climate_context")
    assert d.facts["estimable"] is False
    assert "8" in " ".join(d.cannot_establish)
    assert a.climate_adjusted_interpretation.estimable is False
    assert a.climate_adjusted_interpretation.reason


def test_drought_years_flagged():
    a = assess(build_inputs(climate=make_climate(2021, [-1.0, 0.0, 1.0])))
    d = dim(a, "climate_context")
    assert d.facts["drought_years"] == (2021,)
    assert d.facts["wet_years"] == (2023,)
    assert any("2021" in k and "drought" in k.lower() for k in d.known)
    # SPI -0.99 is not a drought year
    a2 = assess(build_inputs(climate=make_climate(2021, [-0.99, 0.0, 0.5])))
    assert dim(a2, "climate_context").facts["drought_years"] == ()


def test_climate_adjustment_estimable_with_8_overlapping_years():
    n = 8
    spis = [0.5, -0.5, 1.0, -1.0, 0.2, -0.2, 0.8, -0.8]
    # the index tracks SPI exactly, so the adjusted series is flat
    values = [0.40 + 0.03 * s for s in spis]
    inputs = build_inputs(
        series={"NDVI": make_points("NDVI", 2016, values)},
        climate=make_climate(2016, spis),
        coverage_pct=full_coverage(2016, n),
        sensors=sensors(2016, n),
    )
    d = dim(assess(inputs), "climate_context")
    assert d.facts["estimable"] is True
    assert d.status in {"Stable", "No clear change"}


# --- dimension 4: ecological risk ---------------------------------------------------


def test_risk_signal_labelled_signal_not_damage():
    d = dim(assess(build_inputs()), "ecological_risk")
    assert d.status == "Elevated ecological risk"
    assert "signal" in d.finding and "field verification" in d.finding
    assert "signal — requires field verification" in d.finding
    assert d.facts["drought_years"] == (2021,)
    assert d.confidence == "Low"


def test_vegetation_decline_signal_needs_record_minimum_and_a_drop_beyond_standard_error():
    values = [0.40, 0.41, 0.40, 0.39, 0.30]
    inputs = build_inputs(
        series={"NDVI": make_points("NDVI", 2019, values, n_valid_pixels=100)},
        zonal_spread={"NDVI": make_spread(2019, 5, std=0.05, n_valid_pixels=100)},  # SE 0.005
        climate=make_climate(2019, [0.0, 0.0, 0.0, 0.0, -1.4]),
    )
    d = dim(assess(inputs), "ecological_risk")
    assert d.facts["decline_signals"] == (("NDVI", 2023),)
    assert d.facts["drought_years"] == (2023,)

    # the same drop inside the noise (SE 0.2) is not a signal
    noisy = dataclasses.replace(
        inputs, zonal_spread={"NDVI": make_spread(2019, 5, std=2.0, n_valid_pixels=100)}
    )
    assert dim(assess(noisy), "ecological_risk").facts["decline_signals"] == ()


def test_disturbance_is_never_claimed_without_a_fire_source():
    d = dim(assess(build_inputs()), "ecological_risk")
    assert any("burned-area" in c or "fire" in c for c in d.cannot_establish)


# --- dimension 5: restoration progress ---------------------------------------------


def test_progress_makes_no_claim_without_trajectory_support():
    d = dim(assess(build_inputs()), "restoration_progress")
    assert d.status == "Insufficient evidence"
    assert "variab" in " ".join(d.known)
    assert any("progress" in c.lower() for c in d.cannot_establish)


# --- dimensions 6 and 8 --------------------------------------------------------------


def test_comparative_insufficient_without_reference():
    d = dim(assess(build_inputs()), "comparative_performance")
    assert d.status == "Insufficient evidence"
    assert d.limitation == "missing_data"


def test_comparative_with_too_few_donors_is_poor_reference_comparability():
    inputs = build_inputs(reference_series=reference_panel("NDVI", 2021, 3, n_donors=2))
    d = dim(assess(inputs), "comparative_performance")
    assert d.status == "Insufficient evidence"
    assert d.limitation == "poor_reference_comparability"


def test_comparative_reports_difference_and_rank_but_few_periods_stay_insufficient():
    inputs = build_inputs(reference_series=reference_panel("NDVI", 2021, 3, n_donors=4))
    d = dim(assess(inputs), "comparative_performance")
    assert d.status == "Insufficient evidence"
    assert d.limitation == "weak_statistical_power"
    assert "rank" in " ".join(d.known)


def test_attribution_inconclusive_types_missing_data():
    a = assess(build_inputs())
    assert a.attribution.verdict == "Inconclusive"
    assert a.attribution.limitation == "missing_data"
    assert a.attribution.methodology
    d8 = dim(a, "intervention_attribution")
    assert d8.status == "Inconclusive" and d8.limitation == "missing_data"
    assert "2012" in d8.evidence_needed  # names the missing pre-treatment period


def _l3_inputs(**readiness_over: Any):
    n = 8
    return build_inputs(
        series={"NDVI": make_points("NDVI", 2016, [0.30 + 0.01 * i for i in range(n)])},
        climate=make_climate(2016, [0.0] * n),
        reference_series=reference_panel("NDVI", 2016, n),
        readiness=readiness(
            attribution_ready=True,
            pre_treatment_observed=True,
            donor_panel_available=True,
            **readiness_over,
        ),
        coverage_pct=full_coverage(2016, n),
        sensors=sensors(2016, n),
    )


def test_attribution_supported_requires_level4():
    # level 3: a "Supported" causal-run summary is not honoured without a completed run ...
    a = assess(_l3_inputs(causal_run_completed=False, causal_verdict="Supported"))
    assert a.level == 3
    assert a.attribution.verdict == "Inconclusive"

    # ... nor when the readiness criteria are not met
    unready = dataclasses.replace(
        _l3_inputs(),
        readiness=readiness(
            attribution_ready=False,
            donor_panel_available=True,
            causal_run_completed=True,
            causal_verdict="Supported",
        ),
    )
    a2 = assess(unready)
    assert a2.level == 3
    assert a2.attribution.verdict == "Inconclusive"

    a4 = assess(_l3_inputs(causal_run_completed=True, causal_verdict="Supported"))
    assert a4.level == 4
    assert a4.attribution.verdict == "Supported"
    assert a4.attribution.verdict in ATTRIBUTION_VERDICTS


def test_attribution_carries_the_run_limitation_when_inconclusive():
    a = assess(
        _l3_inputs(
            causal_run_completed=True,
            causal_verdict="Inconclusive",
            causal_limitation="failed_model_assumptions",
        )
    )
    assert a.level == 4
    assert a.attribution.verdict == "Inconclusive"
    assert a.attribution.limitation == "failed_model_assumptions"


# --- dimension 7 and levels -----------------------------------------------------------


def test_evidence_quality_lists_each_rule_outcome():
    d = dim(assess(build_inputs()), "evidence_quality")
    assert d.status == d.confidence == "Low"
    text = " ".join(d.known)
    for rule in ("periods", "coverage", "sensor", "climate", "provenance", "level"):
        assert rule in text.lower()


def test_quiet_inputs_have_high_or_moderate_evidence_quality():
    d = dim(assess(quiet_inputs()), "evidence_quality")
    assert d.status in {"Moderate", "High"}


def test_levels():
    assert assess(build_inputs(series={}, climate=None)).level == 0
    assert assess(build_inputs(readiness=readiness(boundary_verified=False))).level == 0
    one_period = build_inputs(series={"NDVI": make_points("NDVI", 2021, [0.3])})
    assert assess(one_period).level == 0

    l1 = assess(build_inputs(climate=None))
    assert l1.level == 1 and l1.level_name == "Basic monitoring"

    l2 = assess(build_inputs())
    assert l2.level == 2 and l2.level_name == "Contextual intelligence"

    # reference series present but for another indicator -> never L3
    no_overlap = build_inputs(reference_series={"EVI": reference_panel("EVI", 2021, 3)["EVI"]})
    assert assess(no_overlap).level == 2

    # full readiness and a completed run still cannot lift a project without reference series
    ready = readiness(
        attribution_ready=True,
        pre_treatment_observed=True,
        donor_panel_available=True,
        causal_run_completed=True,
        causal_verdict="Supported",
    )
    assert assess(build_inputs(readiness=ready)).level == 2

    l3 = assess(build_inputs(reference_series=reference_panel("NDVI", 2021, 3)))
    assert l3.level == 3 and l3.level_name == "Comparative intelligence"

    l4 = assess(build_inputs(reference_series=reference_panel("NDVI", 2021, 3), readiness=ready))
    assert l4.level == 4 and l4.level_name == "Attribution assessment"

    l5 = assess(
        build_inputs(
            reference_series=reference_panel("NDVI", 2021, 3), readiness=ready, field_evidence=True
        )
    )
    assert l5.level == 5 and l5.level_name == "Verified impact"

    # field evidence alone does not skip levels
    assert assess(build_inputs(field_evidence=True)).level == 2


def test_not_assessable_still_returns_every_dimension():
    a = assess(build_inputs(series={}, climate=None))
    assert a.level == 0
    assert len(a.dimensions) == 8
    allowed = STATUSES | EVIDENCE_RATINGS | ATTRIBUTION_VERDICTS
    assert all(d.status in allowed for d in a.dimensions)


def test_dimension_vocabularies_are_exact():
    a = assess(build_inputs())
    ids = [d.id for d in a.dimensions]
    assert ids == [
        "vegetation_trajectory",
        "spatial_performance",
        "climate_context",
        "ecological_risk",
        "restoration_progress",
        "comparative_performance",
        "evidence_quality",
        "intervention_attribution",
    ]
    assert {
        "Improving",
        "Deteriorating",
        "Stable",
        "Mixed spatial performance",
        "Elevated ecological risk",
        "No clear change",
        "Insufficient evidence",
    } == STATUSES
    assert {
        "missing_data",
        "weak_statistical_power",
        "poor_reference_comparability",
        "climate_confounding",
        "failed_model_assumptions",
        "none",
    } == LIMITATIONS
    for d in a.dimensions:
        assert d.limitation in LIMITATIONS
        assert d.confidence in {"High", "Moderate", "Low"}
        assert d.finding


# --- safeguards -----------------------------------------------------------------------


def _ready_l4(**over: Any):
    ready = readiness(
        attribution_ready=True,
        pre_treatment_observed=True,
        donor_panel_available=True,
        causal_run_completed=True,
        causal_verdict="Supported",
    )
    return build_inputs(reference_series=reference_panel("NDVI", 2021, 3), readiness=ready, **over)


def test_no_carbon_fields():
    sets = [
        build_inputs(),
        quiet_inputs(),
        _ready_l4(),
        _ready_l4(field_evidence=True),
        _ready_l4(data_mode="simulated"),
        build_inputs(data_mode="simulated"),
    ]
    for inputs in sets:
        a = assess(inputs)
        for text in _walk(a):
            low = text.lower()
            assert "carbon" not in low and "biomass" not in low and "tco2" not in low, text


def test_simulated_level_is_labelled_not_capped():
    sim = assess(_ready_l4(data_mode="simulated"))
    obs = assess(_ready_l4(data_mode="observed"))
    assert sim.level == obs.level == 4
    assert sim.level_name == "Attribution assessment (simulated)"
    assert obs.level_name == "Attribution assessment"
    assert sim.data_mode == "simulated" and obs.data_mode == "observed"
    for d in sim.dimensions:
        assert d.finding.startswith("[SIMULATED DATA]")
    for c in (
        sim.observed_outcome,
        sim.ecological_assessment,
        sim.climate_adjusted_interpretation,
        sim.comparative_assessment,
    ):
        assert c.summary.startswith("[SIMULATED DATA]")
    assert sim.attribution.finding.startswith("[SIMULATED DATA]")
    assert dim(sim, "evidence_quality").status == "Low"
    assert sim.evidence_confidence == "Low"
    # the label is the only difference in the numeric level
    assert all("SIMULATED" not in d.finding for d in obs.dimensions)


def test_simulated_inputs_marked():
    a = assess(build_inputs(data_mode="simulated"))
    assert a.data_mode == "simulated"
    assert a.simulated_banner and "SIMULATED" in a.simulated_banner
    for d in a.dimensions:
        assert "SIMULATED DATA" in d.finding
    assert "SIMULATED DATA" in a.observed_outcome.summary
    observed = assess(build_inputs())
    assert observed.data_mode == "observed" and observed.simulated_banner is None
    assert all("SIMULATED" not in d.finding for d in observed.dimensions)
    # simulated data is never rated better than Low evidence
    assert dim(a, "evidence_quality").status == "Low"


def test_assessment_is_deterministic():
    assert assess(build_inputs()) == assess(build_inputs())


def test_duplicate_years_are_a_programming_error():
    pts = make_points("NDVI", 2021, [0.3, 0.31]) + make_points("NDVI", 2021, [0.32])
    with pytest.raises(ValueError, match="duplicate"):
        assess(build_inputs(series={"NDVI": pts}))


# --- Kariba-shaped acceptance (inline illustrative fixture, not project results) ----


def test_kariba_shaped_assessment_is_level_2():
    inputs = build_inputs(
        series={"NDVI": make_points("NDVI", 2021, [0.305, 0.297, 0.301])},
        zonal_spread=None,
        reference_series=None,
        treatment_start_year=2012,
    )
    a = assess(inputs)

    assert a.level == 2 and a.level_name == "Contextual intelligence"

    d1 = dim(a, "vegetation_trajectory")
    assert (d1.status, d1.limitation) == ("Insufficient evidence", "weak_statistical_power")
    assert "-0.004" in " ".join(d1.known)  # first-to-last change, 2021 -> 2023

    d2 = dim(a, "spatial_performance")
    assert (d2.status, d2.limitation) == ("Insufficient evidence", "missing_data")

    d3 = dim(a, "climate_context")
    assert len(d3.facts["per_year"]) == 3
    assert d3.facts["drought_years"] == (2021,)

    d6 = dim(a, "comparative_performance")
    assert (d6.status, d6.limitation) == ("Insufficient evidence", "missing_data")

    assert (a.attribution.verdict, a.attribution.limitation) == ("Inconclusive", "missing_data")

    ids = {r.id for r in a.recommendations}
    assert {"acquire_more_observations", "acquire_reference_series"} <= ids
    for r in a.recommendations:
        assert r.rationale.strip()
        assert r.evidence_refs
        assert r.text.strip()
