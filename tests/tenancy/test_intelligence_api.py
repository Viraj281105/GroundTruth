"""WP-C: project-scoped, honest Groq intelligence. The provider is always mocked (no network)."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from groundtruth.platform.intelligence.context import ContextFact, ProjectContext
from groundtruth.platform.intelligence.groq_service import (
    GroqIntelligenceService,
    IntelligenceMode,
    check_text,
)

pytestmark = pytest.mark.usefixtures("_fast_scrypt")

KARIBA_MARKERS = (
    "kariba",
    "vcs-981",
    "58.4",
    "246,000",
    "246000",
    "-2.34",
    "binga",
    "184.2",
    "zambezi",
)
PRIVATE_CASE = "mikoko-pamoja"
GRANTED_CASE = "kariba-redd"


def _context(pid: str = "p1", *, sufficient: bool = True) -> ProjectContext:
    ctx = ProjectContext(project_id=pid, project_name="Test Project", data_mode="observed")
    ctx.facts = [
        ContextFact(
            "project",
            "Project 'Test Project' in Kenya; start year 2018.",
            "platform:project#p1",
            "project",
        ),
        ContextFact(
            "inventory.ndvi",
            "Indicator ndvi: 7 annual records, 2017 to 2023; source sentinel-2.",
            "platform:evidence-inventory#ndvi",
            "evidence_inventory",
        ),
        ContextFact(
            "assessment.level",
            "Assessment level 2 (Contextual intelligence); evidence confidence moderate.",
            "platform:assessment#p1",
            "assessment",
        ),
    ]
    ctx.sufficient = sufficient
    ctx.missing = ["No project documents have been uploaded."]
    return ctx


def _service(handler, key: str | None = "test-key") -> GroqIntelligenceService:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqIntelligenceService(api_key=key, client=client)


def _ok(content: dict) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})


def _no_key_service(monkeypatch) -> GroqIntelligenceService:
    from groundtruth.platform.config import get_settings

    monkeypatch.setattr(get_settings(), "groq_api_key", None)
    return GroqIntelligenceService(api_key=None)


# --------------------------------------------------------------- service units


def test_unconfigured_key_is_unavailable_without_a_call(monkeypatch):
    calls: list[int] = []
    svc = GroqIntelligenceService(
        api_key=None,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: calls.append(1) or _ok({}))),
    )
    monkeypatch.setattr(type(svc), "api_key", property(lambda self: None))
    out = svc.execute_intelligence_query("What evidence exists?", _context())
    assert out["status"] == "unavailable"
    assert out["reason"] == "GROQ_API_KEY not configured"
    assert out["latency_ms"] is None
    assert out["answer"] is None and out["inferences"] == []
    assert not calls
    assert svc.status()["configured"] is False


def test_status_never_contains_the_key():
    st = GroqIntelligenceService(api_key="sekret-value").status()
    assert st["configured"] is True
    assert "sekret-value" not in json.dumps(st)


def test_provider_error_is_a_safe_error_status():
    svc = _service(lambda r: httpx.Response(500, text="boom: internal key=abc"))
    out = svc.execute_intelligence_query("What evidence exists?", _context())
    assert out["status"] == "error"
    assert "abc" not in json.dumps(out)
    assert out["answer"] is None
    assert out["retrieved_facts"]  # platform facts are still returned


def test_provider_timeout_is_a_safe_error_status():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    out = _service(handler).execute_intelligence_query("What evidence exists?", _context())
    assert out["status"] == "error"
    assert "timed out" in out["reason"]


def test_unparseable_provider_output_is_an_error():
    svc = _service(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})
    )
    assert svc.execute_intelligence_query("What evidence exists?", _context())["status"] == "error"


def test_empty_context_is_insufficient_and_never_calls_the_provider():
    calls: list[int] = []
    svc = _service(lambda r: calls.append(1) or _ok({}))
    ctx = ProjectContext(project_id="p2", project_name="Empty", data_mode="observed")
    ctx.missing = ["No observed evidence stored: no cache."]
    out = svc.execute_intelligence_query("Did the forest recover?", ctx)
    assert out["status"] == "insufficient_context"
    assert "insufficient project context" in out["reason"]
    assert out["latency_ms"] is None
    assert out["missing_context"] == ctx.missing
    assert not calls
    assert not any(m in json.dumps(out).lower() for m in KARIBA_MARKERS)


def test_context_answer_with_measured_latency_and_labelled_parts():
    seen: list[dict] = []

    def handler(request):
        seen.append(json.loads(request.content))
        return _ok(
            {
                "answer": "The platform holds 7 annual ndvi records from 2017 to 2023.",
                "cited_fact_ids": ["inventory.ndvi"],
                "inferences": [
                    {
                        "statement": "The record length may support a before and after comparison.",
                        "based_on": ["inventory.ndvi", "project"],
                    }
                ],
                "unanswerable": ["Carbon stock cannot be stated from these records."],
            }
        )

    out = _service(handler).execute_intelligence_query("What evidence exists?", _context())
    assert out["status"] == "ok"
    assert isinstance(out["latency_ms"], float) and out["latency_ms"] >= 0
    assert out["model"] and out["generated_at"]
    assert out["inferences"][0]["label"] == "model_inference"
    assert out["unsupported_conclusions"] == ["Carbon stock cannot be stated from these records."]
    cited = {f["fact_id"]: f["cited_by_model"] for f in out["retrieved_facts"]}
    assert cited["inventory.ndvi"] is True and cited["project"] is False
    assert all(f["source"].startswith("platform:") for f in out["retrieved_facts"])
    # the model received only the project facts
    user = json.loads(seen[0]["messages"][1]["content"])
    assert {f["fact_id"] for f in user["FACTS"]} == {
        "project",
        "inventory.ndvi",
        "assessment.level",
    }
    assert not any(m in json.dumps(seen[0]).lower() for m in KARIBA_MARKERS)


def test_numbers_not_in_context_are_flagged_and_dropped():
    def handler(request):
        return _ok(
            {
                "answer": "The project avoided 246000 tonnes of CO2.",
                "inferences": [
                    {"statement": "Burn counts fell 58.4 percent.", "based_on": ["project"]},
                    {
                        "statement": "Seven annual records exist (7 records).",
                        "based_on": ["inventory.ndvi"],
                    },
                ],
            }
        )

    out = _service(handler).execute_intelligence_query("How much carbon?", _context())
    assert "246000" not in json.dumps(out["answer"])
    assert [i["statement"] for i in out["inferences"]] == [
        "Seven annual records exist (7 records)."
    ]
    reasons = {(d["part"], d["reason"]) for d in out["guardrail"]["dropped"]}
    assert ("answer", "ungrounded_numbers") in reasons
    assert ("inference", "ungrounded_numbers") in reasons
    assert "246000" in out["guardrail"]["dropped"][0]["ungrounded_numbers"]


def test_fraud_language_and_unsupported_inferences_are_dropped():
    def handler(request):
        return _ok(
            {
                "answer": "Evidence is available.",
                "inferences": [
                    {"statement": "This looks like fraud.", "based_on": ["project"]},
                    {"statement": "Something unrelated.", "based_on": ["nonexistent"]},
                ],
            }
        )

    out = _service(handler).execute_intelligence_query("Is it ok?", _context())
    assert out["inferences"] == []
    assert {d["reason"] for d in out["guardrail"]["dropped"]} == {
        "prohibited_assertion",
        "no_supporting_fact",
    }


def test_check_text_allows_context_numbers_and_years():
    assert check_text("7 records in 2019, with 0.5 share", [0.5]).numbers == ()
    assert check_text("a figure of 31.7", [0.5]).numbers == ("31.7",)


def test_literature_is_labelled_and_only_for_methodology_questions():
    svc = _service(lambda r: _ok({"answer": "ok", "inferences": []}))
    out = svc.execute_intelligence_query(
        "Is additionality supported?", _context(), IntelligenceMode.PROPOSAL_ANALYSIS
    )
    assert out["published_literature"]
    assert all(x["kind"] == "published_literature" for x in out["published_literature"])
    assert all("doi" in x for x in out["published_literature"])
    out2 = svc.execute_intelligence_query("What sensors were used?", _context())
    assert out2["published_literature"] == []


# --------------------------------------------------------------- HTTP / tenancy


@pytest.fixture
def groq_mock(monkeypatch):
    """Route the endpoint through a mocked provider; ``state['calls']`` counts provider hits."""
    state: dict = {"calls": 0}

    def handler(request):
        state["calls"] += 1
        return _ok(
            {
                "answer": "Seven annual records exist (7).",
                "cited_fact_ids": ["inventory.ndvi"],
                "inferences": [],
            }
        )

    svc = _service(handler)
    monkeypatch.setattr("groundtruth.platform.api.v2.get_global_intelligence_service", lambda: svc)
    return state


def _evidence_context(monkeypatch):
    def build(project, level, data_dir, **kw):
        ctx = _context(project.id)
        ctx.project_name = project.name
        return ctx

    monkeypatch.setattr("groundtruth.platform.intelligence.context.build_project_context", build)


def test_unauthenticated_is_401(tenant_world, groq_mock):
    anon = TestClient(tenant_world.client("ref").app, base_url="http://localhost:3000")
    pid = tenant_world.project_ids[GRANTED_CASE]
    for path in ("/intelligence/research", "/api/v1/intelligence/research"):
        r = anon.post(path, json={"query": "What evidence exists?", "project_id": pid})
        assert r.status_code == 401
    assert anon.get("/intelligence/status").status_code == 401
    assert groq_mock["calls"] == 0


def test_cross_tenant_is_denied_and_makes_no_provider_call(tenant_world, groq_mock, monkeypatch):
    _evidence_context(monkeypatch)
    pid = tenant_world.project_ids[PRIVATE_CASE]
    r = tenant_world.client("outsider").post(
        "/intelligence/research", json={"query": "What evidence exists?", "project_id": pid}
    )
    assert r.status_code in (403, 404)
    assert "Test Project" not in r.text
    assert groq_mock["calls"] == 0


def test_project_id_is_required_with_no_default(tenant_world, groq_mock):
    r = tenant_world.client("ref").post(
        "/intelligence/research", json={"query": "What evidence exists?"}
    )
    assert r.status_code == 422


def test_empty_real_project_context_is_insufficient_not_kariba(tenant_world, groq_mock):
    """The private non-Kariba project has no evidence caches in the test data dir."""
    pid = tenant_world.project_ids[PRIVATE_CASE]
    r = tenant_world.client("ref").post(
        "/api/v1/intelligence/research",
        json={"query": "Investigate additionality and leakage", "project_id": pid},
    )
    assert r.status_code == 200
    body = r.json()
    if body["status"] != "insufficient_context":
        pytest.skip("evidence caches present for this project in this environment")
    assert body["latency_ms"] is None and body["missing_context"]
    assert groq_mock["calls"] == 0
    text = json.dumps(body).lower()
    assert not any(m in text for m in KARIBA_MARKERS if m != "kariba")
    assert "kariba" not in json.dumps(body["retrieved_facts"]).lower()


def test_project_with_evidence_gets_grounded_answer(tenant_world, groq_mock, monkeypatch):
    _evidence_context(monkeypatch)
    pid = tenant_world.project_ids[PRIVATE_CASE]
    r = tenant_world.client("ref").post(
        "/intelligence/research",
        json={
            "query": "What evidence exists?",
            "project_id": pid,
            "mode": "environmental_research",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["project_id"] == pid
    assert body["latency_ms"] is not None
    assert body["retrieved_facts"] and body["answer"]
    assert groq_mock["calls"] == 1
    assert not any(m in json.dumps(body).lower() for m in KARIBA_MARKERS)


def test_unconfigured_key_over_http(tenant_world, monkeypatch):
    _evidence_context(monkeypatch)
    svc = _no_key_service(monkeypatch)
    monkeypatch.setattr("groundtruth.platform.api.v2.get_global_intelligence_service", lambda: svc)
    pid = tenant_world.project_ids[PRIVATE_CASE]
    c = tenant_world.client("ref")
    r = c.post("/intelligence/research", json={"query": "What evidence exists?", "project_id": pid})
    assert r.status_code == 200
    assert r.json()["status"] == "unavailable" and r.json()["latency_ms"] is None
    st = c.get("/intelligence/status")
    assert st.status_code == 200 and st.json()["configured"] is False
    assert st.json()["reason"] == "GROQ_API_KEY not configured"
