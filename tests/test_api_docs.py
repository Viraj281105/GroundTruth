"""The API documentation (#41): complete, and its examples are real.

* Every operation has a written summary and a description; every parameter, field and schema is
  described (FastAPI's own validation schemas excepted: the guide documents them).
* Every error code the API can send is in the guide's table with its HTTP status and whether it
  is a refusal.
* Every worked example in ``docs/api/README.md`` is what the API actually answers: they are
  produced here by calling the application on simulated data, never typed by hand. Values that
  differ on every run (ids, timestamps, durations) are replaced by named placeholders, long lists
  are cut with a note, and numbers are compared with a small tolerance, so the same guide holds on
  every platform CI runs.

To refresh the examples after an intended change::

    UPDATE_API_DOCS=1 pytest tests/test_api_docs.py
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from groundtruth.contracts.result import ErrorCode
from groundtruth.platform.api.app import ERROR_STATUS, app
from groundtruth.platform.api.errors import API_ERROR_STATUS
from groundtruth.platform.api.openapi_schema import FRAMEWORK_SCHEMAS
from groundtruth.platform.auth.service import _CODE_STATUS as AUTH_CODE_STATUS
from groundtruth.platform.config import REPO_ROOT, get_settings
from groundtruth.platform.jobs.queue import JobQueue
from groundtruth.platform.jobs.worker import Worker

GUIDE = REPO_ROOT / "docs" / "api" / "README.md"
ORIGIN = "http://localhost:3000"
"""The web app's origin: the one the test world allows, as a deployment allows its own."""
UPDATE = os.environ.get("UPDATE_API_DOCS") == "1"

# --- 1. the schema is fully described ----------------------------------------------------------


def _routes() -> list[APIRoute]:
    def walk(routes: Any) -> Any:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from walk(inner.routes)
            elif isinstance(route, APIRoute):
                yield route

    return list(walk(app.routes))


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return app.openapi()


def _operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [(m.upper(), p, op) for p, item in spec["paths"].items() for m, op in item.items()]


class TestEverythingIsDescribed:
    def test_every_operation_has_a_written_summary_and_a_description(self, spec):
        auto = {
            (sorted(r.methods)[0], r.path)
            for r in _routes()
            if not r.summary  # FastAPI would title-case the function name
        }
        lacking = []
        for method, path, op in _operations(spec):
            generated = (method, path) in auto and op.get("summary") == op.get(
                "operationId", ""
            ).split("_")[0].title()
            if not op.get("summary") or not op.get("description") or generated:
                lacking.append(f"{method} {path}")
        assert lacking == []

    def test_every_parameter_is_described(self, spec):
        lacking = [
            f"{m} {p} {q['name']}"
            for m, p, op in _operations(spec)
            for q in op.get("parameters", [])
            if not q.get("description")
        ]
        assert lacking == []

    def test_every_schema_and_field_is_described(self, spec):
        lacking = []
        for name, schema in spec["components"]["schemas"].items():
            if name in FRAMEWORK_SCHEMAS:
                continue
            if not schema.get("description"):
                lacking.append(name)
            lacking += [
                f"{name}.{field}"
                for field, prop in (schema.get("properties") or {}).items()
                if not prop.get("description")
            ]
        assert lacking == []

    def test_every_error_response_is_documented(self, spec):
        """Every operation that can fail says so (the health check is the one that cannot)."""
        bare = [
            f"{m} {p}"
            for m, p, op in _operations(spec)
            if not any(c[0] in "45" for c in op.get("responses", {}))
        ]
        assert bare == ["GET /health"]

    def test_the_exports_are_in_the_schema(self, spec):
        assert {"/cases/{case_id}/export/csv", "/cases/{case_id}/export/pdf"} <= set(spec["paths"])
        pdf = spec["paths"]["/cases/{case_id}/export/pdf"]["get"]
        assert "application/pdf" in pdf["responses"]["200"]["content"]
        assert {"422", "500", "502"} <= set(pdf["responses"])


# --- 2. every error code is in the guide's table -------------------------------------------------


def _expected_codes() -> dict[str, set[int]]:
    codes: dict[str, set[int]] = {}
    for code in ErrorCode:
        codes.setdefault(code.value, set()).add(ERROR_STATUS[code])
    for code, status in API_ERROR_STATUS.items():
        codes.setdefault(code.value, set()).add(status)
    for code, status in AUTH_CODE_STATUS.items():
        codes.setdefault(code, set()).add(status)
    codes["validation_error"] = {422}
    codes["internal_error"] = codes.get("internal_error", set()) | {500}
    return codes


REFUSALS = {code.value for code in ErrorCode if code.is_refusal}


def _code_table() -> dict[str, tuple[set[int], str]]:
    rows: dict[str, tuple[set[int], str]] = {}
    for line in GUIDE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| `([a-z_<>0-9]+)` \| ([^|]+) \| (yes|no) \|", line)
        if match:
            statuses = {int(s) for s in re.findall(r"\b([1-5]\d\d)\b", match.group(2))}
            rows[match.group(1)] = (statuses, match.group(3))
    return rows


class TestEveryErrorCodeIsInTheGuide:
    def test_every_code_with_every_status_it_can_have(self):
        table = _code_table()
        missing = {c for c in _expected_codes() if c not in table}
        assert missing == set()
        wrong = {
            c: (table[c][0], statuses)
            for c, statuses in _expected_codes().items()
            if not statuses <= table[c][0]
        }
        assert wrong == {}

    def test_refusals_are_marked_and_nothing_else_is(self):
        table = _code_table()
        assert {c for c, (_, refusal) in table.items() if refusal == "yes"} == REFUSALS

    def test_the_generic_codes_are_explained(self):
        assert "http_<status>" in _code_table()


# --- 3. the worked examples are real -------------------------------------------------------------

RUN_ID = re.compile(r"run_[0-9a-f]{16}")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
VOLATILE_NUMBERS = {"duration_ms", "elapsed_ms", "total_ms", "attempt_elapsed_ms"}
KEEP_HEADERS = (
    "content-type",
    "retry-after",
    "content-disposition",
    "x-groundtruth-data-mode",
    "x-groundtruth-report-generator",
    "set-cookie",
)
MAX_LIST = 4
MAX_TEXT = 600


class Normaliser:
    """Replace what changes on every run with named placeholders; cut what is too long."""

    def __init__(self) -> None:
        self.runs: dict[str, str] = {}

    def text(self, value: str) -> str:
        value = RUN_ID.sub(self._run, value)
        value = UUID.sub("<uuid>", value)
        value = TIMESTAMP.sub("<timestamp>", value)
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + " … (cut in this guide)"

    def _run(self, match: re.Match[str]) -> str:
        return self.runs.setdefault(match.group(0), f"<run_id_{len(self.runs) + 1}>")

    def value(self, value: Any, key: str = "") -> Any:
        if key == "request_id" and value is not None:
            return "<request_id>"
        if key in VOLATILE_NUMBERS and isinstance(value, int | float):
            return "<ms>"
        if key == "stage_durations_ms" and isinstance(value, dict):
            return dict.fromkeys(value, "<ms>")
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: self.value(v, k) for k, v in value.items()}
        if isinstance(value, list):
            items = [self.value(v) for v in value]
            if len(items) > MAX_LIST:
                cut = len(items) - 2
                return [*items[:2], f"… {cut} more (cut in this guide)"]
            return items
        return value

    def header(self, name: str, value: str) -> str:
        if name == "retry-after":
            return "<seconds>"
        if name == "set-cookie":
            return re.sub(r"gt_session=[^;]+", "gt_session=<token>", value)
        return self.text(value)


def _example(
    norm: Normaliser,
    response: Any,
    *,
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
    text_lines: int | None = None,
) -> dict[str, Any]:
    shown = {k: norm.header(k, v) for k, v in response.headers.items() if k in KEEP_HEADERS}
    if "x-request-id" in response.headers:
        shown["x-request-id"] = "<request_id>"
    if text_lines is not None:
        payload: Any = "\n".join(response.text.splitlines()[:text_lines])
    else:
        payload = norm.value(response.json()) if response.content else None
    return {
        "request": {
            "method": method,
            "path": norm.text(path),
            "headers": headers or {},
            "body": body,
        },
        "status": response.status_code,
        "headers": dict(sorted(shown.items())),
        "body": payload,
    }


def _run_worker(world: Any) -> None:
    Worker(JobQueue(world.sessions), poll_interval=0.01).run(exit_when_idle=True, max_jobs=1)


def build_examples(world: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """Every worked example in the guide, made by calling the app. The order is the guide's."""
    norm = Normaliser()
    ex: dict[str, dict[str, Any]] = {}
    json_origin = {"Content-Type": "application/json", "Origin": ORIGIN}

    # sign in: a new account, then its first sign-in
    anon = TestClient(app, raise_server_exceptions=False)
    account = {"email": "analyst@example.org", "password": "correct horse battery"}
    anon.post("/auth/register", json=account, headers={"Origin": ORIGIN})
    ex["sign-in"] = _example(
        norm,
        anon.post("/auth/login", json=account, headers={"Origin": ORIGIN}),
        method="POST",
        path="/auth/login",
        body=account,
        headers=json_origin,
    )
    ex["unauthenticated"] = _example(norm, TestClient(app).get("/runs"), method="GET", path="/runs")

    client = world.client("ref")
    submit = {"case_id": "kariba-redd", "synthetic": True}
    accepted = client.post("/jobs", json=submit)
    ex["submit-job"] = _example(
        norm, accepted, method="POST", path="/jobs", body=submit, headers=json_origin
    )
    run_id = accepted.json()["run_id"]
    ex["poll-queued"] = _example(
        norm, client.get(f"/jobs/{run_id}"), method="GET", path=f"/jobs/{run_id}"
    )
    _run_worker(world)
    ex["poll-finished"] = _example(
        norm, client.get(f"/jobs/{run_id}"), method="GET", path=f"/jobs/{run_id}"
    )
    ex["completed-run"] = _example(
        norm, client.get(f"/runs/{run_id}"), method="GET", path=f"/runs/{run_id}"
    )

    refuse = {"case_id": "kariba-redd", "synthetic": True, "min_donors": 500}
    refused_id = client.post("/jobs", json=refuse).json()["run_id"]
    _run_worker(world)
    ex["refused-run"] = _example(
        norm,
        client.get(f"/runs/{refused_id}?include_bundle=false"),
        method="GET",
        path=f"/runs/{refused_id}?include_bundle=false",
    )
    ex["verify-refusal"] = _example(
        norm,
        client.post("/cases/kariba-redd/verify", json={"min_donors": 500}),
        method="POST",
        path="/cases/kariba-redd/verify",
        body={"min_donors": 500},
        headers=json_origin,
    )

    other = {"case_id": "kariba-redd", "synthetic": True, "min_donors": 40}
    other_id = client.post("/jobs", json=other).json()["run_id"]
    _run_worker(world)
    compare = f"/runs/compare?baseline={run_id}&candidate={other_id}"
    ex["compare"] = _example(norm, client.get(compare), method="GET", path=compare)
    cannot = f"/runs/compare?baseline={run_id}&candidate={refused_id}"
    ex["compare-not-comparable"] = _example(norm, client.get(cannot), method="GET", path=cannot)

    bad = {"case_id": "kariba-redd", "min_donors": "lots"}
    ex["validation-error"] = _example(
        norm,
        client.post("/jobs", json=bad),
        method="POST",
        path="/jobs",
        body=bad,
        headers=json_origin,
    )
    observed = {"case_id": "kariba-redd", "synthetic": False}
    ex["observed-not-implemented"] = _example(
        norm,
        client.post("/jobs", json=observed),
        method="POST",
        path="/jobs",
        body=observed,
        headers=json_origin,
    )
    ex["csrf-rejected"] = _example(
        norm,
        client.post("/jobs", json=submit, headers={"Origin": "https://elsewhere.example"}),
        method="POST",
        path="/jobs",
        body=submit,
        headers={"Content-Type": "application/json", "Origin": "https://elsewhere.example"},
    )
    ex["csv-export"] = _example(
        norm,
        client.get("/cases/kariba-redd/export/csv"),
        method="GET",
        path="/cases/kariba-redd/export/csv",
        text_lines=12,
    )
    # The budget, set to 1 here so the example needs two submissions: the first is accepted
    # (a stored result answers it), the second is over the limit.
    monkeypatch.setattr(get_settings(), "analysis_rate_limit", 1)
    client.post("/jobs", json=submit)
    ex["rate-limited"] = _example(
        norm,
        client.post("/jobs", json=submit),
        method="POST",
        path="/jobs",
        body=submit,
        headers=json_origin,
    )
    return ex


def render(example: dict[str, Any]) -> str:
    request = example["request"]
    lines = ["```http", f"{request['method']} {request['path']}"]
    lines += [f"{k}: {v}" for k, v in request["headers"].items()]
    if request["body"] is not None:
        lines += ["", json.dumps(request["body"], indent=2)]
    lines += ["```", "", f"Response `{example['status']}`"]
    if example["headers"]:
        lines += ["", "```http"]
        lines += [f"{k}: {v}" for k, v in example["headers"].items()]
        lines += ["```"]
    body = example["body"]
    if isinstance(body, str):
        lines += ["", "```text", body, "```"]
    elif body is not None:
        lines += ["", "```json", json.dumps(body, indent=2, ensure_ascii=False), "```"]
    return "\n".join(lines)


def _blocks(text: str) -> dict[str, str]:
    pattern = re.compile(r"<!-- example:([a-z-]+) -->\n(.*?)\n<!-- /example:\1 -->", re.S)
    return {m.group(1): m.group(2) for m in pattern.finditer(text)}


def _close(a: Any, b: Any) -> bool:
    """Equal, with floats compared to a relative 1e-6: platforms may differ in the last digit."""
    if isinstance(a, float) or isinstance(b, float):
        return (
            isinstance(a, int | float)
            and isinstance(b, int | float)
            and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-12)
        )
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)


def _split(block: str) -> tuple[str, Any]:
    """The block's text with its JSON body removed, and the parsed JSON body."""
    match = re.search(r"```json\n(.*?)\n```", block, re.S)
    if match is None:
        return block, None
    return block.replace(match.group(0), "```json```"), json.loads(match.group(1))


def test_every_worked_example_is_what_the_api_answers(tenant_world, monkeypatch):
    examples = build_examples(tenant_world, monkeypatch)
    text = GUIDE.read_text(encoding="utf-8")
    present = _blocks(text)
    if UPDATE:
        for name, example in examples.items():
            marker = re.compile(
                rf"(<!-- example:{name} -->\n).*?(\n<!-- /example:{name} -->)", re.S
            )
            assert marker.search(text), f"the guide has no place for example {name!r}"
            text = marker.sub(lambda m, e=example: m.group(1) + render(e) + m.group(2), text)
        GUIDE.write_text(text, encoding="utf-8", newline="\n")
        present = _blocks(text)
    assert set(present) == set(examples), "the guide's example markers and the examples differ"
    stale = []
    for name, example in examples.items():
        want_text, want_body = _split(render(example))
        have_text, have_body = _split(present[name])
        if want_text != have_text or not _close(want_body, have_body):
            stale.append(name)
    assert stale == [], f"out of date: {stale}. Run UPDATE_API_DOCS=1 pytest {Path(__file__).name}"


def test_the_examples_include_a_completed_run_a_refusal_a_validation_error_and_a_429():
    blocks = _blocks(GUIDE.read_text(encoding="utf-8"))
    assert '"result_state": "measured"' in blocks["completed-run"]
    assert '"is_refusal": true' in blocks["verify-refusal"]
    assert '"result_state": "refused"' in blocks["refused-run"]
    assert '"code": "validation_error"' in blocks["validation-error"]
    assert "Response `429`" in blocks["rate-limited"]
    assert "retry-after: <seconds>" in blocks["rate-limited"]
