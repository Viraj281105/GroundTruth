"""Recommendation rules fire only on real findings, with rationale and evidence."""

from __future__ import annotations

import dataclasses

import pytest
from assessment_builders import (
    build_inputs,
    full_coverage,
    make_climate,
    make_points,
    make_spread,
    quiet_inputs,
    readiness,
    sensors,
)

from groundtruth.engine.assessment import assess
from groundtruth.engine.assessment.recommendations import (
    RULES,
    recommendations_for_persona,
)

RULE_IDS = {
    "field_verification_before_claims",
    "investigate_drought_explanation",
    "acquire_more_observations",
    "acquire_reference_series",
    "inspect_deteriorating_zones",
    "review_boundary_or_period",
    "increase_oversight",
}


def ids(a):
    return {r.id for r in a.recommendations}


def test_rule_table_has_exactly_the_specified_rules():
    assert {r.id for r in RULES} == RULE_IDS
    for rule in RULES:
        assert rule.text_template and isinstance(rule.priority, int) and rule.personas


def test_recommendations_fire_only_on_triggers():
    a = assess(quiet_inputs())
    assert a.recommendations == ()  # no filler


def test_field_verification_fires_on_improving_without_level5():
    inputs = dataclasses.replace(
        quiet_inputs(),
        series={"NDVI": make_points("NDVI", 2012, [0.30 + 0.01 * i for i in range(10)])},
    )
    a = assess(inputs)
    assert "field_verification_before_claims" in ids(a)
    rec = next(r for r in a.recommendations if r.id == "field_verification_before_claims")
    assert rec.evidence_refs and rec.rationale
    # with independent field observations at level 5 it no longer fires
    a5 = assess(dataclasses.replace(inputs, field_evidence=True))
    assert a5.level == 5
    assert "field_verification_before_claims" not in ids(a5)


def test_drought_explanation_needs_decline_signal_coinciding_with_drought():
    values = [0.40, 0.41, 0.40, 0.39, 0.30]
    base = build_inputs(
        series={"NDVI": make_points("NDVI", 2019, values, n_valid_pixels=100)},
        zonal_spread={"NDVI": make_spread(2019, 5, std=0.05, n_valid_pixels=100)},
        climate=make_climate(2019, [0.0, 0.0, 0.0, 0.0, -1.4]),
        coverage_pct=full_coverage(2019, 5),
        sensors=sensors(2019, 5),
    )
    a = assess(base)
    assert "investigate_drought_explanation" in ids(a)
    rec = next(r for r in a.recommendations if r.id == "investigate_drought_explanation")
    assert "2023" in rec.rationale and rec.evidence_refs

    # drought year without a decline signal: no recommendation
    calm = dataclasses.replace(base, series={"NDVI": make_points("NDVI", 2019, [0.4] * 5)})
    assert "investigate_drought_explanation" not in ids(assess(calm))


def test_acquire_more_observations_names_the_years():
    a = assess(build_inputs())
    rec = next(r for r in a.recommendations if r.id == "acquire_more_observations")
    assert "2021" in rec.text and "2023" in rec.text
    assert "6" in rec.text
    assert "62" in rec.text  # names the low-coverage year(s) with their coverage
    assert rec.evidence_refs


def test_acquire_more_observations_fires_on_coverage_alone():
    inputs = dataclasses.replace(quiet_inputs(), coverage_pct=full_coverage(2012, 10, 80.0))
    a = assess(inputs)
    assert "acquire_more_observations" in ids(a)


def test_acquire_reference_series_fires_without_donor_series():
    assert "acquire_reference_series" in ids(assess(build_inputs()))
    assert "acquire_reference_series" not in ids(assess(quiet_inputs()))


def test_inspect_deteriorating_zones_silent_without_zone_data_fires_with_it():
    assert "inspect_deteriorating_zones" not in ids(assess(build_inputs()))
    n = 8
    zones = {
        "NDVI": {
            "zone-a": make_points("NDVI:a", 2016, [0.30 + 0.01 * i for i in range(n)]),
            "zone-b": make_points("NDVI:b", 2016, [0.50 - 0.01 * i for i in range(n)]),
        }
    }
    a = assess(build_inputs(zone_series=zones))
    rec = next(r for r in a.recommendations if r.id == "inspect_deteriorating_zones")
    assert "zone-b" in rec.text and rec.evidence_refs


def test_review_boundary_or_period_triggers():
    # observed period starts after the treatment start (Kariba-shaped)
    a = assess(build_inputs())
    rec = next(r for r in a.recommendations if r.id == "review_boundary_or_period")
    assert "2012" in rec.rationale

    # coverage below 50 % in an observed year
    inputs = dataclasses.replace(
        quiet_inputs(), coverage_pct={**full_coverage(2012, 10), 2015: 40.0}
    )
    b = assess(inputs)
    rec_b = next(r for r in b.recommendations if r.id == "review_boundary_or_period")
    assert "2015" in rec_b.rationale

    assert "review_boundary_or_period" not in ids(assess(quiet_inputs()))


def test_increase_oversight_needs_low_quality_and_a_claim():
    assert "increase_oversight" not in ids(assess(build_inputs()))
    with_claim = assess(build_inputs(claim_present=True))
    assert "increase_oversight" in ids(with_claim)
    rec = next(r for r in with_claim.recommendations if r.id == "increase_oversight")
    assert set(rec.personas) == {"funder", "government"}
    # a claim alone, with good evidence, does not trigger it
    assert "increase_oversight" not in ids(
        assess(dataclasses.replace(quiet_inputs(), claim_present=True))
    )


def test_every_recommendation_has_rationale_refs_and_valid_priority():
    for inputs in (
        build_inputs(claim_present=True),
        build_inputs(readiness=readiness(boundary_verified=True), climate=None),
    ):
        for r in assess(inputs).recommendations:
            assert r.id in RULE_IDS
            assert r.rationale.strip() and r.evidence_refs and r.text.strip()
            assert r.priority >= 1


def test_recommendations_sorted_by_priority_then_id():
    recs = assess(build_inputs(claim_present=True)).recommendations
    keys = [(r.priority, r.id) for r in recs]
    assert keys == sorted(keys)


def test_persona_view_filters_and_keeps_the_same_wording():
    a = assess(build_inputs(claim_present=True))
    funder = recommendations_for_persona(a.recommendations, "funder")
    ngo = recommendations_for_persona(a.recommendations, "ngo")
    assert "increase_oversight" in {r.id for r in funder}
    assert "increase_oversight" not in {r.id for r in ngo}
    by_id = {r.id: r for r in a.recommendations}
    for r in funder + ngo:
        assert r == by_id[r.id]
    with pytest.raises(ValueError):
        recommendations_for_persona(a.recommendations, "robot")
