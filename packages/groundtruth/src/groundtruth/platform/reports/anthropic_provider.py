"""Anthropic Messages API narrator using JSON tool-use for structured output.

The model is forced to call ``write_report`` whose schema carries the narrative
sections; the sections are rendered to Markdown here. The result is still
untrusted text: :func:`groundtruth.platform.reports.narrative.generate_report`
verifies every number against the evidence bundle before accepting it.
"""

from __future__ import annotations

from typing import Any

import httpx

from groundtruth.contracts.errors import ConfigurationError

ANTHROPIC_VERSION = "2023-06-01"
TOOL_NAME = "write_report"

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One-sentence outcome."},
        "summary": {"type": "string", "description": "Plain-English summary."},
        "findings": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "summary", "findings", "caveats"],
}


def sections_to_markdown(data: dict[str, Any]) -> str:
    """Render the structured narrative sections as Markdown."""
    lines = [f"# {data['headline']}", "", str(data["summary"]), ""]
    findings = [str(f) for f in data.get("findings", [])]
    if findings:
        lines += ["## Findings", "", *[f"- {f}" for f in findings], ""]
    caveats = [str(c) for c in data.get("caveats", [])]
    if caveats:
        lines += ["## How to read this report", "", *[f"- {c}" for c in caveats], ""]
    return "\n".join(lines)


class AnthropicNarrator:
    """Narrator backed by the Anthropic Messages API (plain httpx, no SDK)."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str = "https://api.anthropic.com/v1",
        *,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = client

    @property
    def is_configured(self) -> bool:
        """True if an API key is present."""
        return bool(self.api_key)

    def complete(self, system: str, user: str) -> str:
        """Call the API with a forced tool call and return rendered Markdown."""
        if not self.api_key:
            raise ConfigurationError("ANTHROPIC_API_KEY is not set.")
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": "Submit the narrative report sections.",
                    "input_schema": REPORT_SCHEMA,
                }
            ],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(f"{self.base_url}/messages", json=payload, headers=headers)
        finally:
            if self._client is None:
                client.close()
        response.raise_for_status()
        for block in response.json().get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
                data = block.get("input")
                if isinstance(data, dict) and "headline" in data and "summary" in data:
                    return sections_to_markdown(data)
        raise ValueError("Anthropic response contained no valid write_report tool call")
