"""Tests for the HTTP API and the command-line interface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from groundtruth.cli import main
from groundtruth.platform.api.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestApi:
    def test_health_reports_capabilities_honestly(self, client):
        payload = client.get("/health").json()
        assert payload["status"] == "ok"
        assert payload["earth_observation_implemented"] is False
        assert payload["genai_narration_implemented"] is False
        assert payload["cases_available"] >= 3

    def test_cases_are_listed(self, client):
        cases = client.get("/cases").json()
        assert {c["case_id"] for c in cases} >= {"kariba-redd", "mikoko-pamoja"}

    def test_case_detail_includes_the_known_reference(self, client):
        detail = client.get("/cases/kariba-redd").json()
        assert detail["registry_id"] == "VCS 902"
        assert detail["known_reference"]

    def test_unknown_case_returns_404(self, client):
        assert client.get("/cases/nope").status_code == 404

    def test_observed_data_verification_is_refused_not_simulated(self, client):
        """The API must never serve simulated numbers under a real-data label."""
        response = client.post("/cases/kariba-redd/verify", json={"synthetic": False})
        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"]

    def test_synthetic_verification_returns_a_bundle_labelled_simulated(self, client):
        payload = client.post("/cases/kariba-redd/verify", json={"synthetic": True}).json()
        assert payload["data_mode"] == "simulated"
        assert payload["bundle"]["items"]
        assert any("SIMULATED DATA" in w for w in payload["warnings"])

    def test_verification_response_always_carries_caveats(self, client):
        payload = client.post("/cases/kariba-redd/verify", json={"synthetic": True}).json()
        assert payload["caveats"]
        assert any("not evidence of" in c for c in payload["caveats"])

    def test_an_underpowered_request_returns_422(self, client):
        response = client.post(
            "/cases/kariba-redd/verify", json={"synthetic": True, "min_donors": 500}
        )
        assert response.status_code == 422

    def test_openapi_schema_builds(self, client):
        assert client.get("/openapi.json").status_code == 200


class TestCli:
    def test_cases_command_lists_the_cases(self, capsys):
        assert main(["cases"]) == 0
        assert "kariba-redd" in capsys.readouterr().out

    def test_cases_json_output_parses(self, capsys):
        import json

        assert main(["cases", "--json"]) == 0
        assert "kariba-redd" in json.loads(capsys.readouterr().out)

    def test_show_command_prints_the_known_reference_disclaimer(self, capsys):
        assert main(["show", "kariba-redd"]) == 0
        assert "NOT an input to the estimate" in capsys.readouterr().out

    def test_show_on_an_unknown_case_fails_cleanly(self, capsys):
        assert main(["show", "nope"]) == 1
        assert "error:" in capsys.readouterr().err

    def test_verify_without_synthetic_refuses_to_run(self, capsys):
        assert main(["verify", "kariba-redd"]) == 2
        assert "not implemented yet" in capsys.readouterr().err

    def test_verify_synthetic_prints_a_simulated_data_banner(self, capsys):
        assert main(["verify", "kariba-redd", "--synthetic"]) == 0
        captured = capsys.readouterr()
        assert "SIMULATED DATA RUN" in captured.err
        assert "Verification screening report" in captured.out

    def test_verify_json_emits_a_parseable_analysis_result(self, capsys):
        from groundtruth.contracts.result import AnalysisResult

        assert main(["verify", "kariba-redd", "--synthetic", "--json"]) == 0
        result = AnalysisResult.model_validate_json(capsys.readouterr().out)
        assert result.case_id == "kariba-redd"
        assert result.spec_hash
        assert result.is_simulated

    def test_verify_writes_report_and_bundle_to_disk(self, tmp_path, capsys):
        out = tmp_path / "report.md"
        assert main(["verify", "kariba-redd", "--synthetic", "--out", str(out)]) == 0
        capsys.readouterr()
        assert out.exists()
        assert out.with_suffix(".result.json").exists()

    def test_doctor_does_not_overstate_what_is_implemented(self, capsys):
        assert main(["doctor"]) == 0
        output = capsys.readouterr().out
        assert "earth observation implemented" in output
        assert "no - see docs/product/roadmap-detail.md M1" in output
        assert "no - deterministic renderer is used" in output
        assert "engine: biomass carbon conversion" in output
