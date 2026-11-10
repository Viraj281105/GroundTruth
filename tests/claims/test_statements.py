"""Multi-claim, overclaim-aware text analysis (no language model, no fabricated outcomes)."""

from __future__ import annotations

from groundtruth.claims import StatementKind as K
from groundtruth.claims import StatementStatus as S
from groundtruth.claims import analyze_text

SAMPLE = (
    "The project restores 1,200 hectares of degraded dry forest. "
    "85% of planted seedlings survived after 3 years. "
    "NDVI increased by 0.15 since 2021. "
    "The project has sequestered 40,000 tCO2e and proves biodiversity has fully recovered."
)


def test_four_claim_sample_yields_every_claim() -> None:
    a = analyze_text(SAMPLE)
    kinds = [s.kind for s in a.statements]
    assert kinds == [
        K.AREA_HECTARES,
        K.SURVIVAL_RATE,
        K.VEGETATION_INDEX_CHANGE,
        K.CARBON_TCO2E,
        K.BIODIVERSITY_RECOVERY,
    ]
    area, surv, ndvi, carbon, bio = a.statements
    assert (area.value, area.unit) == (1200.0, "ha")
    assert (surv.value, surv.unit, surv.period) == (85.0, "percent", "after 3 years")
    assert (ndvi.value, ndvi.unit, ndvi.period) == (0.15, "ndvi_units", "since 2021")
    assert (carbon.value, carbon.unit) == (40000.0, "tCO2e")
    assert bio.status is S.OVERCLAIM
    assert a.unrecognised == []


def test_spans_preserve_original_text() -> None:
    stmts = analyze_text(SAMPLE).statements
    for s in stmts:
        assert SAMPLE[s.start : s.end] == s.text
    texts = [s.text for s in stmts]
    assert texts[0] == "The project restores 1,200 hectares of degraded dry forest"
    assert texts[3] == "The project has sequestered 40,000 tCO2e"
    assert texts[4] == "proves biodiversity has fully recovered"


def test_every_statement_has_reason_and_evidence_gap_and_no_invented_numbers() -> None:
    for s in analyze_text(SAMPLE).statements:
        assert s.reason and s.evidence_gap
        assert s.evidence_link is None  # nothing was attached, so nothing is linked
        assert s.status in set(S)
        assert not hasattr(s, "confidence") and not hasattr(s, "verdict")


def test_overclaim_wording_detected() -> None:
    for text in (
        "This guarantees permanent carbon storage.",
        "The ecosystem is fully recovered.",
        "Results prove the project works.",
    ):
        a = analyze_text(text)
        assert any(s.status is S.OVERCLAIM for s in a.statements), text


def test_ndvi_to_carbon_conflation_flagged() -> None:
    a = analyze_text("Rising NDVI means 5,000 tCO2e were stored.")
    carbon = [s for s in a.statements if s.kind is K.CARBON_TCO2E]
    assert carbon and carbon[0].status is S.OVERCLAIM and "cannot be converted" in carbon[0].reason
    b = analyze_text("NDVI increased, so carbon sequestration increased.")
    assert any(s.kind is K.INDEX_TO_CARBON for s in b.statements)


def test_causal_attribution_needs_counterfactual() -> None:
    a = analyze_text("The greening is due to the project intervention.")
    c = [s for s in a.statements if s.kind is K.CAUSAL_ATTRIBUTION]
    assert c and c[0].status is S.UNSUPPORTED and "counterfactual" in c[0].reason


def test_unrecognised_sentences_returned_not_dropped() -> None:
    t = "Community meetings were held monthly. NDVI decreased by 0.05 since 2020."
    a = analyze_text(t)
    assert [u.text for u in a.unrecognised] == ["Community meetings were held monthly"]
    ndvi = a.statements[0]
    assert ndvi.value == -0.05 and ndvi.period == "since 2020"


def test_no_fraud_language_in_any_reason() -> None:
    for s in analyze_text(SAMPLE).statements:
        low = (s.reason + (s.evidence_gap or "")).lower()
        assert not any(w in low for w in ("fraud", "scam", "crime", "theft", "lying"))


def test_empty_and_whitespace_input() -> None:
    a = analyze_text("   \n  ")
    assert a.statements == [] and a.unrecognised == []


def test_permanent_sample_plots_is_a_monitoring_method_not_an_overclaim() -> None:
    # "Permanent sample plot" is the standard forestry term for a re-measured field plot. A
    # sentence that only describes monitoring must not be read as absolute wording.
    t = "Monitoring uses annual field surveys of permanent sample plots."
    a = analyze_text(t)
    assert a.statements == []
    assert [u.text for u in a.unrecognised] == [t.rstrip(".")]


def test_permanent_as_a_guarantee_is_still_an_overclaim() -> None:
    a = analyze_text("The restored forest is permanent and carries zero risk.")
    assert [s.kind for s in a.statements] == [K.UNSUPPORTED_CONCLUSION]
    assert a.statements[0].status is S.OVERCLAIM


def test_quantified_biodiversity_change_is_recognised_and_unsupported() -> None:
    # "increased by 20 percent" names no recovery verb, but it is still a biodiversity claim
    # that only a field survey can test. It must be listed, not silently dropped.
    t = "Bird species richness in the project area has increased by 20 percent since 2021."
    a = analyze_text(t)
    assert [s.kind for s in a.statements] == [K.BIODIVERSITY_RECOVERY]
    bio = a.statements[0]
    assert bio.status is S.UNSUPPORTED and bio.value is None and bio.period == "since 2021"
    assert "field surveys" in bio.reason
    assert a.unrecognised == []


def test_a_sentence_that_only_mentions_wildlife_makes_no_claim() -> None:
    a = analyze_text("Rangers record wildlife sightings every month.")
    assert a.statements == []
