"""Response models of the grant, portfolio, audit and activity routes.

Portfolio rows are built from the same engine ``Assessment`` as ``/projects/{id}/assessment``
and only reshaped. A portfolio never aggregates: simulated projects are a separate list, and
funding appears only as the amount the owning organization reported (never computed).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.platform.api.project_schemas import RecommendationView
from groundtruth.platform.api.schemas import DataModeName, ProjectLevelName, ProjectView

GrantLevel = Literal["view", "audit", "contribute"]


class GrantRequest(BaseModel):
    """Share a project with another organization."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    org_slug: str = Field(min_length=1, max_length=100)
    """Slug of the organization to share with."""
    level: GrantLevel
    """What they may do: `view`, `audit` or `contribute`."""


class GrantView(BaseModel):
    """An active grant of a project to another organization."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    org_slug: str
    """Slug of the organization granted access."""
    org_name: str
    """Its name."""
    org_type: str
    """Its type."""
    level: GrantLevel
    """Its level: `view`, `audit` or `contribute`."""
    granted_at: datetime
    """When access was granted (UTC)."""


class DimensionStatuses(BaseModel):
    """The status of each assessment dimension, for a portfolio row."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    trajectory: str = Field(description="Status of the vegetation trajectory dimension.")
    risk: str = Field(description="Status of the ecological risk dimension.")
    evidence_quality: str = Field(description="Evidence-quality rating.")


class ReportedFunding(BaseModel):
    """Funding exactly as the owning organization reported it. Never computed by GroundTruth."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    amount: float
    """The amount reported."""
    currency: str | None = None
    """Its currency, as reported."""
    reported_by: str = Field(description="Name of the owning organization.")


class PortfolioRow(BaseModel):
    """One project in a portfolio."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    project: ProjectView
    """The project."""
    access_level: ProjectLevelName
    """Your organization's level on it."""
    assessment_level: int = Field(description="0-5; a level, never a score.")
    level_name: str
    """Assessment level reached."""
    dimension_statuses: DimensionStatuses
    """Status of each dimension."""
    top_recommendation: RecommendationView | None = Field(
        default=None, description="Highest-priority recommendation for the org's persona."
    )
    attribution_verdict: str | None = Field(
        default=None, description="Null only when the row is degraded."
    )
    evidence_confidence: str | None = Field(
        default=None, description="Null only when the row is degraded."
    )
    data_mode: DataModeName
    """`observed` or `simulated`."""
    reported_funding: ReportedFunding | None = None
    """Funding as the owner reported it, when it did."""
    degraded: bool = Field(
        default=False, description="True when the assessment failed; the row is level 0."
    )
    degraded_reason: str | None = None
    """Why the row is incomplete, when its assessment could not be built."""


class PortfolioView(BaseModel):
    """Every project your organization can see, with its assessment summary."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    projects: list[PortfolioRow] = Field(description="Real (observed) projects only.")
    simulated: list[PortfolioRow] = Field(
        description="SIMULATED DATA projects, kept apart and never aggregated with real ones."
    )


class AuditEventView(BaseModel):
    """One security-relevant event."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    id: str
    """Event id."""
    occurred_at: datetime
    """When it happened (UTC)."""
    actor_user_id: str | None = None
    """Who did it, when signed in."""
    action: str
    """What was done, e.g. `run.start`, `case.create`, `auth.login`."""
    resource_type: str
    """Kind of resource acted on."""
    resource_id: str | None = None
    """The resource acted on."""
    outcome: str
    """`success` or `denied`."""
    ip: str | None = None
    """Client address."""
    user_agent: str | None = None
    """Client user agent."""
    details: dict[str, Any] = Field(default_factory=dict)
    """Structured context of the event."""


class AuditPage(BaseModel):
    """A page of audit events, newest first."""

    model_config = ConfigDict(use_attribute_docstrings=True)
    events: list[AuditEventView]
    """Events on this page."""
    next_cursor: str | None = None
    """Pass as `cursor` for the next page; null on the last."""


class ActivityItem(BaseModel):
    """One feed entry: no actor, address, user agent or details."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    id: str
    """Event id."""
    occurred_at: datetime
    """When it happened (UTC)."""
    action: str
    """What was done."""
    outcome: str
    """`success` or `denied`."""
    project_id: str | None = None
    """The project concerned."""
    project_slug: str | None = None
    """Its slug."""
    project_name: str | None = None
    """Its name."""
    own: bool = Field(description="True when the organization itself did this.")
