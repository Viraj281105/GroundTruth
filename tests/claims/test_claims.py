"""Tests for claim extraction, TF-IDF retrieval and comparison."""

from __future__ import annotations

from groundtruth.claims import (
    ClaimKind,
    Severity,
    TfidfIndex,
    chunk_text,
    compare_claims,
    extract_claims,
)

DOC = (
    "The project covers 12,500 hectares of forest. The baseline is 1.2 million tCO2e over the "
    "period. The project reduced deforestation by 40% in the crediting period. "
    "A total of 300,000 credits were issued in 2022."
)


def _by_kind(claims):
    return {c.kind: c for c in claims}


def test_extracts_all_kinds_with_spans():
    claims = _by_kind(extract_claims(DOC, "pdd"))
    assert claims[ClaimKind.AREA_HECTARES].value == 12500
    assert claims[ClaimKind.BASELINE].value == 1.2e6
    assert claims[ClaimKind.REDUCTION_PERCENT].value == 40
    assert claims[ClaimKind.CREDITS_ISSUED].value == 300000
    for c in claims.values():
        assert DOC[c.start : c.end] == c.quote


def test_bare_credit_number_without_issuance_cue_is_ignored():
    assert not extract_claims("Buyers may purchase 5,000 credits at any time.")


def test_index_retrieves_relevant_chunk():
    chunks = chunk_text(DOC, "pdd", size=120, overlap=20)
    hits = TfidfIndex(chunks).search("credits issued", k=2)
    assert hits and "credits" in hits[0].chunk.text


def test_compare_flags_difference_neutrally():
    claims = extract_claims(DOC, "pdd")
    found = compare_claims(claims, {"reduction_pct": 15, "area_ha": 12500})
    assert [d.kind for d in found] == [ClaimKind.REDUCTION_PERCENT]
    d = found[0]
    assert d.severity is Severity.LARGE
    assert "pdd[" in d.citation
    for word in ("fraud", "illegal", "deceiv", "mislead"):
        assert word not in d.message.lower()


def test_compare_within_tolerance_is_silent():
    assert not compare_claims(extract_claims(DOC), {"area_ha": 12600})
