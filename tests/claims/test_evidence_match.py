"""Matching a claim against evidence: outcomes, tolerances, and what can never be established."""

from __future__ import annotations

import pytest

from groundtruth.claims.evidence_match import (
    CONTRADICTED,
    PARTIALLY_SUPPORTED,
    SUPPORTED,
    UNVERIFIED,
    EvidenceContext,
    ObservationSeries,
    match_claim,
)


def ctx(
    area: float | None = 1000.0, ndvi: dict[int, float] | None = None, cov=None
) -> EvidenceContext:
    series = {"ndvi": ObservationSeries("ndvi", ndvi, cov or {})} if ndvi is not None else {}
    return EvidenceContext(boundary_area_ha=area, boundary_ref="sha256:abc", series=series)


# --- area -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("claimed", "unit", "expected"),
    [
        (1000, "ha", SUPPORTED),
        (1049, "hectares", SUPPORTED),  # within 5%
        (951, "ha", SUPPORTED),
        (1051, "ha", CONTRADICTED),  # larger than the boundary by more than 5%
        (500, "ha", PARTIALLY_SUPPORTED),  # fits inside, restored extent not shown
        (10, "km2", SUPPORTED),  # 10 km2 = 1000 ha
        (2471.05, "acres", SUPPORTED),  # = 1000 ha
    ],
)
def test_area_against_the_boundary(claimed: float, unit: str, expected: str) -> None:
    out = match_claim("area_hectares", claimed, unit, None, ctx())
    assert out.status == expected, out.headline
    assert out.observed_unit == "ha" and out.observed_value == 1000.0
    assert any("drawn by the project" in lim for lim in out.limitations)  # boundary != restored


def test_a_matching_area_does_not_claim_the_land_was_restored() -> None:
    out = match_claim("area_hectares", 1000, "ha", None, ctx())
    assert "restored" not in out.headline.lower() or "not shown" in out.headline.lower()
    assert any("restored" in m.lower() for m in out.missing_evidence)


def test_area_without_boundary_unit_or_number_is_unverified_with_a_reason() -> None:
    assert match_claim("area_hectares", 100, "ha", None, ctx(area=None)).status == UNVERIFIED
    assert match_claim("area_hectares", 100, "furlongs", None, ctx()).status == UNVERIFIED
    assert match_claim("area_hectares", None, "ha", None, ctx()).status == UNVERIFIED
    assert match_claim("area_hectares", -5, "ha", None, ctx()).status == UNVERIFIED


# --- vegetation index change --------------------------------------------------------------------------


def test_change_that_matches_is_supported_but_never_causal() -> None:
    out = match_claim(
        "vegetation_index_change",
        0.15,
        "ndvi_units",
        "since 2021",
        ctx(ndvi={2021: 0.40, 2023: 0.54}),
    )
    assert out.status == SUPPORTED
    assert out.observed_value == pytest.approx(0.14)
    text = " ".join(out.limitations).lower()
    assert "does not measure tree survival" in text and "caused it" in text
    assert any("caused by the project" in m for m in out.missing_evidence)


def test_opposite_direction_is_contradicted() -> None:
    out = match_claim(
        "vegetation_index_change",
        0.15,
        "ndvi_units",
        "since 2021",
        ctx(ndvi={2021: 0.50, 2023: 0.45}),
    )
    assert out.status == CONTRADICTED and out.contradicting


def test_less_than_half_the_claimed_change_is_contradicted() -> None:
    out = match_claim(
        "vegetation_index_change",
        0.30,
        "ndvi_units",
        "since 2021",
        ctx(ndvi={2021: 0.40, 2023: 0.50}),
    )
    assert out.status == CONTRADICTED


def test_same_direction_but_different_size_is_partial() -> None:
    out = match_claim(
        "vegetation_index_change",
        0.20,
        "ndvi_units",
        "since 2021",
        ctx(ndvi={2021: 0.40, 2023: 0.54}),
    )
    assert out.status == PARTIALLY_SUPPORTED  # observed 0.14 is 70% of 0.20, outside tolerance
    larger = match_claim(
        "vegetation_index_change",
        0.05,
        "ndvi_units",
        "since 2021",
        ctx(ndvi={2021: 0.40, 2023: 0.52}),
    )
    assert larger.status == PARTIALLY_SUPPORTED  # observed change is bigger than claimed


def test_incomplete_area_coverage_downgrades_a_match() -> None:
    out = match_claim(
        "vegetation_index_change",
        0.14,
        "ndvi_units",
        "since 2021",
        ctx(ndvi={2021: 0.40, 2023: 0.54}, cov={2021: 99.0, 2023: 60.0}),
    )
    assert out.status == PARTIALLY_SUPPORTED
    assert any("below 95%" in lim and "2023" in lim for lim in out.limitations)


def test_period_selection() -> None:
    series = ctx(ndvi={2019: 0.30, 2021: 0.40, 2023: 0.60})
    both = match_claim("vegetation_index_change", 0.30, "ndvi_units", "2019-2023", series)
    assert both.observed_value == pytest.approx(0.30) and both.status == SUPPORTED
    nothing_stated = match_claim("vegetation_index_change", 0.30, "ndvi_units", None, series)
    assert nothing_stated.observed_value == pytest.approx(0.30)
    assert any("earliest" in r for r in nothing_stated.reasons)


def test_not_enough_observations_is_insufficient_not_guessed() -> None:
    none = match_claim("vegetation_index_change", 0.1, "ndvi_units", "since 2021", ctx())
    one = match_claim(
        "vegetation_index_change", 0.1, "ndvi_units", "since 2021", ctx(ndvi={2023: 0.5})
    )
    for out in (none, one):
        assert out.status == UNVERIFIED and out.observed_value is None
        assert any("at least two years" in r for r in out.reasons)
        assert any("Earth observation tab" in m for m in out.missing_evidence)


def test_years_the_claim_names_but_the_data_lacks_are_reported() -> None:
    out = match_claim(
        "vegetation_index_change", 0.1, "ndvi_units", "2018-2023", ctx(ndvi={2021: 0.4, 2023: 0.5})
    )
    assert out.status == UNVERIFIED
    assert "2018" in " ".join(out.missing_evidence) and out.available_evidence


def test_other_indicators_need_their_own_series() -> None:
    out = match_claim(
        "vegetation_index_change", 0.1, "evi_units", "since 2021", ctx(ndvi={2021: 0.4, 2023: 0.5})
    )
    assert out.status == UNVERIFIED and "EVI" in out.headline


# --- claims no evidence here can establish -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "phrase"),
    [
        ("survival_rate", "field survey"),
        ("trees_planted", "Planting records"),
        ("carbon_tco2e", "NDVI is not carbon"),
        ("index_to_carbon_conflation", "cannot be converted"),
        ("biodiversity_recovery", "species"),
        ("ecosystem_recovery", "greenness series covers none"),
        ("causal_attribution", "counterfactual"),
        ("unsupported_conclusion", "Absolute wording"),
    ],
)
def test_claims_satellite_greenness_cannot_establish_are_never_supported(
    kind: str, phrase: str
) -> None:
    rich = ctx(ndvi={2019: 0.2, 2023: 0.9})  # even strong greening changes nothing here
    out = match_claim(kind, 85.0, "percent", "after 3 years", rich)
    assert out.status == UNVERIFIED
    blob = " ".join([out.headline, *out.reasons, *out.missing_evidence, *out.required_evidence])
    assert phrase.lower() in blob.lower()
    assert out.missing_evidence and out.required_evidence


def test_unknown_kind_is_unverified() -> None:
    assert match_claim("made_up", 1.0, None, None, ctx()).status == UNVERIFIED


def test_outcomes_never_say_verified_or_accuse_anyone() -> None:
    cases = [
        match_claim("area_hectares", 5000, "ha", None, ctx()),
        match_claim(
            "vegetation_index_change",
            0.9,
            "ndvi_units",
            "since 2021",
            ctx(ndvi={2021: 0.4, 2023: 0.41}),
        ),
        match_claim("carbon_tco2e", 40000, "tCO2e", None, ctx()),
    ]
    for out in cases:
        text = " ".join([out.headline, *out.reasons, *out.contradicting, *out.limitations]).lower()
        assert "verified" not in text.replace("unverified", "")
        assert not any(w in text for w in ("fraud", "scam", "lied", "lying", "fake"))


def test_a_noisy_record_discloses_that_two_years_can_mislead() -> None:
    """Real Pune record: NDVI is not monotonic, so a 2021->2026 difference depends on endpoints."""
    real = {2021: 0.317, 2022: 0.349, 2023: 0.420, 2024: 0.338, 2025: 0.327, 2026: 0.371}
    out = match_claim("vegetation_index_change", 0.05, "ndvi_units", "since 2021", ctx(ndvi=real))
    assert out.status == SUPPORTED  # 2026 - 2021 = +0.054
    text = " ".join(out.limitations)
    assert "ranged from 0.317 to 0.420" in text and "year-to-year variation" in text
    assert any("All observed years" in a and "2023 0.420" in a for a in out.available_evidence)
    # a smooth record does not carry that warning
    smooth = {2021: 0.30, 2022: 0.32, 2023: 0.34, 2024: 0.36}
    quiet = match_claim(
        "vegetation_index_change", 0.30, "ndvi_units", "since 2021", ctx(ndvi=smooth)
    )
    assert not any("ranged from" in lim for lim in quiet.limitations)
