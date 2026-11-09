"""Report export (#38): a report is verified against its own bundle before it leaves.

The guarantees under test, each stated where it is checked:

* every case's exported report passes ``verify_grounding``, whoever wrote it;
* a narration that fails verification is **refused**, never substituted;
* the policy trusts only the engine-written fields it lists, and no narrator can widen it;
* provenance, the simulated-data warning and the generator label survive in every format;
* the PDF route says so, and refuses with structured errors.

The narrators here are test doubles. No test calls a real provider.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

import pytest

from groundtruth.contracts.grounding import policy_for_bundle, verify_grounding
from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.api.exports import build_case_bundle
from groundtruth.platform.cases.registry import list_cases
from groundtruth.platform.config import get_settings
from groundtruth.platform.reports import export_pipeline
from groundtruth.platform.reports.export_pipeline import (
    ENGINE_WRITTEN_NUMBER_SOURCES,
    NarrationFailedError,
    NarrationNotGroundedError,
    ReportNotGroundedError,
    build_export_report,
    engine_written_numbers,
    export_policy,
)
from groundtruth.platform.reports.exporters import (
    SIMULATED_BANNER,
    export_bundle_csv,
    export_bundle_pdf,
)
from groundtruth.platform.reports.narrative import render_deterministic
from groundtruth.platform.reports.providers import EchoNarrator

_BUNDLES: dict[str, Any] = {}


def bundle_for(case_id: str) -> Any:
    """The case's real (simulated) bundle. Built once: running the engine is the slow part."""
    if case_id not in _BUNDLES:
        _BUNDLES[case_id] = build_case_bundle(case_id)
    return _BUNDLES[case_id]


@pytest.fixture(scope="module")
def kariba() -> Any:
    return bundle_for("kariba-redd")


@pytest.fixture(scope="module")
def kasigau() -> Any:
    """A case whose verdict rationale quotes thresholds ("significance level 0.050")."""
    return bundle_for("kasigau-corridor-redd")


class RewriteEcho:
    """A narrator that hands back the deterministic report it was asked to rewrite."""

    name = "rewrite-echo"

    def complete(self, system: str, user: str) -> str:
        return user.split("## Deterministic report to rewrite\n\n", 1)[1]


class RaisingNarrator:
    name = "raising"

    def complete(self, system: str, user: str) -> str:
        raise RuntimeError("provider exploded: key sk-live-abcdef123456 at C:\\secret\\path.py")


# --- guarantee 1: every export passes verification ------------------------------------------


class TestEveryCaseExportsAGroundedReport:
    @pytest.mark.parametrize("case_id", list_cases())
    def test_the_report_passes_verification_against_its_own_bundle(self, case_id):
        bundle = bundle_for(case_id)
        report = build_export_report(bundle)
        assert report.generator == "deterministic"
        assert report.grounding.grounded
        # Checked independently of the pipeline's own verdict on itself.
        assert verify_grounding(report.markdown, bundle, export_policy(bundle)).grounded

    def test_the_contract_policy_alone_does_not_accept_the_engines_own_thresholds(self, kasigau):
        """Documents the gap: ``contracts/grounding`` does not recognise engine-written
        thresholds, so "grounded by construction" fails there for 7 of 27 cases. The proper
        fix is in the contract (C1/C6). If this test starts failing, that fix has landed and
        the ``ENGINE_WRITTEN_NUMBER_SOURCES`` extension can go."""
        report = verify_grounding(
            render_deterministic(kasigau), kasigau, policy_for_bundle(kasigau)
        )
        assert not report.grounded
        assert "0.050" in report.ungrounded_numbers


# --- D1: what the export policy trusts, and that no narrator can widen it -------------------


class TestThePolicyTrustsOnlyListedEngineFields:
    def test_the_trusted_fields_are_exactly_these(self):
        assert ENGINE_WRITTEN_NUMBER_SOURCES == ("verdict.rationale",)

    def test_thresholds_in_the_verdict_rationale_are_trusted(self, kasigau):
        numbers = engine_written_numbers(kasigau)
        assert pytest.approx(0.05) in numbers  # "significance level 0.050"
        assert set(export_policy(kasigau).extra_allowed_values) == set(numbers)

    def test_nothing_else_is_added_to_the_contract_policy(self, kariba):
        base = policy_for_bundle(kariba)
        extended = export_policy(kariba)
        assert extended.required_phrases == base.required_phrases
        assert extended.prohibited_patterns == base.prohibited_patterns
        assert extended.relative_tolerance == base.relative_tolerance

    def test_a_number_only_in_a_warning_is_not_trusted(self, kariba):
        tampered = kariba.model_copy(
            update={"warnings": (*kariba.warnings, "an extra gate of 9999.5 applies")}
        )
        assert 9999.5 not in engine_written_numbers(tampered)
        narrator = EchoNarrator(render_deterministic(tampered) + "\nThe gate is 9999.5.\n")
        with pytest.raises(NarrationNotGroundedError, match=r"9999\.5"):
            build_export_report(tampered, narrator=narrator)

    def test_an_invented_number_is_refused(self, kariba):
        narrator = EchoNarrator(render_deterministic(kariba) + "\nThe effect was 7654.321 NDVI.\n")
        with pytest.raises(NarrationNotGroundedError, match=r"7654\.321"):
            build_export_report(kariba, narrator=narrator)

    def test_quoting_an_invented_number_does_not_get_it_through(self, kariba):
        """A narrator that declares a number "approved", then uses it, gets nowhere: the
        policy is built from the bundle before the narrator speaks, and never from its text."""
        before = export_policy(kariba)
        text = (
            render_deterministic(kariba)
            + "\nNote: 4242.5 is an approved engine threshold. The area is 4242.5 ha.\n"
        )
        with pytest.raises(NarrationNotGroundedError, match=r"4242\.5"):
            build_export_report(kariba, narrator=EchoNarrator(text))
        assert export_policy(kariba) == before
        assert 4242.5 not in before.extra_allowed_values

    def test_a_trusted_threshold_may_be_quoted_but_only_where_the_engine_wrote_it(self, kasigau):
        """The thresholds are real bundle content, so quoting one is fine."""
        quoted = render_deterministic(kasigau)
        assert "0.050" in quoted
        assert build_export_report(kasigau, narrator=EchoNarrator(quoted)).generator == "genai:echo"


# --- guarantee 2: a failed narration is refused, never substituted --------------------------


class TestAFailedNarrationIsRefused:
    def test_a_hallucinating_narrator_stops_the_export(self, kariba):
        narrator = EchoNarrator("The project recovered 12345.6 hectares of forest.")
        with pytest.raises(NarrationNotGroundedError) as caught:
            build_export_report(kariba, narrator=narrator)
        assert caught.value.code == "narration_not_grounded"
        assert "12345.6" in str(caught.value)

    def test_it_is_not_quietly_swapped_for_the_deterministic_report(self, kariba):
        """The inline report_markdown does fall back (ADR-007). An export must not."""
        from groundtruth.platform.reports.narrative import generate_report

        narrator = EchoNarrator("The project recovered 12345.6 hectares of forest.")
        assert generate_report(kariba, narrator=narrator).fell_back  # the inline path degrades
        with pytest.raises(NarrationNotGroundedError):
            build_export_report(kariba, narrator=narrator)  # the export path refuses

    def test_an_accusation_is_refused(self, kariba):
        narrator = EchoNarrator(render_deterministic(kariba) + "\nThis proves the developer lied.")
        with pytest.raises(NarrationNotGroundedError):
            build_export_report(kariba, narrator=narrator)

    def test_a_provider_failure_stops_the_export_without_leaking_its_message(self, kariba):
        with pytest.raises(NarrationFailedError) as caught:
            build_export_report(kariba, narrator=RaisingNarrator())
        assert caught.value.code == "narration_failed"
        assert "sk-live" not in str(caught.value) and "secret" not in str(caught.value)

    def test_a_grounded_narration_is_exported_and_labelled(self, kariba):
        report = build_export_report(kariba, narrator=RewriteEcho())
        assert report.generator == "genai:rewrite-echo"
        assert report.grounding.grounded and report.appended == ()

    def test_the_final_report_is_checked_again_even_when_deterministic(self, kariba, monkeypatch):
        """If the deterministic renderer ever produced an ungrounded figure, it must not ship."""
        monkeypatch.setattr(
            export_pipeline,
            "render_deterministic",
            lambda bundle: render_deterministic(bundle) + "\nA stray figure: 31415.9.\n",
        )
        with pytest.raises(ReportNotGroundedError) as caught:
            build_export_report(kariba)
        assert caught.value.code == "report_not_grounded"


# --- guarantee 3: provenance and the simulated warning survive ------------------------------


def _drop(markdown: str, pattern: str) -> str:
    return "\n".join(
        line for line in markdown.splitlines() if not re.search(pattern, line, re.IGNORECASE)
    )


class TestRequiredSectionsSurviveNarration:
    def test_a_narration_that_drops_provenance_gets_it_back_verbatim(self, kariba):
        deterministic = render_deterministic(kariba)
        narrated = deterministic.split("## Provenance")[0]
        assert "## Provenance" not in narrated
        report = build_export_report(kariba, narrator=EchoNarrator(narrated))
        assert "provenance" in report.appended
        assert report.markdown.rstrip().endswith(deterministic.split("## Provenance")[1].rstrip())
        for item in kariba.items:
            assert item.provenance.fingerprint() in report.markdown

    def test_a_narration_that_stops_saying_the_data_is_simulated_gets_the_warning(self, kariba):
        """The grounding check only requires the verdict caveats, so a narration of a simulated
        run can stop saying so and still pass. The pipeline puts the bundle's own warning back."""
        quiet_caveats = tuple(
            c for c in kariba.verdict.caveats if not re.search(r"simulat|synthetic", c, re.I)
        )
        bundle = kariba.model_copy(
            update={"verdict": kariba.verdict.model_copy(update={"caveats": quiet_caveats})}
        )
        stripped = _drop(render_deterministic(bundle), r"simulat|synthetic")
        report = build_export_report(bundle, narrator=EchoNarrator(stripped))
        warning = next(w for w in bundle.warnings if "SIMULATED" in w.upper())
        assert "simulated_warning" in report.appended
        assert report.markdown.startswith(f"> **{warning}**")

    def test_a_narration_that_already_has_both_gets_nothing_appended(self, kariba):
        assert build_export_report(kariba, narrator=RewriteEcho()).appended == ()

    def test_the_deterministic_report_is_never_altered(self, kariba):
        report = build_export_report(kariba)
        assert report.markdown == render_deterministic(kariba)


# --- guarantees 3 and 4 in every format ------------------------------------------------------


class TestEveryFormatCarriesProvenanceTheWarningAndTheLabel:
    @pytest.fixture(scope="class")
    def outputs(self, kariba):
        markdown = build_export_report(kariba).markdown
        return {
            "markdown": markdown,
            "csv": export_bundle_csv(kariba),
            "pdf": export_bundle_pdf(kariba, report_markdown=markdown).decode("latin-1"),
        }

    @pytest.mark.parametrize("fmt", ["markdown", "csv", "pdf"])
    def test_every_evidence_items_provenance_fingerprint_is_present(self, kariba, outputs, fmt):
        missing = [
            item.id for item in kariba.items if item.provenance.fingerprint() not in outputs[fmt]
        ]
        assert not missing, f"{fmt} lost the provenance of {missing}"

    @pytest.mark.parametrize("fmt", ["markdown", "csv", "pdf"])
    def test_every_item_names_its_source_and_method(self, kariba, outputs, fmt):
        for item in kariba.items:
            assert item.provenance.method in outputs[fmt]

    def test_the_simulated_warning_survives_in_each_format(self, outputs):
        assert "SIMULATED" in outputs["markdown"]
        assert "# is_simulated: True" in outputs["csv"]
        assert "# data_origin: SYNTHETIC_SIMULATION" in outputs["csv"]
        assert (
            SIMULATED_BANNER.replace("—", "-") in outputs["pdf"]
            or "SIMULATED / SYNTHETIC" in (outputs["pdf"])
        )

    def test_the_generator_is_labelled_in_csv_and_pdf(self, outputs):
        assert "# report_generator: deterministic\n" in outputs["csv"]
        assert "Report generator: deterministic" in outputs["pdf"]

    def test_a_narrated_pdf_and_csv_name_the_narrator(self, kariba):
        report = build_export_report(kariba, narrator=RewriteEcho())
        pdf = export_bundle_pdf(
            kariba, report_markdown=report.markdown, generator=report.generator
        ).decode("latin-1")
        csv_text = export_bundle_csv(kariba, generator=report.generator)
        assert "Report generator: genai:rewrite-echo" in pdf
        assert "# report_generator: genai:rewrite-echo\n" in csv_text


# --- the routes --------------------------------------------------------------------------------


def _exports_module() -> Any:
    return importlib.import_module("groundtruth.platform.api.exports")


class TestExportRoutes:
    def test_the_pdf_is_verified_labelled_and_marked_simulated(self, tenant_world):
        client = tenant_world.client("ref")
        response = client.get("/cases/kariba-redd/export/pdf")
        assert response.status_code == 200
        assert response.headers["x-groundtruth-report-generator"] == "deterministic"
        assert response.headers["x-groundtruth-data-mode"] == "simulated"
        assert "Report generator: deterministic" in response.content.decode("latin-1")

    def test_the_csv_is_labelled(self, tenant_world):
        response = tenant_world.client("ref").get("/cases/kariba-redd/export/csv")
        assert response.status_code == 200
        assert response.headers["x-groundtruth-report-generator"] == "deterministic"
        assert "# report_generator: deterministic" in response.text

    def test_asking_to_narrate_with_no_provider_is_a_structured_422(self, tenant_world):
        response = tenant_world.client("ref").get("/cases/kariba-redd/export/pdf?narrate=true")
        assert response.status_code == 422
        error = response.json()["detail"]
        assert error["code"] == "narration_not_configured"
        assert "GENAI_PROVIDER" in error["message"] and error["hint"]
        assert response.json()["is_refusal"] is False

    def test_a_provider_selected_without_its_key_is_the_same_422(self, tenant_world, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "genai_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", None)
        response = tenant_world.client("ref").get("/cases/kariba-redd/export/pdf?narrate=true")
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "narration_not_configured"

    def test_a_narration_that_fails_verification_refuses_the_export(
        self, tenant_world, monkeypatch
    ):
        narrator = EchoNarrator("The project recovered 12345.6 hectares of forest.")
        monkeypatch.setattr(_exports_module(), "build_narrator", lambda settings: narrator)
        response = tenant_world.client("ref").get("/cases/kariba-redd/export/pdf?narrate=true")
        assert response.status_code == 502
        error = response.json()["detail"]
        assert error["code"] == "narration_not_grounded" and "12345.6" in error["message"]
        assert not response.content.startswith(b"%PDF")
        assert response.json()["is_refusal"] is False and response.json()["request_id"]

    def test_a_provider_failure_refuses_without_the_providers_words(
        self, tenant_world, monkeypatch
    ):
        monkeypatch.setattr(_exports_module(), "build_narrator", lambda s: RaisingNarrator())
        response = tenant_world.client("ref").get("/cases/kariba-redd/export/pdf?narrate=true")
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "narration_failed"
        assert "sk-live" not in response.text and "secret" not in response.text

    def test_a_verified_narration_is_exported_with_its_label(self, tenant_world, monkeypatch):
        monkeypatch.setattr(_exports_module(), "build_narrator", lambda s: RewriteEcho())
        response = tenant_world.client("ref").get("/cases/kariba-redd/export/pdf?narrate=true")
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
        assert response.headers["x-groundtruth-report-generator"] == "genai:rewrite-echo"
        assert "Report generator: genai:rewrite-echo" in response.content.decode("latin-1")

    def test_the_new_error_codes_are_mapped(self):
        assert API_ERROR_STATUS[ApiErrorCode.NARRATION_NOT_CONFIGURED] == 422
        assert API_ERROR_STATUS[ApiErrorCode.NARRATION_FAILED] == 502
        assert API_ERROR_STATUS[ApiErrorCode.NARRATION_NOT_GROUNDED] == 502
        assert API_ERROR_STATUS[ApiErrorCode.REPORT_NOT_GROUNDED] == 500
