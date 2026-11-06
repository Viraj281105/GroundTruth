"""Anthropic narrator tests with mocked HTTP (no network, no key)."""

from __future__ import annotations

import json

import httpx
import pytest

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.config import Settings
from groundtruth.platform.reports.anthropic_provider import AnthropicNarrator
from groundtruth.platform.reports.narrative import generate_report
from groundtruth.platform.reports.providers import build_narrator


def _narrator(
    summary: str, seen: list[dict], caveats: list[str] | None = None
) -> AnthropicNarrator:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        block = {
            "type": "tool_use",
            "name": "write_report",
            "input": {
                "headline": "Outcome",
                "summary": summary,
                "findings": [],
                "caveats": caveats or [],
            },
        }
        return httpx.Response(200, json={"content": [block]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return AnthropicNarrator("k", "model-x", temperature=0.2, client=client)


def test_grounded_response_is_accepted_and_request_is_structured(bundle):
    seen: list[dict] = []
    caveats = list(bundle.verdict.caveats)
    narrator = _narrator("The estimated effect was 0.0421.", seen, caveats)
    report = generate_report(bundle, narrator=narrator)
    assert not report.fell_back
    assert report.generator == "genai:anthropic"
    body = seen[0]["body"]
    assert body["model"] == "model-x" and body["temperature"] == 0.2
    assert body["tool_choice"] == {"type": "tool", "name": "write_report"}
    assert seen[0]["headers"]["x-api-key"] == "k"


def test_invented_number_is_rejected_and_falls_back(bundle):
    narrator = _narrator("The project over-issued 12400000 credits.", [])
    report = generate_report(bundle, narrator=narrator)
    assert report.fell_back
    assert report.generator == "deterministic"
    assert report.grounding is not None
    assert "12400000" in report.grounding.ungrounded_numbers


def test_http_error_falls_back(bundle):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    report = generate_report(bundle, narrator=AnthropicNarrator("k", "m", client=client))
    assert report.fell_back


def test_selecting_anthropic_without_key_is_an_error():
    settings = Settings(genai_provider="anthropic", anthropic_api_key=None)
    with pytest.raises(ConfigurationError):
        build_narrator(settings)
