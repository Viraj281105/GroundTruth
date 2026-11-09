"""Response models of the grant, portfolio, audit and activity routes.

Portfolio rows are built from the same engine ``Assessment`` as ``/projects/{id}/assessment``
and only reshaped. A portfolio never aggregates: simulated projects are a separate list, and
funding appears only as the amount the owning organization reported (never computed).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from groundtruth.platform.api.project_schemas import RecommendationView
from groundtruth.platform.api.schemas import DataModeName, ProjectLevelName, ProjectView

GrantLevel = Literal["view", "audit", "contribute"]


class GrantRequest(BaseModel):
    org_slug: str = Field(min_length=1, max_length=100)
    level: GrantLevel


class GrantView(BaseModel):
    """An active grant of a project to another organization."""

    org_slug: str
    org_name: str
    org_type: str
    level: GrantLevel
    granted_at: datetime


class DimensionStatuses(BaseModel):
    trajectory: str = Field(description="Status of the vegetation trajectory dimension.")
    risk: str = Field(description="Status of the ecological risk dimension.")
    evidence_quality: str = Field(description="Evidence-quality rating.")


class ReportedFunding(BaseModel):
    """Funding exactly as the owning organization reported it. Never computed by GroundTruth."""

    amount: float
    currency: str | None = None
    reported_by: str = Field(description="Name of the owning organization.")


class PortfolioRow(BaseModel):
    project: ProjectView
    access_level: ProjectLevelName
    assessment_level: int = Field(description="0-5; a level, never a score.")
    level_name: str
    dimension_statuses: DimensionStatuses
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
    reported_funding: ReportedFunding | None = None
    degraded: bool = Field(
        default=False, description="True when the assessment failed; the row is level 0."
    )
    degraded_reason: str | None = None


class PortfolioView(BaseModel):
    projects: list[PortfolioRow] = Field(description="Real (observed) projects only.")
    simulated: list[PortfolioRow] = Field(
        description="SIMULATED DATA projects, kept apart and never aggregated with real ones."
    )


class AuditEventView(BaseModel):
    id: str
    occurred_at: datetime
    actor_user_id: str | None = None
    actor_email: str | None = Field(
        default=None,
        description="Email of the actor when they are a member of this organization; null otherwise.",
    )
    action: str
    resource_type: str
    resource_id: str | None = None
    outcome: str
    ip: str | None = None
    user_agent: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditPage(BaseModel):
    events: list[AuditEventView]
    next_cursor: str | None = None


class ActivityItem(BaseModel):
    """One feed entry: no actor, address, user agent or details."""

    id: str
    occurred_at: datetime
    action: str
    outcome: str
    project_id: str | None = None
    project_slug: str | None = None
    project_name: str | None = None
    own: bool = Field(description="True when the organization itself did this.")
