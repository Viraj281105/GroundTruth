"""The OpenAPI schema the frontend's types are generated from (issue #17).

The served ``/openapi.json`` and the committed snapshot are one source of truth. If a
schema or route changes and the snapshot is not regenerated, the first test here fails,
which is how "a schema change without regeneration fails the build" holds on the Python
side. The Node side (``npm run check:api-types``) then checks the TypeScript against the
snapshot.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from groundtruth.contracts.types import VerdictLabel
from groundtruth.platform.api.app import app
from groundtruth.platform.api.openapi_schema import (
    FRAMEWORK_SCHEMAS,
    _refs,
    request_schema_names,
    require_response_fields,
    snapshot_text,
)
from groundtruth.platform.api.schemas import (
    EngineFailureBody,
    MessageErrorBody,
    VerificationResponse,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "apps" / "web" / "src" / "lib" / "generated" / "openapi.json"
REGENERATE = "The API schema changed: run `make api-types` and commit the result."


def _raw() -> dict[str, Any]:
    """What FastAPI generates before our one adjustment."""
    return get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )


@pytest.fixture(scope="module")
def served() -> dict[str, Any]:
    return TestClient(app).get("/openapi.json").json()


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


class TestOneSourceOfTruth:
    def test_the_committed_snapshot_is_current(self, snapshot):
        assert snapshot == app.openapi(), REGENERATE

    def test_the_served_schema_is_the_snapshot(self, served, snapshot):
        assert served == snapshot, REGENERATE

    def test_the_schema_is_built_once_and_kept(self):
        assert app.openapi() is app.openapi()

    def test_the_snapshot_is_written_with_lf_and_one_trailing_newline(self):
        text = snapshot_text(app.openapi())
        assert text.endswith("}\n") and "\r" not in text


class TestTheOneAdjustment:
    """Response-only schemas are fully required; nothing else is touched."""

    def test_every_response_only_schema_lists_every_property_as_required(self, served):
        schemas = served["components"]["schemas"]
        untouched = request_schema_names(served) | FRAMEWORK_SCHEMAS
        checked = 0
        for name, schema in schemas.items():
            if name in untouched or not schema.get("properties"):
                continue
            assert schema["required"] == list(schema["properties"]), name
            checked += 1
        assert checked > 30

    def test_request_schemas_are_exactly_as_fastapi_wrote_them(self, served):
        raw = _raw()["components"]["schemas"]
        names = request_schema_names(served)
        assert {"VerificationRequest", "SubmitJobRequest"} <= names
        for name in names:
            assert served["components"]["schemas"][name] == raw[name], name
        # a default there really does mean "you may leave this out"
        assert "required" not in served["components"]["schemas"]["VerificationRequest"]
        assert served["components"]["schemas"]["SubmitJobRequest"]["required"] == ["case_id"]

    def test_fastapis_own_validation_schemas_are_untouched(self, served):
        raw = _raw()["components"]["schemas"]
        for name in FRAMEWORK_SCHEMAS:
            assert served["components"]["schemas"][name] == raw[name], name
        assert "ctx" not in served["components"]["schemas"]["ValidationError"]["required"]

    def test_fields_with_defaults_in_responses_are_required(self, served):
        """The case that motivated the adjustment: these are always sent."""
        schemas = served["components"]["schemas"]
        assert "qualifiers" in schemas["Evidence"]["required"]
        assert "parameters" in schemas["Provenance"]["required"]
        assert "engine_capabilities" in schemas["HealthResponse"]["required"]

    def test_the_adjustment_follows_references_into_request_schemas(self):
        spec = {
            "paths": {
                "/x": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"$ref": "#/components/schemas/In"}}
                            }
                        },
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Out"}
                                    }
                                }
                            }
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "In": {"properties": {"nested": {"$ref": "#/components/schemas/Shared"}}},
                    "Shared": {"properties": {"a": {}, "b": {}}, "required": ["a"]},
                    "Out": {"properties": {"x": {}, "y": {}}, "required": ["x"]},
                }
            },
        }
        adjusted = require_response_fields(spec)
        schemas = adjusted["components"]["schemas"]
        assert schemas["Out"]["required"] == ["x", "y"]
        assert schemas["Shared"]["required"] == ["a"]  # reached from a request: left alone
        assert "required" not in schemas["In"]
        assert spec["components"]["schemas"]["Out"]["required"] == ["x"]  # input not mutated

    def test_the_adjustment_is_idempotent(self, served):
        assert require_response_fields(served) == served


class TestTheSchemaGeneratesGoodTypes:
    def test_every_success_response_is_typed(self, served):
        untyped = [
            f"{method.upper()} {path} {code}"
            for path, operations in served["paths"].items()
            for method, operation in operations.items()
            for code, response in operation["responses"].items()
            if code.startswith("2")
            and not any(m.get("schema") for m in response.get("content", {}).values())
        ]
        assert not untyped, untyped

    def test_every_reference_resolves(self, served):
        assert _refs(served) <= set(served["components"]["schemas"])

    def test_schema_names_are_plain(self, served):
        """FastAPI qualifies a name with its module when two models collide; none do."""
        assert not [n for n in served["components"]["schemas"] if "__" in n or "-" in n]


class TestDocumentedErrorsMatchWhatIsSent:
    def _body_schema(self, served, path, method, code):
        return served["paths"][path][method]["responses"][code]["content"]["application/json"][
            "schema"
        ]

    def test_verify_documents_both_meanings_of_422(self, served):
        schema = self._body_schema(served, "/cases/{case_id}/verify", "post", "422")
        assert schema == {
            "anyOf": [
                {"$ref": "#/components/schemas/HTTPValidationError"},
                {"$ref": "#/components/schemas/EngineFailureBody"},
            ]
        }

    def test_verify_documents_both_meanings_of_501(self, served):
        schema = self._body_schema(served, "/cases/{case_id}/verify", "post", "501")
        assert {r["$ref"].rsplit("/", 1)[-1] for r in schema["anyOf"]} == {
            "MessageErrorBody",
            "EngineFailureBody",
        }

    def test_unknown_case_404s_are_documented(self, served):
        for path, method in (("/cases/{case_id}", "get"), ("/cases/{case_id}/verify", "post")):
            schema = self._body_schema(served, path, method, "404")
            assert schema == {"$ref": "#/components/schemas/MessageErrorBody"}

    def test_an_unknown_case_sends_the_documented_body(self):
        client = TestClient(app)
        for response in (
            client.get("/cases/no-such-case"),
            client.post("/cases/no-such-case/verify", json={"synthetic": True}),
        ):
            assert response.status_code == 404
            MessageErrorBody.model_validate(response.json())

    def test_observed_data_sends_the_documented_501_body(self):
        response = TestClient(app).post("/cases/kariba-redd/verify", json={"synthetic": False})
        assert response.status_code == 501
        MessageErrorBody.model_validate(response.json())

    def test_a_bad_body_sends_a_validation_error(self):
        response = TestClient(app).post("/cases/kariba-redd/verify", json={"min_donors": 1})
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)  # FastAPI's validation shape

    def test_a_refusal_sends_the_documented_engine_failure_body(self):
        """A real engine refusal, through the real endpoint (SIMULATED DATA)."""
        response = TestClient(app).post(
            "/cases/kariba-redd/verify", json={"synthetic": True, "min_donors": 500}
        )
        assert response.status_code == 422
        body = EngineFailureBody.model_validate(response.json())
        assert body.detail.is_refusal is True and body.detail.code.value == "donor_pool_inadequate"


class TestNarrowedVerifyFields:
    def test_the_schema_narrows_verdict_label_and_data_mode(self, served):
        props = served["components"]["schemas"]["VerificationResponse"]["properties"]
        assert props["verdict_label"] == {"$ref": "#/components/schemas/VerdictLabel"}
        assert props["data_mode"]["enum"] == ["simulated", "observed"]

    def test_the_json_sent_is_unchanged(self):
        """Still the plain strings the UI already reads."""
        response = TestClient(app).post("/cases/kariba-redd/verify", json={"synthetic": True})
        body = response.json()
        assert body["verdict_label"] in {label.value for label in VerdictLabel}
        assert isinstance(body["verdict_label"], str) and body["data_mode"] == "simulated"
        VerificationResponse.model_validate(body)
