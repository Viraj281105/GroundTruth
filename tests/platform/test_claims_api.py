"""POST /claims/analyze."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from groundtruth.contracts.grounding import PROHIBITED_PATTERNS
from groundtruth.platform.api.app import app

client = TestClient(app)
TEXT = "The project covers 12,000 hectares. Baseline emissions were 1.5 million tCO2e."


def _wording_ok(text: str) -> bool:
    return not any(re.search(p, text, re.IGNORECASE) for p, _ in PROHIBITED_PATTERNS)


def test_extracts_claims_with_spans() -> None:
    r = client.post("/claims/analyze", json={"text": TEXT})
    assert r.status_code == 200
    body = r.json()
    assert {c["kind"] for c in body["claims"]} >= {"area_hectares", "baseline"}
    for c in body["claims"]:
        assert TEXT[c["span"]["start"] : c["span"]["end"]] == c["span"]["text"]
    assert body["comparisons"] == []
    assert "No case was selected" in body["disclaimer"]


def test_empty_and_blank_text_is_422() -> None:
    assert client.post("/claims/analyze", json={"text": ""}).status_code == 422
    assert client.post("/claims/analyze", json={"text": "   "}).status_code == 422


def test_too_long_is_422() -> None:
    assert client.post("/claims/analyze", json={"text": "a" * 200_001}).status_code == 422


def test_unknown_case_is_404() -> None:
    r = client.post("/claims/analyze", json={"text": TEXT, "case_id": "no-such-case"})
    assert r.status_code == 404


def test_case_comparison_never_invents_estimates() -> None:
    r = client.post("/claims/analyze", json={"text": TEXT, "case_id": "kariba-redd"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["comparisons"]) == len(body["claims"])
    for c in body["comparisons"]:
        if c["claim_kind"] != "area_hectares":
            assert c["estimated"] is None


def test_wording_is_neutral() -> None:
    r = client.post("/claims/analyze", json={"text": TEXT, "case_id": "kariba-redd"}).json()
    texts = [r["disclaimer"], *(c["note"] for c in r["comparisons"])]
    assert all(_wording_ok(t) for t in texts)
    assert "warrants accredited review" in r["disclaimer"]
