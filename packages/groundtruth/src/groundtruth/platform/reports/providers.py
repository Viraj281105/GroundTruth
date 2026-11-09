"""Language-model providers for the narration layer.

STATUS: interfaces implemented; network calls NOT implemented.

The narration layer is optional by design, so these stubs raise rather than
guess. The deterministic renderer in :mod:`groundtruth.platform.reports.narrative`
produces a complete, correct report without any of them.

The Nugen provider is the one the competition submission targets, because its
alignment stack is what the hallucination evaluation in
``experiments/genai_grounding_eval`` is meant to measure against an unaligned
baseline. That evaluation has not been run; no comparative claim is made here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

import httpx

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.config import Settings
from groundtruth.platform.reports.anthropic_provider import (
    REPORT_SCHEMA,
    AnthropicNarrator,
    sections_to_markdown,
)


@runtime_checkable
class Narrator(Protocol):
    """Anything that can turn a system and user prompt into narrative text."""

    name: str

    def complete(self, system: str, user: str) -> str:
        """Return the model's completion."""
        ...


class EchoNarrator:
    """Test double that returns a fixed string.

    Used by the grounding test-suite to exercise both the accept and the reject
    path without a network call.
    """

    name = "echo"

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        """Record the call and return the canned response."""
        self.calls.append((system, user))
        return self.response


class _HttpNarrator:
    """Shared configuration surface for HTTP-backed providers."""

    name = "http"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        *,
        temperature: float = 0.0,
        max_tokens: int = 1200,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def is_configured(self) -> bool:
        """True if an API key is present."""
        return bool(self.api_key)

    def complete(self, system: str, user: str) -> str:
        """Call the provider. NOT IMPLEMENTED."""
        raise NotImplementedError(
            f"{self.name} narration is not implemented yet. The deterministic renderer produces "
            "a complete report without it; see docs/architecture/genai.md."
        )


class NugenNarrator(_HttpNarrator):
    """Nugen alignment-stack narrator. NOT IMPLEMENTED."""

    name = "nugen"


class OpenAINarrator(_HttpNarrator):
    """OpenAI narrator, used as the unaligned baseline in the evaluation."""

    name = "openai"


class GeminiNarrator:
    """Narrator backed by the Google Gemini REST API (plain httpx, no SDK)."""

    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-2.5-flash",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
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
        """Call the Gemini API and return rendered Markdown."""
        if not self.api_key:
            raise ConfigurationError("GEMINI_API_KEY is not set.")

        if ":generateContent" in self.base_url:
            url = self.base_url
        else:
            url = f"{self.base_url}/models/{self.model}:generateContent"

        params = {"key": self.api_key}
        headers = {
            "x-goog-api-key": self.api_key,
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user}],
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json",
                "responseSchema": REPORT_SCHEMA,
            },
        }
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}],
            }

        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(url, json=payload, params=params, headers=headers)
        finally:
            if self._client is None:
                client.close()

        response.raise_for_status()
        data = response.json()

        # Handle direct response adhering to REPORT_SCHEMA
        if isinstance(data, dict) and "headline" in data and "summary" in data:
            return sections_to_markdown(data)

        # Handle candidates from Gemini REST API
        if isinstance(data, dict):
            for candidate in data.get("candidates", []):
                content = candidate.get("content", {})
                for part in content.get("parts", []):
                    # Handle tool / functionCall
                    if "functionCall" in part:
                        args = part["functionCall"].get("args")
                        if isinstance(args, dict) and "headline" in args and "summary" in args:
                            return sections_to_markdown(args)
                    # Handle structured JSON text
                    if "text" in part:
                        text = part["text"].strip()
                        if text.startswith("```json"):
                            text = text[7:]
                        elif text.startswith("```"):
                            text = text[3:]
                        if text.endswith("```"):
                            text = text[:-3]
                        text = text.strip()
                        try:
                            parsed = json.loads(text)
                            if (
                                isinstance(parsed, dict)
                                and "headline" in parsed
                                and "summary" in parsed
                            ):
                                return sections_to_markdown(parsed)
                        except json.JSONDecodeError:
                            continue

        raise ValueError("Gemini response contained no valid narrative report content")


def build_narrator(settings: Settings) -> Narrator | None:
    """Construct the configured narrator, or ``None`` if narration is disabled.

    Raises:
        ConfigurationError: if a provider is selected but has no API key. Silently
            degrading to no narration would hide a deployment mistake.
    """
    if settings.genai_provider == "none":
        return None
    if not settings.genai_configured:
        raise ConfigurationError(
            f"GENAI_PROVIDER={settings.genai_provider} is selected but its API key is not set. "
            "Set the key, or set GENAI_PROVIDER=none to use the deterministic renderer."
        )

    key_map: dict[str, Any] = {
        "nugen": settings.nugen_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
    }
    default_urls = {
        "nugen": "https://api.nugen.in/v1",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta",
    }
    classes: dict[str, Callable[..., Narrator]] = {
        "nugen": NugenNarrator,
        "openai": OpenAINarrator,
        "anthropic": AnthropicNarrator,
        "gemini": GeminiNarrator,
    }

    provider = settings.genai_provider
    secret = key_map[provider]
    if hasattr(secret, "get_secret_value"):
        api_key = secret.get_secret_value()
    elif isinstance(secret, str):
        api_key = secret
    else:
        api_key = None

    model = (
        settings.gemini_model
        if provider == "gemini" and settings.genai_model == "unset"
        else settings.genai_model
    )

    return classes[provider](
        api_key=api_key,
        model=model,
        base_url=settings.genai_base_url or default_urls[provider],
        temperature=settings.genai_temperature,
        max_tokens=settings.genai_max_output_tokens,
    )
