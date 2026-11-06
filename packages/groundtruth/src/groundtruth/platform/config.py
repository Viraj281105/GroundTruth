"""Application configuration, loaded from the environment.

Nothing here reaches out to a network. Credentials are read but never logged,
and every external provider is optional so the full pipeline can run offline
against synthetic fixtures.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # .../src/groundtruth


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the repository root by walking up for a marker directory.

    Counting ``parents[n]`` is brittle: it broke silently when the package moved
    into ``packages/groundtruth/`` during the monorepo restructure. Searching for
    a marker survives that kind of move, and falls back to the current working
    directory when the package is installed non-editable (a wheel has no
    repository around it).
    """
    candidate = (start or PACKAGE_ROOT).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / "cases").is_dir() and (directory / "docs").is_dir():
            return directory
    return Path.cwd()


REPO_ROOT = find_repo_root()


class Settings(BaseSettings):
    """Runtime settings for the API, CLI and pipeline."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    random_seed: int = Field(
        default=20260101, description="Seed for every stochastic step, for reproducibility."
    )

    # --- paths -------------------------------------------------------------
    data_dir: Path = Field(default=REPO_ROOT / "data")
    cases_dir: Path = Field(default=REPO_ROOT / "cases")
    artifacts_dir: Path = Field(default=REPO_ROOT / "artifacts")

    # --- earth observation providers --------------------------------------
    google_cloud_project: str | None = None
    gee_service_account_json: str | None = None
    sentinel_hub_client_id: str | None = None
    sentinel_hub_client_secret: SecretStr | None = None
    global_forest_watch_api_key: SecretStr | None = None

    # --- generative reporting layer ---------------------------------------
    genai_provider: Literal["none", "nugen", "openai", "anthropic"] = "none"
    genai_model: str = "unset"
    genai_base_url: str | None = None
    nugen_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    genai_max_output_tokens: int = 1200
    genai_temperature: float = 0.0

    # --- build identity -----------------------------------------------------
    git_sha: str | None = Field(
        default=None,
        description=(
            "Commit this process runs, recorded on every result it produces. Set by the "
            "deployment (env GIT_SHA). Unset means unknown, and is recorded as null, never "
            "as a placeholder string (R6)."
        ),
    )

    # --- persistence and services -----------------------------------------
    database_url: str | None = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_allowed_origins: str | None = Field(
        default=None,
        description=(
            "Comma-separated browser origins the API accepts cross-origin requests from "
            "(env CORS_ALLOWED_ORIGINS). Unset means FRONTEND_URL alone. A wildcard is "
            "refused: the API names its callers."
        ),
    )

    # --- authentication (docs/security/auth.md) ----------------------------
    auth_required: bool = Field(
        default=False,
        description="Enforce sign-in on protected endpoints (env AUTH_REQUIRED).",
    )
    auth_allow_registration: bool = Field(
        default=True, description="Allow POST /auth/register (env AUTH_ALLOW_REGISTRATION)."
    )
    auth_cookie_secure: bool = Field(
        default=False,
        description="Set the Secure flag on the session cookie (env AUTH_COOKIE_SECURE). "
        "Must be true behind HTTPS.",
    )
    auth_session_days: int = Field(default=7, ge=1, le=90)

    # --- analysis defaults -------------------------------------------------
    min_pre_periods: int = Field(
        default=5, description="Minimum pre-treatment periods required for a synthetic control."
    )
    min_donors: int = Field(default=10, description="Minimum admissible donors for an estimate.")
    max_pre_rmse_ratio: float = Field(
        default=0.30,
        description="Reject a fit whose pre-period RMSE exceeds this share of the outcome SD.",
    )

    @field_validator("git_sha")
    @classmethod
    def _blank_git_sha_is_unknown(cls, value: str | None) -> str | None:
        # An empty GIT_SHA= in an env file must not be recorded as if it were a commit.
        if value is None:
            return None
        return value.strip() or None

    @field_validator("cors_allowed_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if any(origin.strip() == "*" for origin in value.split(",")):
            # "*" would let any site drive the API from a visitor's browser. Deployments
            # list their frontends explicitly instead.
            raise ValueError("CORS_ALLOWED_ORIGINS must list origins explicitly, never '*'")
        return value

    @property
    def cors_origins(self) -> list[str]:
        """The origins the API's CORS middleware allows, in configured order."""
        if self.cors_allowed_origins is None:
            return [self.frontend_url.rstrip("/")]
        origins = (origin.strip().rstrip("/") for origin in self.cors_allowed_origins.split(","))
        return list(dict.fromkeys(origin for origin in origins if origin))

    @property
    def earth_observation_configured(self) -> bool:
        """True if at least one real Earth-observation provider has credentials."""
        return bool(
            self.gee_service_account_json
            or self.sentinel_hub_client_id
            or self.global_forest_watch_api_key
        )

    @property
    def genai_configured(self) -> bool:
        """True if a generative provider is selected *and* has a key."""
        keys = {
            "nugen": self.nugen_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return self.genai_provider != "none" and keys.get(self.genai_provider) is not None


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache. Used by tests that patch the environment."""
    get_settings.cache_clear()
