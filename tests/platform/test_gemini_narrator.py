"""Google Gemini narrator tests with mocked HTTP (no network, no key)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from groundtruth.cli import main
from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.config import Settings
from groundtruth.platform.reports.anthropic_provider import REPORT_SCHEMA
from groundtruth.platform.reports.narrative import generate_report
from groundtruth.platform.reports.providers import GeminiNarrator, build_narrator


def _narrator(
    summary: str,
    seen: list[dict[str, Any]],
    caveats: list[str] | None = None,
    *,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.2,
) -> GeminiNarrator:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": json.loads(request.content),
            }
        )
        report_data = {
            "headline": "Outcome",
            "summary": summary,
            "findings": [],
            "caveats": caveats or [],
        }
        candidate = {
            "content": {
                "parts": [{"text": json.dumps(report_data)}],
                "role": "model",
            },
            "finishReason": "STOP",
        }
        return httpx.Response(200, json={"candidates": [candidate]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GeminiNarrator("test-key", model, temperature=temperature, client=client)


def test_grounded_response_is_accepted_and_request_is_structured(bundle: Any) -> None:
    seen: list[dict[str, Any]] = []
    caveats = list(bundle.verdict.caveats)
    narrator = _narrator("The estimated effect was 0.0421.", seen, caveats)
    report = generate_report(bundle, narrator=narrator)

    assert not report.fell_back
    assert report.generator == "genai:gemini"
    assert "# Outcome" in report.markdown
    assert "The estimated effect was 0.0421." in report.markdown

    req = seen[0]
    assert "key=test-key" in req["url"]
    assert "models/gemini-2.5-flash:generateContent" in req["url"]

    body = req["body"]
    assert body["generationConfig"]["temperature"] == 0.2
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"] == REPORT_SCHEMA
    assert body["contents"][0]["role"] == "user"
    assert "systemInstruction" in body


def test_invented_number_is_rejected_and_falls_back(bundle: Any) -> None:
    seen: list[dict[str, Any]] = []
    narrator = _narrator("The project over-issued 12400000 credits.", seen, [])
    report = generate_report(bundle, narrator=narrator)

    assert report.fell_back
    assert report.generator == "deterministic"
    assert report.grounding is not None
    assert "12400000" in report.grounding.ungrounded_numbers


def test_direct_json_response_accepted(bundle: Any) -> None:
    seen: list[dict[str, Any]] = []
    caveats = list(bundle.verdict.caveats)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"body": json.loads(request.content)})
        return httpx.Response(
            200,
            json={
                "headline": "Outcome",
                "summary": "The estimated effect was 0.0421.",
                "findings": [],
                "caveats": caveats,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    narrator = GeminiNarrator("test-key", "gemini-2.5-flash", client=client)
    report = generate_report(bundle, narrator=narrator)

    assert not report.fell_back
    assert report.generator == "genai:gemini"
    assert "The estimated effect was 0.0421." in report.markdown


def test_tool_call_function_call_response_accepted(bundle: Any) -> None:
    caveats = list(bundle.verdict.caveats)

    def handler(request: httpx.Request) -> httpx.Response:
        resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "write_report",
                                    "args": {
                                        "headline": "Outcome",
                                        "summary": "The estimated effect was 0.0421.",
                                        "findings": [],
                                        "caveats": caveats,
                                    },
                                }
                            }
                        ]
                    }
                }
            ]
        }
        return httpx.Response(200, json=resp)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    narrator = GeminiNarrator("test-key", "gemini-2.5-flash", client=client)
    report = generate_report(bundle, narrator=narrator)

    assert not report.fell_back
    assert report.generator == "genai:gemini"
    assert "The estimated effect was 0.0421." in report.markdown


def test_markdown_fenced_json_response_accepted(bundle: Any) -> None:
    caveats = list(bundle.verdict.caveats)

    def handler(request: httpx.Request) -> httpx.Response:
        report_data = {
            "headline": "Outcome",
            "summary": "The estimated effect was 0.0421.",
            "findings": [],
            "caveats": caveats,
        }
        resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": f"```json\n{json.dumps(report_data)}\n```"}],
                    }
                }
            ]
        }
        return httpx.Response(200, json=resp)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    narrator = GeminiNarrator("test-key", "gemini-2.5-flash", client=client)
    report = generate_report(bundle, narrator=narrator)

    assert not report.fell_back
    assert report.generator == "genai:gemini"


def test_http_error_falls_back(bundle: Any) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    narrator = GeminiNarrator("k", "m", client=client)
    report = generate_report(bundle, narrator=narrator)
    assert report.fell_back
    assert report.generator == "deterministic"


def test_malformed_response_falls_back(bundle: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    narrator = GeminiNarrator("k", "m", client=client)
    report = generate_report(bundle, narrator=narrator)
    assert report.fell_back
    assert report.generator == "deterministic"


def test_selecting_gemini_without_key_is_an_error() -> None:
    settings = Settings(genai_provider="gemini", gemini_api_key=None)
    with pytest.raises(ConfigurationError):
        build_narrator(settings)


def test_build_narrator_with_gemini_config() -> None:
    # _env_file=None: the developer's own .env (e.g. GENAI_MODEL) must not decide this test.
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        genai_provider="gemini",
        gemini_api_key="my-gemini-key",
        gemini_model="gemini-2.5-flash",
    )
    narrator = build_narrator(settings)
    assert isinstance(narrator, GeminiNarrator)
    assert narrator.api_key == "my-gemini-key"
    assert narrator.model == "gemini-2.5-flash"


def test_gemini_missing_key_in_complete_raises() -> None:
    narrator = GeminiNarrator(api_key=None)
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is not set"):
        narrator.complete("sys", "usr")


def test_doctor_command_recognizes_gemini(capsys: Any, monkeypatch: Any) -> None:
    from groundtruth.platform.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "genai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "mock-gemini-key")

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "genai provider" in out
    assert "gemini" in out
    assert "genai configured" in out
    assert "True" in out
    assert "genai narration implemented" in out
    assert "yes" in out
