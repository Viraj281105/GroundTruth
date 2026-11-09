"""Case management (#36) and the case's own ``min_donors`` (V8, agreed with Viraj).

Three things must stay true of a case made through the API: it produces a valid
``AnalysisRequest``, it cannot be ``analysed`` without a run reviewed by both owners (C7), and
a bad input is refused with a structured, actionable error instead of a 500. The ``analysed``
guard sits on ``CaseDefinition`` itself, so each path that can produce a case is tested.
"""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from groundtruth.contracts.errors import CaseDefinitionError
from groundtruth.platform.api.app import app
from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.cases import creator
from groundtruth.platform.cases.creator import create_and_register_case
from groundtruth.platform.cases.registry import (
    CASE_STATUSES,
    CaseValidationError,
    get_case,
    list_cases,
    load_all_cases,
    load_case,
)
from groundtruth.platform.config import REPO_ROOT, get_settings

GOOD = {"name": "Probe Project", "country": "Zimbabwe", "registry_id": "VCS 9999", "area_ha": 5000}


@pytest.fixture
def cases_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway copy of ``cases/``, so creating a case never touches the real folder."""
    target = tmp_path / "cases"
    shutil.copytree(REPO_ROOT / "cases", target)
    monkeypatch.setattr(get_settings(), "cases_dir", target)
    # Fixture calibration runs the engine and writes under data/; this suite is about the case.
    monkeypatch.setattr(creator, "_generate_and_store_fixture", lambda case: None)
    monkeypatch.setattr(creator, "_queue_initial_run", lambda case: None)
    return target


@pytest.fixture
def client(cases_dir: Path) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _files(cases_dir: Path) -> set[str]:
    return {p.relative_to(cases_dir).as_posix() for p in cases_dir.rglob("*") if p.is_file()}


def _error(response: Any) -> dict[str, Any]:
    return response.json()["detail"]


def _kariba_yaml_with(tmp_path: Path, **changes: Any) -> Path:
    payload = yaml.safe_load((REPO_ROOT / "cases/kariba-redd.yaml").read_text(encoding="utf-8"))
    payload.update(changes)
    path = tmp_path / "kariba-redd.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


# --- acceptance 1 and 2: a created case is valid, and YAML stays the format ----------------


class TestCreate:
    def test_a_created_case_produces_a_valid_request(self, client, cases_dir):
        response = client.post("/cases", json=GOOD)
        assert response.status_code == 200, response.text
        case_id = response.json()["case_id"]
        assert response.json()["status"] == "scaffolded"

        case = get_case(case_id)
        request = case.to_request()
        assert request.case_id == case_id and request.spec_hash
        assert request.window == case.window
        # A third-party figure must never reach the engine, created case or not.
        assert "known_reference" not in request.model_dump_json()

    def test_the_created_case_is_a_yaml_file_that_loads_back(self, client, cases_dir):
        case_id = client.post("/cases", json=GOOD).json()["case_id"]
        path = cases_dir / f"{case_id}.yaml"
        assert path.is_file()
        assert load_case(path) == get_case(case_id)
        assert case_id in list_cases()
        assert case_id in load_all_cases()  # one more YAML case does not break the rest

    def test_a_second_case_with_the_same_name_gets_a_new_id(self, client, cases_dir):
        first = client.post("/cases", json=GOOD).json()["case_id"]
        second = client.post("/cases", json=GOOD).json()["case_id"]
        assert first != second

    def test_the_repository_cases_are_untouched(self, client, cases_dir):
        before = {c: get_case(c).status for c in list_cases()}
        client.post("/cases", json=GOOD)
        assert {c: get_case(c).status for c in before} == before


# --- acceptance 4: validation errors are structured and actionable -------------------------


class TestValidation:
    def _refused(self, client, cases_dir, body, *, field: str) -> dict[str, Any]:
        before = _files(cases_dir)
        response = client.post("/cases", json=body)
        assert response.status_code == 422, response.text
        error = _error(response)
        assert error["code"] == "invalid_case"
        assert field in error["message"]
        assert error["hint"], "an error that does not say what to do is not actionable"
        assert _files(cases_dir) == before, "a refused case must leave nothing on disk"
        return error

    def test_a_bad_boundary_is_not_a_500(self, client, cases_dir):
        error = self._refused(
            client, cases_dir, {**GOOD, "boundary_geojson": {"type": "Banana"}}, field="boundary"
        )
        assert "Banana" in error["message"]

    def test_a_backwards_window_names_the_fields_and_writes_nothing(self, client, cases_dir):
        self._refused(
            client,
            cases_dir,
            {**GOOD, "pre_start": 2020, "pre_end": 2010},
            field="analysis window",
        )
        assert "broken" not in " ".join(_files(cases_dir))
        assert load_all_cases()  # and the case list still loads

    def test_a_window_too_short_for_the_estimator_cannot_make_a_request(self, client, cases_dir):
        """The window is ordered, but 3 pre-periods is below what the estimator needs."""
        error = self._refused(
            client,
            cases_dir,
            {**GOOD, "pre_start": 2012, "pre_end": 2014, "post_start": 2015, "post_end": 2022},
            field="case",
        )
        assert "pre-treatment" in error["message"]

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"indicator": "vibes"}, "indicator"),
            ({"standard": "Bespoke"}, "standard"),
            ({"crediting_period_start": "next spring"}, "crediting_period"),
            (
                {"crediting_period_start": "2030-01-01", "crediting_period_end": "2020-01-01"},
                "crediting_period_end",
            ),
        ],
    )
    def test_each_bad_field_is_named(self, client, cases_dir, changes, field):
        self._refused(client, cases_dir, {**GOOD, **changes}, field=field)

    @pytest.mark.parametrize("bad_id", ["../evil", "Has Spaces", "UPPER", "a/b", "-x", "x" * 90])
    def test_a_case_id_that_is_not_kebab_case_is_refused(self, client, cases_dir, bad_id):
        """The id becomes a file name, so it must not be able to name a path."""
        self._refused(client, cases_dir, {**GOOD, "case_id": bad_id}, field="case_id")

    def test_a_missing_required_field_is_still_the_standard_422_list(self, client, cases_dir):
        response = client.post("/cases", json={"name": "x"})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)  # FastAPI's own, field-by-field


# --- acceptance 3: status: analysed is rejected without a reviewed run ---------------------


class TestAnalysedIsRefused:
    def test_the_api_refuses_it_and_says_why(self, client, cases_dir):
        before = _files(cases_dir)
        response = client.post("/cases", json={**GOOD, "status": "analysed"})
        assert response.status_code == 422
        error = _error(response)
        assert error["code"] == "case_status_requires_review"
        assert "C7" in error["message"] and "#4" in error["message"]
        assert "Omit status" in error["hint"]
        assert _files(cases_dir) == before

    @pytest.mark.parametrize("status", ["data-wired", "banana", ""])
    def test_no_other_status_can_be_set_either(self, client, cases_dir, status):
        response = client.post("/cases", json={**GOOD, "status": status})
        assert response.status_code == 422
        assert _error(response)["code"] == "invalid_case"

    def test_scaffolded_is_accepted_because_it_is_what_you_get_anyway(self, client, cases_dir):
        response = client.post("/cases", json={**GOOD, "status": "scaffolded"})
        assert response.status_code == 200 and response.json()["status"] == "scaffolded"

    def test_the_creator_function_refuses_it_too(self, cases_dir):
        with pytest.raises(CaseValidationError) as caught:
            create_and_register_case(**{**GOOD, "status": "analysed"})  # type: ignore[arg-type]
        assert caught.value.code == "case_status_requires_review"

    def test_a_yaml_file_cannot_claim_it(self, tmp_path):
        path = _kariba_yaml_with(tmp_path, status="analysed")
        with pytest.raises(CaseValidationError) as caught:
            load_case(path)
        error = caught.value
        assert error.code == "case_status_requires_review"
        assert "kariba-redd.yaml" in str(error), "the message should name the file"
        assert "C7" in str(error) and "#4" in str(error)

    def test_a_case_cannot_be_built_or_changed_into_it_directly(self):
        """The database upsert and project seeding build from a CaseDefinition, so guarding the
        class closes those paths without a separate check on each."""
        with pytest.raises(CaseValidationError):
            dataclasses.replace(get_case("kariba-redd"), status="analysed")

    def test_a_misspelt_status_is_refused_rather_than_quietly_not_analysed(self, tmp_path):
        path = _kariba_yaml_with(tmp_path, status="analyzed")
        with pytest.raises(CaseValidationError) as caught:
            load_case(path)
        assert caught.value.code == "invalid_case"
        assert "spelling" in (caught.value.hint or "")

    @pytest.mark.parametrize("status", ["scaffolded", "data-wired"])
    def test_the_other_statuses_still_load(self, tmp_path, status):
        assert load_case(_kariba_yaml_with(tmp_path, status=status)).status == status

    def test_a_refusal_is_a_case_definition_error_so_existing_handlers_catch_it(self, tmp_path):
        with pytest.raises(CaseDefinitionError):
            load_case(_kariba_yaml_with(tmp_path, status="analysed"))

    def test_the_status_sets_in_code_and_database_agree(self):
        from groundtruth.platform.store.models import CASE_STATUSES as DATABASE_STATUSES

        assert tuple(CASE_STATUSES) == tuple(DATABASE_STATUSES)

    def test_every_error_code_maps_to_a_422(self):
        for code in (
            ApiErrorCode.INVALID_CASE,
            ApiErrorCode.CASE_STATUS_REQUIRES_REVIEW,
            ApiErrorCode.MIN_DONORS_BELOW_CASE_FLOOR,
        ):
            assert API_ERROR_STATUS[code] == 422


# --- min_donors: the case's own floor ------------------------------------------------------


class TestMinDonorsFloor:
    def test_kariba_pins_pool_floor_and_cap(self):
        case = get_case("kariba-redd")
        assert (case.donor_pool_size, case.min_donors, case.max_donors) == (80, 30, 50)

    def test_nothing_requested_means_nothing_overridden(self):
        assert get_case("kariba-redd").resolve_min_donors(None) is None

    @pytest.mark.parametrize("value", [30, 31, 500])
    def test_the_floor_or_more_is_allowed(self, value):
        assert get_case("kariba-redd").resolve_min_donors(value) == value

    @pytest.mark.parametrize("value", [29, 10, 2])
    def test_less_than_the_floor_is_refused_and_says_why(self, value):
        with pytest.raises(CaseValidationError) as caught:
            get_case("kariba-redd").resolve_min_donors(value)
        error = caught.value
        assert error.code == "min_donors_below_case_floor" and error.field == "min_donors"
        assert "30" in error.message and "pre-registered" in error.message
        assert "Omit min_donors" in (error.hint or "")

    def test_a_case_without_its_own_floor_is_unchanged(self):
        case = get_case("southern-cardamom-redd")
        assert case.min_donors is None
        assert case.resolve_min_donors(5) == 5
        assert case.to_request().donors.min_donors == 10  # the contract default, as before

    def test_verify_refuses_a_lower_floor_before_running_anything(self, tenant_world):
        # /verify is project-scoped, so it is driven by a signed-in owner of the case's project.
        client = tenant_world.client("ref")
        response = client.post("/cases/kariba-redd/verify", json={"min_donors": 10})
        assert response.status_code == 422
        assert _error(response)["code"] == "min_donors_below_case_floor"

    def test_verify_with_nothing_requested_runs_the_cases_own_floor(self, tenant_world):
        client = tenant_world.client("ref")
        response = client.post(
            "/cases/kariba-redd/verify", json={"synthetic": True, "include_report": False}
        )
        assert response.status_code == 200, response.text
        expected = get_case("kariba-redd").to_request(
            data_mode="simulated", seed=get_settings().random_seed
        )
        assert response.json()["spec_hash"] == expected.spec_hash

    def test_the_cli_refuses_a_lower_floor_and_defaults_to_the_case(self, capsys):
        from groundtruth.cli import build_parser, main

        parser = build_parser()
        assert parser.parse_args(["verify", "kariba-redd"]).min_donors is None
        assert parser.parse_args(["submit", "kariba-redd"]).min_donors is None

        assert main(["verify", "kariba-redd", "--synthetic", "--min-donors", "10"]) == 1
        err = capsys.readouterr().err
        assert "min_donors=10 is below this case's floor of 30" in err
