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

from typing import Protocol, runtime_checkable

from groundtruth.contracts.errors import ConfigurationError
from groundtruth.platform.config import Settings


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
            "a complete report without it; see docs/07-genai-grounding.md."
        )


class NugenNarrator(_HttpNarrator):
    """Nugen alignment-stack narrator. NOT IMPLEMENTED."""

    name = "nugen"


class OpenAINarrator(_HttpNarrator):
    """OpenAI narrator, used as the unaligned baseline in the evaluation."""

    name = "openai"


class AnthropicNarrator(_HttpNarrator):
    """Anthropic narrator."""

    name = "anthropic"


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

    key_map = {
        "nugen": settings.nugen_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    default_urls = {
        "nugen": "https://api.nugen.in/v1",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
    }
    classes: dict[str, type[_HttpNarrator]] = {
        "nugen": NugenNarrator,
        "openai": OpenAINarrator,
        "anthropic": AnthropicNarrator,
    }

    provider = settings.genai_provider
    secret = key_map[provider]
    return classes[provider](
        api_key=secret.get_secret_value() if secret else None,
        model=settings.genai_model,
        base_url=settings.genai_base_url or default_urls[provider],
        temperature=settings.genai_temperature,
        max_tokens=settings.genai_max_output_tokens,
    )
