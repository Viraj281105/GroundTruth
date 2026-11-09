"""Backend validation and structured error handling (#39).

Every error the API sends, from any router, has one envelope: ``is_refusal`` and ``request_id``
at the top level, the existing ``detail`` shape unchanged, validation errors that name their
field, and nothing in the body that is a stack trace, a file path, SQL or a secret. The tests
cover the middleware on a small app (so each behaviour is pinned exactly) and then sweep the
real application's routes, so a router added later cannot quietly opt out.
"""

from __future__ import annotations

import importlib
import json
import logging
import re
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr

from groundtruth.contracts.result import AnalysisError, ErrorCode
from groundtruth.platform.api.app import ERROR_STATUS, app
from groundtruth.platform.api.error_envelope import (
    ErrorEnvelopeMiddleware,
    redact_secrets,
    scrub_json,
    scrub_text,
)
from groundtruth.platform.api.errors import API_ERROR_STATUS, ApiErrorCode
from groundtruth.platform.api.schemas import RunError
from groundtruth.platform.config import get_settings

LEAK = re.compile(r"[A-Za-z]:\\|/home/|/app/|site-packages|Traceback|\[SQL:|\[parameters:")
SECRET = "sk-test-secret-value-123"


# --- acceptance 1: every error code has a status -------------------------------------------


class TestTotality:
    def test_every_engine_error_code_has_an_http_status(self):
        assert set(ErrorCode) <= set(ERROR_STATUS)
        assert all(400 <= status < 600 for status in ERROR_STATUS.values())

    def test_every_api_error_code_has_an_http_status(self):
        assert set(ApiErrorCode) == set(API_ERROR_STATUS)
        assert all(400 <= status < 600 for status in API_ERROR_STATUS.values())

    def test_a_refusal_is_never_a_server_error(self):
        """A refusal is the system declining to give a fragile number, not a malfunction."""
        for code in ErrorCode:
            if code.is_refusal:
                assert ERROR_STATUS[code] == 422, code

    def test_a_code_shared_by_both_enums_has_one_status(self):
        for code in ApiErrorCode:
            if code.value in {e.value for e in ErrorCode}:
                assert API_ERROR_STATUS[code] == ERROR_STATUS[ErrorCode(code.value)], code


# --- the scrubber: only paths, tracebacks, SQL and secrets ----------------------------------


class TestScrub:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                r"not found at D:\IT\.vscode\GroundTruth\data\processed\climate_cache\kariba.json. Run it.",
                "not found at <path>/kariba.json. Run it.",
            ),
            (r"C:\Program Files\App\x.py failed", "<path>/x.py failed"),
            ("D:/a/b/c.json ok", "<path>/c.json ok"),
            ("cannot open /app/data/x.db: locked", "cannot open <path>/x.db: locked"),
            ("see /home/bob/.ssh/id", "see <path>/id"),
        ],
    )
    def test_absolute_paths_go_and_the_file_name_stays(self, text, expected):
        assert scrub_text(text) == expected

    def test_a_traceback_and_its_frames_go(self):
        text = 'it broke\nTraceback (most recent call last):\n  File "/app/x.py", line 3, in f\n    boom()'
        scrubbed = scrub_text(text)
        assert scrubbed == "it broke\n[traceback removed]"
        assert scrub_text('see File "/a/b.py", line 9, in g') == "see [frame removed]"

    def test_sql_and_its_parameters_go(self):
        text = "boom [SQL: SELECT * FROM users WHERE email=%s]\n[parameters: ('a@b.co',)]"
        assert scrub_text(text) == "boom [SQL removed]"

    def test_credentials_in_a_connection_string_go_and_the_host_stays(self):
        scrubbed = scrub_text("could not connect postgresql+psycopg://user:hunter2pw@db/gt")
        assert scrubbed == "could not connect postgresql+psycopg://<credentials>@db/gt"

    def test_a_bearer_token_and_key_material_go(self):
        assert "abcdef" not in scrub_text("Authorization: Bearer abcdef0123456789abcdef0123")
        pem = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----"
        assert "MIIE" not in scrub_text(f"bad key {pem}")

    def test_a_configured_secret_goes(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr(SECRET))
        assert SECRET not in scrub_text(f"401 for key {SECRET}")
        assert SECRET not in redact_secrets(f"key {SECRET}")

    def test_the_database_password_goes(self, monkeypatch):
        monkeypatch.setattr(
            get_settings(), "database_url", "postgresql://groundtruth:pa55w0rd-long@db/gt"
        )
        assert "pa55w0rd-long" not in scrub_text("auth failed for pa55w0rd-long")

    @pytest.mark.parametrize(
        "text",
        [
            "Set DATABASE_URL and run the migrations.",
            "Widen the donor search region. Do not lower min_donors to force a result.",
            "cases/boundaries/kariba-redd.geojson is missing; python -m apps.worker.main --migrate",
            "see https://sqlalche.me/e/20/e3q8 and http://localhost:3000/cases/x",
            "stage=ingestion code=donor_pool_inadequate /runs/compare",
            "ratio 3:/ and a:b",
        ],
    )
    def test_nothing_else_is_touched(self, text):
        assert scrub_text(text) == text

    def test_what_the_ui_needs_is_never_removed(self):
        """code, stage, remediation and hint reach the UI exactly as written."""
        detail = {
            "code": "donor_pool_inadequate",
            "stage": "matching",
            "message": "too few donors",
            "remediation": "Widen the donor search region.",
            "hint": "Reuse the filters it was issued for.",
            "run_id": "run_0123456789abcdef",
            "is_refusal": True,
        }
        assert scrub_json(detail) == detail

    def test_it_scrubs_inside_nested_structures_and_leaves_keys_alone(self):
        payload = {"detail": [{"loc": ["body", "x"], "msg": r"at C:\a\b.py"}]}
        assert scrub_json(payload) == {"detail": [{"loc": ["body", "x"], "msg": "at <path>/b.py"}]}

    def test_a_stored_engine_error_is_scrubbed_in_a_200_body_too(self):
        error = AnalysisError(
            code=ErrorCode.DATA_UNAVAILABLE,
            message=r"bundle not found at D:\IT\data\climate.json. Run ingestion first.",
            stage="ingestion",
            remediation="Check dataset availability, then retry.",
        )
        view = RunError.from_error(error)
        assert view.message == "bundle not found at <path>/climate.json. Run ingestion first."
        assert (view.code, view.stage, view.remediation) == (
            "data_unavailable",
            "ingestion",
            "Check dataset availability, then retry.",
        )


# --- the middleware, on a small app ---------------------------------------------------------


class Body(BaseModel):
    name: str
    age: int


def make_app() -> FastAPI:
    mini = FastAPI()

    @mini.get("/ok")
    def ok() -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/string-404")
    def string_404() -> None:
        raise HTTPException(404, "Case 'x' not found")

    @mini.get("/dict-409")
    def dict_409() -> None:
        raise HTTPException(
            409,
            {
                "code": "job_already_finished",
                "message": "done",
                "hint": "nothing to cancel",
                "stage": "claim",
                "remediation": "Submit a new job.",
            },
        )

    @mini.get("/refusal")
    def refusal() -> None:
        raise HTTPException(
            422,
            {
                "code": "donor_pool_inadequate",
                "message": "too few donors",
                "stage": "matching",
                "is_refusal": True,
                "remediation": "Widen the donor search region.",
            },
        )

    @mini.get("/leaky")
    def leaky() -> None:
        raise HTTPException(
            503, "missing D:\\x\\y\\data.json [SQL: SELECT 1]\n[parameters: ('private@x.co',)]"
        )

    @mini.post("/body")
    def body(payload: Body) -> dict[str, str]:
        return {"name": payload.name}

    @mini.get("/boom")
    def boom() -> None:
        raise RuntimeError(f"failed with key {SECRET} at C:\\secret\\file.py")

    @mini.get("/stream")
    def stream() -> StreamingResponse:
        return StreamingResponse(iter([b"one,", b"two,", b"three"]), media_type="text/plain")

    mini.add_middleware(ErrorEnvelopeMiddleware)
    mini.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True
    )
    return mini


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app(), raise_server_exceptions=False)


class TestEnvelope:
    @pytest.mark.parametrize("path", ["/string-404", "/dict-409", "/refusal", "/leaky", "/boom"])
    def test_every_error_has_a_request_id_and_is_refusal(self, client, path):
        response = client.get(path)
        body = response.json()
        assert response.status_code >= 400
        assert isinstance(body["is_refusal"], bool)
        assert body["request_id"] == response.headers["x-request-id"]

    def test_a_string_detail_stays_a_string_and_gains_a_code(self, client):
        body = client.get("/string-404").json()
        assert body["detail"] == "Case 'x' not found"
        assert (body["code"], body["is_refusal"]) == ("http_404", False)

    def test_a_dict_detail_keeps_every_key_and_gains_is_refusal(self, client):
        original = {
            "code": "job_already_finished",
            "message": "done",
            "hint": "nothing to cancel",
            "stage": "claim",
            "remediation": "Submit a new job.",
        }
        body = client.get("/dict-409").json()
        assert body["detail"] == {**original, "is_refusal": False}
        assert body["is_refusal"] is False

    def test_a_refusal_says_true_at_the_top_and_inside(self, client):
        body = client.get("/refusal").json()
        assert body["is_refusal"] is True and body["detail"]["is_refusal"] is True
        assert body["detail"]["remediation"] == "Widen the donor search region."
        assert body["detail"]["stage"] == "matching"

    def test_a_validation_error_names_the_field_and_has_the_same_envelope(self, client):
        body = client.post("/body", json={"name": "ok"}).json()
        assert body["code"] == "validation_error"
        assert body["fields"] == ["body.age"]
        assert body["is_refusal"] is False and body["request_id"]
        assert "body.age" in body["message"]
        assert body["detail"][0]["loc"] == ["body", "age"]  # the UI still reads detail[].loc

    def test_a_validation_error_never_echoes_what_was_submitted(self, client):
        response = client.post("/body", json={"name": "ok", "age": "hunter2-secret-value"})
        assert response.status_code == 422
        assert "hunter2-secret-value" not in response.text
        assert all(set(entry) <= {"type", "loc", "msg"} for entry in response.json()["detail"])

    def test_paths_sql_and_parameters_are_scrubbed_but_the_status_and_file_name_stay(self, client):
        response = client.get("/leaky")
        assert response.status_code == 503
        assert "data.json" in response.text
        assert not LEAK.search(response.text) and "private@x.co" not in response.text

    def test_a_good_response_is_untouched_but_still_gets_a_request_id(self, client):
        response = client.get("/ok")
        assert response.json() == {"ok": True}
        assert response.headers["x-request-id"]

    def test_a_streamed_response_passes_through_whole(self, client):
        response = client.get("/stream")
        assert response.text == "one,two,three" and response.headers["x-request-id"]

    def test_a_valid_request_id_from_the_caller_is_kept_and_a_bad_one_is_replaced(self, client):
        kept = client.get("/string-404", headers={"X-Request-ID": "caller-id-12345"})
        assert kept.json()["request_id"] == "caller-id-12345"
        bad = client.get("/string-404", headers={"X-Request-ID": "x\ny"})
        assert bad.json()["request_id"] != "x\ny" and len(bad.json()["request_id"]) >= 8


class TestUnexpectedExceptions:
    def test_the_client_gets_a_generic_json_500_with_the_request_id(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr(SECRET))
        response = client.get("/boom")
        body = response.json()
        assert response.status_code == 500
        assert body["detail"]["code"] == "internal_error"
        assert body["request_id"] in body["detail"]["hint"]
        assert body["is_refusal"] is False
        assert SECRET not in response.text and "secret" not in response.text.lower()
        assert not LEAK.search(response.text)

    def test_the_traceback_is_logged_with_the_request_id_but_not_the_secret(
        self, client, monkeypatch, caplog
    ):
        monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr(SECRET))
        caplog.set_level(logging.ERROR, logger="groundtruth.api.errors")
        response = client.get("/boom")
        logged = caplog.text
        assert "Traceback" in logged and "RuntimeError" in logged
        assert response.json()["request_id"] in logged
        assert "C:\\secret\\file.py" in logged  # a developer needs the real path in the log
        assert SECRET not in logged

    def test_a_500_still_carries_cors_headers(self, client):
        response = client.get("/boom", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


# --- the real application: every router -----------------------------------------------------


def _fill(path: str) -> str:
    values = {"run_id": "run_0000000000000000", "case_id": "nope", "org": "nope", "slug": "nope"}
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), "nope-0000"), path)


SKIP = ("/events", "/auth/logout", "/auth/change-password")
"""A stream that never ends, and two routes that would sign the caller out mid-sweep."""


def _sweep(client: TestClient) -> list[tuple[str, str, int, Any]]:
    seen = []
    for path, operations in app.openapi()["paths"].items():
        if path.endswith(SKIP[0]) or path in SKIP[1:]:
            continue
        for method in operations:
            if method not in {"get", "post", "patch", "put", "delete"}:
                continue
            attempts = [{}] if method == "get" else [{}, {"json": {"zzz": 1, "case_id": 5}}]
            for kwargs in attempts:
                response = client.request(method.upper(), _fill(path), **kwargs)
                if response.status_code >= 400:
                    seen.append((method.upper(), path, response.status_code, response))
    return seen


class TestEveryRouterUsesTheEnvelope:
    @pytest.mark.parametrize("who", ["anon", "ref", "outsider"])
    def test_every_error_from_every_route(self, tenant_world, who):
        client = (
            TestClient(app, raise_server_exceptions=False)
            if who == "anon"
            else tenant_world.client(who)
        )
        seen = _sweep(client)
        assert len({(m, p) for m, p, _, _ in seen}) >= 15, "the sweep reached too few routes"
        for method, path, status, response in seen:
            where = f"{method} {path} -> {status}"
            assert "json" in response.headers["content-type"], where
            body = response.json()
            assert isinstance(body["is_refusal"], bool), where
            assert body["request_id"] == response.headers["x-request-id"], where
            assert not LEAK.search(response.text), f"{where}: {response.text[:200]}"
            if isinstance(body["detail"], list):
                assert body["code"] == "validation_error" and body["fields"], where
                assert all("input" not in entry and "ctx" not in entry for entry in body["detail"])
            elif isinstance(body["detail"], dict):
                assert body["detail"]["is_refusal"] == body["is_refusal"], where
                assert body["detail"].get("code"), where

    def test_a_validation_error_on_a_real_route_never_echoes_the_input(self, tenant_world):
        response = tenant_world.client("ref").post(
            "/cases",
            json={
                "name": "ok name",
                "country": "Zim",
                "registry_id": "VCS 1",
                "area_ha": "hunter2-secret-value",
            },
        )
        assert response.status_code == 422
        assert "hunter2-secret-value" not in response.text
        assert response.json()["fields"] == ["body.area_ha"]

    def test_a_real_engine_refusal_keeps_is_refusal_true_and_everything_the_ui_reads(
        self, tenant_world
    ):
        response = tenant_world.client("ref").post(
            "/cases/kariba-redd/verify", json={"min_donors": 500}
        )
        assert response.status_code == 422
        body = response.json()
        assert body["is_refusal"] is True and body["detail"]["is_refusal"] is True
        assert body["detail"]["code"] == "donor_pool_inadequate"
        assert body["detail"]["stage"] == "matching" and body["detail"]["remediation"]
        assert body["detail"]["run_id"].startswith("run_")

    def test_an_unknown_case_is_a_404_that_says_it_is_not_a_refusal(self, tenant_world):
        body = tenant_world.client("ref").get("/cases/nope").json()
        assert body["is_refusal"] is False and body["code"] == "http_404"

    def test_an_unhandled_exception_on_a_real_route_is_safe_and_has_cors(self, monkeypatch):
        module = importlib.import_module("groundtruth.platform.api.app")
        monkeypatch.setattr(get_settings(), "anthropic_api_key", SecretStr(SECRET))

        def boom() -> None:
            raise RuntimeError(f"reading C:\\secret\\project\\data.json with {SECRET}")

        monkeypatch.setattr(module, "describe_engine", boom)
        response = TestClient(app, raise_server_exceptions=False).get(
            "/health", headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 500
        body = json.loads(response.text)
        assert body["detail"]["code"] == "internal_error" and body["request_id"]
        assert SECRET not in response.text and "secret" not in response.text.lower()
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_the_csrf_rejection_has_the_same_envelope(self, tenant_world):
        """The CSRF guard answers before any route runs; the envelope still reaches it."""
        client = tenant_world.client("ref")
        response = client.post("/cases", json={}, headers={"Origin": "http://evil.example"})
        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["code"] == "csrf_origin_rejected"
        assert body["is_refusal"] is False and body["request_id"]
