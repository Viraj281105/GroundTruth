"""Tests for the GenAI grounding boundary.

These are the tests that make the architectural claim enforceable. If they pass,
a language model cannot put an invented number or an accusation into a published
GroundTruth report.
"""

from __future__ import annotations

import pytest

from groundtruth.core.errors import GroundingViolationError
from groundtruth.reporting.grounding import (
    GroundingPolicy,
    enforce_grounding,
    policy_for_bundle,
    verify_grounding,
)
from groundtruth.reporting.narrative import generate_report, render_deterministic
from groundtruth.reporting.providers import EchoNarrator


class TestNumericGrounding:
    def test_accepts_text_whose_numbers_all_come_from_the_bundle(self, bundle):
        text = "The estimated effect was 0.0421 with a permutation p-value of 0.0385."
        assert verify_grounding(text, bundle).grounded

    def test_rejects_an_invented_number(self, bundle):
        text = "The project over-issued 12400000 credits."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert "12400000" in report.ungrounded_numbers

    def test_rejects_a_plausible_but_unsupported_figure(self, bundle):
        """The dangerous case: a number that looks right but is not in the evidence."""
        text = "The estimated effect was 0.0430."
        assert not verify_grounding(text, bundle).grounded

    def test_accepts_a_percentage_rendering_of_a_bundle_value(self, bundle):
        text = "The permutation p-value corresponds to 3.85 percent of comparison regions."
        assert verify_grounding(text, bundle).grounded

    def test_allows_years(self, bundle):
        text = "The crediting period began in 2011 and the effect was 0.0421."
        assert verify_grounding(text, bundle).grounded

    def test_allows_small_integers_used_as_list_markers(self, bundle):
        text = "There are 3 findings. The effect was 0.0421."
        assert verify_grounding(text, bundle).grounded

    def test_grounding_rate_is_reported(self, bundle):
        report = verify_grounding("Values of 0.0421 and 99999.5 were seen.", bundle)
        assert report.checked_numbers == 2
        assert report.matched_numbers == 1
        assert report.grounding_rate == pytest.approx(0.5)

    def test_extra_allowed_values_are_honoured(self, bundle):
        policy = GroundingPolicy(extra_allowed_values=(785000.0,))
        assert verify_grounding("The project covers 785000 ha.", bundle, policy).grounded


class TestProhibitedAssertions:
    @pytest.mark.parametrize(
        "text",
        [
            "The developer committed fraud.",
            "This is a scam.",
            "The baseline was deliberately inflated.",
            "The project developer lied about the baseline.",
            "This is illegal under the standard.",
            "The analysis proves that the claim is wrong.",
            "The result conclusively shows over-issuance.",
            "The project is certainly over-credited.",
        ],
    )
    def test_accusatory_and_overclaiming_text_is_rejected(self, bundle, text):
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert report.prohibited_findings

    def test_index_to_carbon_phrasing_is_rejected(self, bundle):
        text = "An NDVI of 0.0421 equals 0.0385 tCO2e per hectare."
        report = verify_grounding(text, bundle)
        assert not report.grounded
        assert any("carbon" in f for f in report.prohibited_findings)

    def test_the_approved_framing_is_accepted(self, bundle):
        text = (
            "The independent estimate of 0.0421 diverges from the claim. This warrants "
            "accredited review; it is not a finding of wrongdoing."
        )
        assert verify_grounding(text, bundle).grounded


class TestRequiredCaveats:
    def test_dropping_the_verdict_caveats_fails(self, bundle):
        policy = policy_for_bundle(bundle)
        report = verify_grounding("The effect was 0.0421.", bundle, policy)
        assert not report.grounded
        assert report.missing_phrases

    def test_carrying_the_caveats_passes(self, bundle):
        policy = policy_for_bundle(bundle)
        assert bundle.verdict is not None
        text = "The effect was 0.0421.\n\n" + "\n".join(bundle.verdict.caveats)
        assert verify_grounding(text, bundle, policy).grounded


class TestEnforcement:
    def test_enforce_returns_grounded_text_unchanged(self, bundle):
        text = "The effect was 0.0421."
        assert enforce_grounding(text, bundle) == text

    def test_enforce_raises_on_a_violation(self, bundle):
        with pytest.raises(GroundingViolationError):
            enforce_grounding("The over-issuance was 5500000 credits.", bundle)


class TestDeterministicRenderer:
    def test_is_grounded_by_construction(self, bundle):
        """The no-model path must pass its own grounding check."""
        markdown = render_deterministic(bundle)
        assert verify_grounding(markdown, bundle, policy_for_bundle(bundle)).grounded

    def test_includes_every_evidence_item(self, bundle):
        markdown = render_deterministic(bundle)
        for item in bundle.items:
            assert item.label in markdown

    def test_includes_provenance_fingerprints(self, bundle):
        markdown = render_deterministic(bundle)
        for item in bundle.items:
            assert item.provenance.fingerprint() in markdown


class TestNarrationFallback:
    def test_no_narrator_yields_the_deterministic_report(self, bundle):
        report = generate_report(bundle, narrator=None)
        assert report.generator == "deterministic"
        assert not report.fell_back

    def test_a_hallucinating_narrator_is_rejected_and_falls_back(self, bundle):
        narrator = EchoNarrator("The project over-issued 9400000 credits through fraud.")
        report = generate_report(bundle, narrator=narrator)
        assert report.fell_back
        assert report.generator == "deterministic"
        assert report.grounding is not None and not report.grounding.grounded
        assert "9400000" not in report.markdown

    def test_a_grounded_narrator_is_accepted(self, bundle):
        assert bundle.verdict is not None
        text = (
            "The independent estimate of the incremental effect was 0.0421, with a permutation "
            "p-value of 0.0385 across 32 comparison regions.\n\n"
            + "\n".join(bundle.verdict.caveats)
        )
        report = generate_report(bundle, narrator=EchoNarrator(text))
        assert not report.fell_back
        assert report.generator == "genai:echo"
        assert report.markdown == text

    def test_a_failing_provider_degrades_to_deterministic(self, bundle):
        class Broken:
            name = "broken"

            def complete(self, system: str, user: str) -> str:
                raise RuntimeError("upstream timeout")

        report = generate_report(bundle, narrator=Broken())
        assert report.fell_back
        assert report.generator == "deterministic"
        assert "upstream timeout" in (report.fallback_reason or "")

    def test_the_narrator_receives_the_bundle_and_the_rules(self, bundle):
        narrator = EchoNarrator("0.0421")
        generate_report(bundle, narrator=narrator)
        system, user = narrator.calls[0]
        assert "Every number you write must appear in the evidence bundle" in system
        assert "Never state or imply fraud" in system
        assert bundle.case_id in user
