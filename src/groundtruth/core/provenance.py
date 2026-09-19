"""Provenance records: where a number came from and how it was produced."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Provenance(BaseModel):
    """An immutable record of the origin of a single analytical value.

    Every :class:`~groundtruth.core.evidence.Evidence` item must carry one.
    Without provenance a number cannot be audited, and an un-auditable number is
    not admissible in a verification report.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="Data source or upstream system, e.g. 'Sentinel-2 L2A'.")
    method: str = Field(description="Algorithm or estimator that produced the value.")
    stage: str = Field(
        default="unspecified",
        description="Pipeline stage: ingestion|geospatial|matching|causal|uncertainty|external.",
    )
    source_uri: str | None = Field(
        default=None, description="Resolvable identifier for the source (URL, asset id, DOI)."
    )
    retrieved_at: datetime | None = Field(
        default=None, description="When the underlying data was retrieved."
    )
    code_version: str | None = Field(
        default=None, description="Git SHA or package version of the producing code."
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Estimator parameters needed to reproduce the value."
    )
    inputs: tuple[str, ...] = Field(
        default=(), description="Evidence ids this value was derived from."
    )
    notes: str | None = Field(default=None, description="Caveats a human auditor should read.")

    @classmethod
    def external(
        cls, source: str, source_uri: str | None = None, notes: str | None = None
    ) -> Provenance:
        """Provenance for a third-party published figure GroundTruth did not compute."""
        return cls(
            source=source,
            method="published-third-party-figure",
            stage="external",
            source_uri=source_uri,
            notes=notes,
        )

    @classmethod
    def computed(
        cls,
        source: str,
        method: str,
        stage: str,
        *,
        parameters: dict[str, Any] | None = None,
        inputs: tuple[str, ...] = (),
        notes: str | None = None,
    ) -> Provenance:
        """Provenance for a value produced by the GroundTruth analytical engine."""
        from groundtruth import __version__

        return cls(
            source=source,
            method=method,
            stage=stage,
            retrieved_at=datetime.now(UTC),
            code_version=__version__,
            parameters=parameters or {},
            inputs=inputs,
            notes=notes,
        )

    def fingerprint(self) -> str:
        """Stable short hash of the provenance record, for audit trails."""
        payload = json.dumps(
            self.model_dump(mode="json", exclude={"retrieved_at"}), sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
