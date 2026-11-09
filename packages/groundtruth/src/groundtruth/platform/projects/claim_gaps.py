"""What a project still lacks before its claims can be checked (read-only, no I/O of its own).

Built from the computed readiness criteria, so every item is a fact about the project's stored
artifacts, never a guess. Used by the structured-claims routes to give a new project an honest,
actionable empty state instead of demonstration data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from groundtruth.platform.projects.readiness import compute_project_readiness
from groundtruth.platform.store.models import ProjectRow

_ACTIONS = {
    "boundary_verified": "Add the project boundary (GeoJSON polygon) in project settings.",
    "observation_years": "Ingest annual satellite observations for the project area.",
    "pre_treatment_observations": "Ingest observations from before the intervention started.",
    "climate_covariates": "Ingest climate covariates (rainfall, temperature) for the area.",
    "donor_panel": "Provide comparison areas (donor pool) outside the project boundary.",
    "sensor_continuity": "Ingest observations from a consistent sensor across the period.",
}


def claim_gaps(project: ProjectRow, data_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Return ``(missing_information, next_steps)`` for ``project``.

    Each missing item is ``{"id", "label", "status", "detail", "action"}``. Always includes the
    fact that no claims have been submitted, since this is called only for an empty portfolio.
    """
    missing: list[dict[str, Any]] = [
        {
            "id": "claims_submitted",
            "label": "Claims to verify",
            "status": "not_met",
            "detail": "No claims have been submitted for this project.",
            "action": "Upload a project document or paste claim text to extract claims.",
        }
    ]
    try:
        readiness = compute_project_readiness(project, data_dir=data_dir)
        for c in readiness.criteria:
            if c.status != "met":
                missing.append(
                    {
                        "id": c.id,
                        "label": c.name,
                        "status": c.status,
                        "detail": c.evidence_needed,
                        "action": _ACTIONS.get(c.id, c.evidence_needed),
                    }
                )
    except Exception:  # readiness must never take the claims page down
        missing.append(
            {
                "id": "readiness_unavailable",
                "label": "Evidence readiness",
                "status": "unavailable",
                "detail": "Evidence readiness could not be computed for this project.",
                "action": "Add a boundary and ingest observations, then reload.",
            }
        )
    steps = [
        "Add the project boundary.",
        "Upload project documents containing the claims you want checked.",
        "Ingest observations (satellite series) for the project area.",
        "Return here to compare each claim with the available evidence.",
    ]
    return missing, steps
