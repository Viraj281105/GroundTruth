"""Application configuration, loaded from the environment.

Nothing here reaches out to a network. Credentials are read but never logged,
and every external provider is optional so the full pipeline can run offline
against synthetic fixtures.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parents[1]  # src/groundtruth
REPO_ROOT = PACKAGE_ROOT.parents[1]  # repository root


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

    # --- persistence and services -----------------------------------------
    database_url: str | None = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # --- analysis defaults -------------------------------------------------
    min_pre_periods: int = Field(
        default=5, description="Minimum pre-treatment periods required for a synthetic control."
    )
    min_donors: int = Field(default=10, description="Minimum admissible donors for an estimate.")
    max_pre_rmse_ratio: float = Field(
        default=0.30,
        description="Reject a fit whose pre-period RMSE exceeds this share of the outcome SD.",
    )

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
