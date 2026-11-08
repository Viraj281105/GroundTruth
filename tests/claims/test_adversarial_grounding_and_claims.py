"""Adversarial grounding and claim verification tests.

Covers the 5 adversarial grounding vulnerabilities from Section 8 of the
Independent Post-Execution Audit:
1. Defamatory synonyms blocklist (grift/hoax/swindle/ponzi/sham, embezzlement/bribery/corruption/kickbacks/laundering/theft/stole)
2. Unsupported causal attribution ("project caused", "intervention drove", etc., while permitting negated disclaimers)
3. Unit smuggling ("NDVI as Carbon" without calibration or attaching carbon units to indicator effect values)
4. Semantic polarity / context inversion (positive indicator effect narrated as ecological destruction)
5. Verdict contradiction guard (asserting consistency/confirmation when verdict is INCONCLUSIVE or DIVERGENT_FROM_CLAIM)

Also tests ``verify_claims_against_bundle`` across all 5 ``ClaimVerificationStatus`` states:
SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED, NOT_VERIFIABLE, and INSUFFICIENT_EVIDENCE.
"""

from __future__ import annotations

import pytest

from groundtruth.claims.compare import (
    ClaimVerificationRecord,
    ClaimVerificationStatus,
    verify_claims_against_bundle,
)
from groundtruth.claims.extract import Claim, ClaimKind, extract_claims
from groundtruth.contracts.errors import GroundingViolationError
from groundtruth.contracts.evidence import Evidence, EvidenceBundle
from groundtruth.contracts.grounding import enforce_grounding, verify_grounding
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.types import (
    STANDARD_CAVEATS,
    VerdictLabel,
    VerificationVerdict,
)


class TestAdversarialDefamatorySynonyms:
    """Test that defamatory synonyms and criminal misconduct allegations are blocked."""

    @pytest.mark.parametrize(
        "word",
        ["grift", "hoax", "swindle", "ponzi", "sham"],
    )
    def test_scam_and_hoax_synonyms_blocked(self, bundle: EvidenceBundle, word: str) -> None:
        text = f"The estimated effect is 0.0421, exposing the project as a {word}."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert "alleges a scam or hoax" in report.prohibited_findings

    @pytest.mark.parametrize(
        "word",
        [
            "embezzlement",
            "embezzled",
            "bribery",
            "bribed",
            "corruption",
            "corrupt",
            "kickbacks",
            "laundering",
            "theft",
            "stole",
        ],
    )
    def test_criminal_misconduct_synonyms_blocked(
        self, bundle: EvidenceBundle, word: str
    ) -> None:
        text = f"With 32 donors and an effect of 0.0421, the discrepancy suggests {word}."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert "alleges criminal misconduct" in report.prohibited_findings


class TestAdversarialCausalAttribution:
    """Test that direct causal attribution is blocked while negated disclaimers pass."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "the project caused",
            "the project causes",
            "the project drove",
            "the project created",
            "the intervention caused",
            "the intervention drove",
            "the intervention created",
        ],
    )
    def test_direct_causal_attribution_blocked(
        self, bundle: EvidenceBundle, phrase: str
    ) -> None:
        text = f"Across 32 donors, {phrase} a 0.0421 gain in vegetation index."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert (
            "asserts direct causal attribution beyond observational screening"
            in report.prohibited_findings
        )

    def test_negated_causal_attribution_allowed(self, bundle: EvidenceBundle) -> None:
        text = (
            "The observed difference is 0.0421 across 32 donors (p = 0.0385), "
            "which does not prove that the project caused the change."
        )
        report = verify_grounding(text, bundle)
        assert report.grounded
        assert not report.prohibited_findings


class TestAdversarialUnitSmuggling:
    """Test that attaching carbon/credit units to spectral index values is blocked."""

    @pytest.mark.parametrize(
        "unit_phrase",
        [
            "tonnes of carbon credits per hectare",
            "tonnes of carbon",
            "tCO2e",
            "carbon credits",
            "credits per hectare",
            "tonnes of CO2",
        ],
    )
    def test_indicator_value_smuggled_as_carbon_blocked(
        self, bundle: EvidenceBundle, unit_phrase: str
    ) -> None:
        text = f"The project generated 0.0421 {unit_phrase} across 32 donor regions."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert (
            "converts an indicator value into carbon/credit units without calibration"
            in report.prohibited_findings
        )

    def test_unit_smuggling_blocked_even_when_carbon_item_present(
        self, provenance: Provenance
    ) -> None:
        calibrated_bundle = EvidenceBundle(
            case_id="calibrated-case",
            items=(
                Evidence(
                    id="effect.point_estimate",
                    label="Estimated incremental effect on ndvi",
                    value=0.0421,
                    unit="ndvi",
                    provenance=provenance,
                ),
                Evidence(
                    id="carbon.estimated_tco2e",
                    label="Calibration-conditional carbon estimate",
                    value=125000.0,
                    unit="tCO2e",
                    provenance=provenance,
                ),
            ),
            verdict=VerificationVerdict(
                label=VerdictLabel.CONSISTENT_WITH_CLAIM,
                rationale="Calibrated test.",
                caveats=STANDARD_CAVEATS,
            ),
        )
        text = "The analysis found 0.0421 tCO2e alongside the total of 125,000 tCO2e."
        report = verify_grounding(text, calibrated_bundle)
        assert not report.grounded
        assert (
            "converts an indicator value into carbon/credit units without calibration"
            in report.prohibited_findings
        )


class TestAdversarialContextInversion:
    """Test that positive indicator effects cannot be narrated as ecological destruction."""

    @pytest.mark.parametrize(
        "sentence",
        [
            "The intervention caused severe forest destruction of 0.0421 across the region.",
            "The project resulted in widespread habitat loss with an index of 0.0421.",
            "The region suffered catastrophic deforestation and ecosystem collapse (0.0421).",
            "The estimate shows 0.0421 deforestation across 32 donor units.",
            "The area led to ecocide with a 0.0421 shift.",
        ],
    )
    def test_positive_effect_narrated_as_destruction_blocked(
        self, bundle: EvidenceBundle, sentence: str
    ) -> None:
        report = verify_grounding(sentence, bundle)
        assert not report.grounded
        assert (
            "inverts positive indicator effect into ecological destruction"
            in report.prohibited_findings
        )


class TestAdversarialVerdictContradiction:
    """Test that narratives contradicting INCONCLUSIVE or DIVERGENT_FROM_CLAIM verdicts are blocked."""

    def test_inconclusive_verdict_contradicted_by_consistent_claim(
        self, provenance: Provenance
    ) -> None:
        inconclusive_bundle = EvidenceBundle(
            case_id="inc-case",
            items=(
                Evidence(
                    id="effect.point_estimate",
                    label="Estimated incremental effect on ndvi",
                    value=0.0421,
                    unit="ndvi",
                    provenance=provenance,
                ),
            ),
            verdict=VerificationVerdict(
                label=VerdictLabel.INCONCLUSIVE,
                rationale="Failed robustness gates.",
                caveats=STANDARD_CAVEATS,
            ),
        )
        for text in (
            "With an effect of 0.0421, the verdict is consistent with the claim.",
            "The screening outcome is consistent with claim expectations (0.0421).",
            "This 0.0421 result confirms the developer's claim.",
        ):
            report = verify_grounding(text, inconclusive_bundle)
            assert not report.grounded
            assert "contradicts the bundle's screening verdict" in report.prohibited_findings

    def test_divergent_verdict_contradicted_by_consistent_claim(
        self, bundle: EvidenceBundle
    ) -> None:
        text = "The estimated effect of 0.0421 across 32 donors is consistent with the claim."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert "contradicts the bundle's screening verdict" in report.prohibited_findings
        with pytest.raises(GroundingViolationError):
            enforce_grounding(text, bundle)

    def test_negated_consistency_statement_allowed_on_divergent_bundle(
        self, bundle: EvidenceBundle
    ) -> None:
        text = (
            "The estimated effect of 0.0421 across 32 donors (p = 0.0385) "
            "is not consistent with the claim."
        )
        report = verify_grounding(text, bundle)
        assert report.grounded
        assert "contradicts the bundle's screening verdict" not in report.prohibited_findings


class TestVerifyClaimsAgainstBundle:
    """Test verify_claims_against_bundle across all 5 ClaimVerificationStatus values."""

    def test_credits_not_verifiable_when_uncalibrated(self, bundle: EvidenceBundle) -> None:
        claims = extract_claims("The project had 100,000 credits issued in 2022.")
        records = verify_claims_against_bundle(claims, bundle)
        assert len(records) == 1
        rec = records[0]
        assert isinstance(rec, ClaimVerificationRecord)
        assert rec.status is ClaimVerificationStatus.NOT_VERIFIABLE
        assert rec.evidence_id is None
        assert rec.observed_value is None
        assert "NDVI is not carbon" in rec.rationale

    def test_credits_insufficient_evidence_when_robustness_inconclusive(
        self, provenance: Provenance
    ) -> None:
        inc_bundle = EvidenceBundle(
            case_id="inc-gates",
            items=(
                Evidence(
                    id="effect.point_estimate",
                    label="Effect",
                    value=0.01,
                    unit="ndvi",
                    provenance=provenance,
                ),
            ),
            verdict=VerificationVerdict(
                label=VerdictLabel.INCONCLUSIVE,
                rationale=(
                    "The pipeline ran but the result does not meet the robustness bar "
                    "required to report a screening outcome: donor pool has 4 units."
                ),
                caveats=STANDARD_CAVEATS,
            ),
        )
        claims = extract_claims("A total of 50,000 VCUs were issued.")
        records = verify_claims_against_bundle(claims, inc_bundle)
        assert len(records) == 1
        assert records[0].status is ClaimVerificationStatus.INSUFFICIENT_EVIDENCE
        assert "NDVI is not carbon" in records[0].rationale

    def test_credits_supported_partially_supported_and_contradicted(
        self, provenance: Provenance
    ) -> None:
        calibrated_bundle = EvidenceBundle(
            case_id="cal-case",
            items=(
                Evidence(
                    id="carbon.estimated_tco2e",
                    label="Calibrated carbon estimate",
                    value=100_000.0,
                    unit="tCO2e",
                    provenance=provenance,
                    qualifiers={"area_ha": 10_000.0},
                ),
            ),
        )
        supported_claim = Claim(
            kind=ClaimKind.CREDITS_ISSUED,
            value=105_000.0,
            unit="credits",
            doc_id="pdd",
            start=0,
            end=10,
            quote="105,000 credits issued",
        )
        partial_claim = Claim(
            kind=ClaimKind.CREDITS_ISSUED,
            value=125_000.0,
            unit="credits",
            doc_id="pdd",
            start=11,
            end=20,
            quote="125,000 credits issued",
        )
        contradicted_claim = Claim(
            kind=ClaimKind.BASELINE,
            value=200_000.0,
            unit="tCO2e",
            doc_id="pdd",
            start=21,
            end=30,
            quote="baseline of 200,000 tCO2e",
        )

        records = verify_claims_against_bundle(
            [supported_claim, partial_claim, contradicted_claim],
            calibrated_bundle,
        )
        assert [r.status for r in records] == [
            ClaimVerificationStatus.SUPPORTED,
            ClaimVerificationStatus.PARTIALLY_SUPPORTED,
            ClaimVerificationStatus.CONTRADICTED,
        ]
        for rec in records:
            assert rec.evidence_id == "carbon.estimated_tco2e"
            assert rec.observed_value == 100_000.0
            assert rec.observed_unit == "tCO2e"
            assert rec.relative_difference is not None

    def test_area_hectares_verification_statuses(
        self, bundle: EvidenceBundle, provenance: Provenance
    ) -> None:
        area_claim_ok = Claim(
            kind=ClaimKind.AREA_HECTARES,
            value=10_200.0,
            unit="ha",
            doc_id="pdd",
            start=0,
            end=10,
            quote="10,200 ha",
        )
        area_claim_partial = Claim(
            kind=ClaimKind.AREA_HECTARES,
            value=11_500.0,
            unit="ha",
            doc_id="pdd",
            start=11,
            end=20,
            quote="11,500 ha",
        )
        area_claim_contradicted = Claim(
            kind=ClaimKind.AREA_HECTARES,
            value=20_000.0,
            unit="ha",
            doc_id="pdd",
            start=21,
            end=30,
            quote="20,000 ha",
        )

        # Without area in bundle -> INSUFFICIENT_EVIDENCE
        missing_records = verify_claims_against_bundle([area_claim_ok], bundle)
        assert missing_records[0].status is ClaimVerificationStatus.INSUFFICIENT_EVIDENCE

        # With claim.project_area_ha in bundle
        area_bundle = bundle.with_items(
            Evidence(
                id="claim.project_area_ha",
                label="Project area",
                value=10_000.0,
                unit="ha",
                provenance=provenance,
            )
        )
        records = verify_claims_against_bundle(
            [area_claim_ok, area_claim_partial, area_claim_contradicted],
            area_bundle,
        )
        assert [r.status for r in records] == [
            ClaimVerificationStatus.SUPPORTED,
            ClaimVerificationStatus.PARTIALLY_SUPPORTED,
            ClaimVerificationStatus.CONTRADICTED,
        ]
        assert all(r.evidence_id == "claim.project_area_ha" for r in records)

    def test_reduction_percent_not_verifiable(self, bundle: EvidenceBundle) -> None:
        claims = extract_claims("The project achieved a 45% reduction in deforestation.")
        records = verify_claims_against_bundle(claims, bundle)
        assert len(records) == 1
        assert records[0].status is ClaimVerificationStatus.NOT_VERIFIABLE
        assert records[0].evidence_id is None
