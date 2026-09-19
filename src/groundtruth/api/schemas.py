"""Request and response schemas for the HTTP API.

The API deliberately exposes the evidence bundle rather than a bare verdict. A
consumer that only wants the label can read one field; a consumer doing due
diligence gets the full provenance in the same response.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from groundtruth.core.evidence import EvidenceBundle


class HealthResponse(BaseModel):
    """Service liveness and capability report."""

    status: str = "ok"
    version: str
    earth_observation_implemented: bool = Field(
        default=False, description="False until the Earth Engine reducer chain lands."
    )
    genai_narration_implemented: bool = Field(
        default=False, description="False until a narration provider is implemented."
    )
    cases_available: int = 0


class CaseSummary(BaseModel):
    """A case as listed by the API."""

    case_id: str
    name: str
    country: str
    standard: str
    registry_id: str | None = None
    ecosystem: str
    indicator: str
    pre_period: str
    post_period: str
    status: str
    has_known_reference: bool


class CaseDetail(CaseSummary):
    """Full case definition, including validation references."""

    area_ha: float | None = None
    donor_search_region: str
    donor_pool_size: int
    covariates: list[str]
    known_reference: dict[str, Any] = Field(
        default_factory=dict,
        description="Published third-party findings. Never an input to the estimate.",
    )
    notes: str = ""


class VerificationRequest(BaseModel):
    """Options for a verification run."""

    synthetic: bool = Field(
        default=True,
        description=(
            "Must be true until real Earth-observation providers are implemented. A request "
            "with synthetic=false is rejected rather than silently simulated."
        ),
    )
    true_effect: float = Field(
        default=0.06, description="Effect injected into the simulated treated unit."
    )
    min_donors: int = Field(default=10, ge=2)
    include_report: bool = True


class VerificationResponse(BaseModel):
    """The result of a verification run."""

    case_id: str
    data_mode: str = Field(description="'simulated' or 'observed'.")
    verdict_label: str
    verdict_rationale: str
    caveats: list[str]
    warnings: list[str]
    bundle: EvidenceBundle
    report_markdown: str | None = None
    report_generator: str | None = None


class ErrorResponse(BaseModel):
    """A structured error."""

    error: str
    detail: str
    hint: str | None = None
