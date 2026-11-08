"""Tests for synthetic-fixture vs real Earth-observation data separation.

The precomputed Kariba series is a SYNTHETIC fixture. It must never be
presented as satellite observations, and the real-data path must refuse rather
than fall back to it.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from groundtruth.cli import main
from groundtruth.contracts.errors import DataUnavailableError
from groundtruth.contracts.evidence import EvidenceBundle
from groundtruth.contracts.ports import ObservationSpec
from groundtruth.contracts.request import UnitRef
from groundtruth.contracts.result import EngineStatus
from groundtruth.contracts.types import Indicator, VerdictLabel
from groundtruth.engine import run_analysis
from groundtruth.platform.api.app import app
from groundtruth.platform.cases.registry import get_case
from groundtruth.platform.datasets.access import (
    SYNTHETIC_KARIBA_FIXTURE_DATASET,
    SyntheticFixtureCovariateAccess,
    SyntheticFixtureDonorAccess,
    SyntheticFixtureObservationAccess,
    earth_engine_access,
    real_observation_cases,
    synthetic_fixture_access,
    synthetic_fixture_paths,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _fixture_request():
    case = get_case("kariba-redd")
    return case.to_request(data_mode="simulated", datasets=(SYNTHETIC_KARIBA_FIXTURE_DATASET,))


class TestFixtureIsLabelledSynthetic:
    def test_dataset_ref_is_synthetic(self) -> None:
        assert SYNTHETIC_KARIBA_FIXTURE_DATASET.provider == "synthetic"
        assert SYNTHETIC_KARIBA_FIXTURE_DATASET.is_synthetic is True
        assert SYNTHETIC_KARIBA_FIXTURE_DATASET.source_uri is None

    def test_fixture_file_declares_itself_synthetic(self) -> None:
        path = next(p for p in synthetic_fixture_paths() if p.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["synthetic"] is True
        assert data["SYNTHETIC"] is True
        assert data["dataset_ref"]["provider"] == "synthetic"
        assert "SYNTHETIC" in data["fixture_warning"]
        # Historical mislabel is preserved for auditability, not silently dropped.
        assert data["historical_mislabel"]["former_dataset_ref"]["provider"] == "copernicus-usgs"
        assert "copernicus" not in json.dumps(data["dataset_ref"]).lower()

    def test_all_ports_report_synthetic(self) -> None:
        data = synthetic_fixture_access(_fixture_request())
        assert isinstance(data.observations, SyntheticFixtureObservationAccess)
        assert isinstance(data.covariates, SyntheticFixtureCovariateAccess)
        assert isinstance(data.donors, SyntheticFixtureDonorAccess)
        assert data.observations.dataset(Indicator.NDVI).is_synthetic
        assert data.covariates.dataset("elevation_m").is_synthetic
        spec = ObservationSpec(
            unit=UnitRef(unit_id="kariba-redd"),
            indicator=Indicator.NDVI,
            start_period=2001,
            end_period=2022,
        )
        prov = data.observations.provenance(spec)
        assert prov.source == "synthetic"
        assert "SYNTHETIC" in (prov.notes or "")
        assert "satellite" not in (prov.notes or "").lower().replace("not satellite", "")

    def test_run_is_marked_simulated_and_inconclusive(self) -> None:
        request = _fixture_request()
        result = run_analysis(request, synthetic_fixture_access(request))
        assert result.status == EngineStatus.COMPLETED
        assert result.is_simulated is True
        assert result.bundle is not None
        assert result.bundle.is_simulated is True
        assert any("SIMULATED DATA" in w for w in result.bundle.warnings)
        assert all(d.provider == "synthetic" for d in result.datasets)
        assert result.bundle.verdict is not None
        assert result.bundle.verdict.label is VerdictLabel.INCONCLUSIVE
        assert "carbon.estimated_tco2e" not in result.bundle
        assert any("SYNTHETIC" in c or "SIMULATED" in c for c in result.bundle.verdict.caveats)

    def test_host_districts_are_excluded_from_donor_pool(self) -> None:
        case = get_case("kariba-redd")
        for host in ("zw-hurungwe", "zw-binga", "zw-mbire"):
            assert host in case.excluded_donor_ids
        request = _fixture_request()
        result = run_analysis(request, synthetic_fixture_access(request))
        assert result.bundle is not None
        assert float(result.bundle.require("matching.n_candidates_excluded").value) >= 3

    def test_fixture_rejects_unlabelled_data(self, tmp_path, monkeypatch) -> None:
        from groundtruth.platform.datasets import access

        bad = tmp_path / access.SYNTHETIC_FIXTURE_FILENAME
        bad.write_text(
            json.dumps({"dataset_ref": {"provider": "copernicus-usgs"}, "units": {}}),
            encoding="utf-8",
        )
        access._load_kariba_synthetic_fixture.cache_clear()
        monkeypatch.setattr(access, "synthetic_fixture_paths", lambda: [bad])
        try:
            with pytest.raises(DataUnavailableError, match="not labelled SYNTHETIC"):
                access._load_kariba_synthetic_fixture()
        finally:
            access._load_kariba_synthetic_fixture.cache_clear()

    def test_no_fixture_for_other_cases(self) -> None:
        request = get_case("mikoko-pamoja").to_request(data_mode="simulated")
        with pytest.raises(DataUnavailableError, match="No synthetic fixture"):
            synthetic_fixture_access(request)


class TestRealDataPathRefuses:
    def test_no_real_observation_cases(self) -> None:
        assert real_observation_cases() == ()

    @pytest.mark.parametrize("case_id", ["kariba-redd", "mikoko-pamoja"])
    def test_earth_engine_access_never_falls_back(self, case_id: str) -> None:
        request = get_case(case_id).to_request(data_mode="observed")
        with pytest.raises(DataUnavailableError, match="not implemented"):
            earth_engine_access(request)

    def test_observed_request_never_pins_synthetic_dataset(self) -> None:
        request = get_case("kariba-redd").to_request(data_mode="observed")
        assert not any(d.is_synthetic for d in request.datasets)
        assert not any(d.provider == "copernicus-usgs" for d in request.datasets)

    def test_api_refuses_real_kariba(self, client: TestClient) -> None:
        response = client.post("/cases/kariba-redd/verify", json={"synthetic": False})
        assert response.status_code == 501
        assert "not implemented" in response.json()["detail"].lower()

    def test_cli_refuses_real_kariba(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["verify", "kariba-redd"]) == 2
        captured = capsys.readouterr()
        assert "not implemented" in captured.err.lower()
        assert captured.out == ""

    def test_cli_fixture_run_is_bannered_and_labelled(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["verify", "kariba-redd", "--synthetic-fixture"]) == 0
        captured = capsys.readouterr()
        assert "SYNTHETIC FIXTURE RUN" in captured.err
        assert "NOT SATELLITE OBSERVATIONS" in captured.err
        assert "copernicus" not in captured.out.lower()
        assert "Inconclusive" in captured.out

    def test_cli_fixture_refused_for_other_cases(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["verify", "mikoko-pamoja", "--synthetic-fixture"]) == 2


class TestDoctorReportsActualCapabilities:
    def test_doctor_is_honest(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["doctor"]) == 0
        out = capsys.readouterr().out
        assert "earth observation ingestion implemented : no" in out
        assert "real observation data available         : none" in out
        assert "synthetic fixtures available" in out and "SYNTHETIC" in out
        assert "NOT CALIBRATED" in out
        assert "biomass carbon conversion       : no" in out
        # The old optimistic line must not return.
        assert "calibrated for benchmark cases" not in out
        assert "yes (calibrated" not in out


def test_bundle_type_roundtrip() -> None:
    request = _fixture_request()
    result = run_analysis(request, synthetic_fixture_access(request))
    assert result.bundle is not None
    EvidenceBundle.model_validate(result.bundle.model_dump(mode="json"))
