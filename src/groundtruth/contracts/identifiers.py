"""Stable identifiers for runs, datasets, engines and specifications.

Reproducibility is a requirement of this system, not a convenience. Every
result must answer: which code, which data, which parameters, which seed. These
identifiers are how that question is answered without reading the source.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SLUG = r"^[a-z0-9]+(?:[-_.][a-z0-9]+)*$"


class DatasetRef(BaseModel):
    """A pinned reference to an external dataset.

    The platform resolves a logical dataset name to a concrete, versioned
    reference before the engine runs. The engine never chooses a dataset
    version, so a re-run months later uses the same imagery rather than
    whatever the provider currently serves.
    """

    model_config = ConfigDict(frozen=True)

    dataset_id: str = Field(pattern=SLUG, description="e.g. 'sentinel2-l2a', 'chirps-daily'.")
    version: str = Field(description="Provider version or snapshot date, e.g. '2024.1'.")
    provider: str = Field(description="e.g. 'google-earth-engine', 'synthetic'.")
    asset: str | None = Field(default=None, description="Provider asset path.")
    source_uri: str | None = None
    retrieved_at: str | None = Field(
        default=None, description="ISO timestamp of retrieval, set by the platform."
    )

    def __str__(self) -> str:
        return f"{self.dataset_id}@{self.version}"

    @property
    def is_synthetic(self) -> bool:
        """True if this dataset is simulated rather than observed."""
        return self.provider == "synthetic" or self.dataset_id.startswith("synthetic")


class EngineRef(BaseModel):
    """Which build of the analytical engine produced a result."""

    model_config = ConfigDict(frozen=True)

    engine_version: str = Field(description="Version of groundtruth.engine.")
    contract_version: str = Field(description="Contract version it targets.")
    git_sha: str | None = Field(default=None, description="Commit the run was executed from.")

    def __str__(self) -> str:
        suffix = f"+{self.git_sha[:8]}" if self.git_sha else ""
        return f"engine-{self.engine_version}{suffix}"


class ModelRef(BaseModel):
    """A named estimator configuration inside the engine.

    Distinct from :class:`EngineRef`: one engine build offers several estimators,
    and a specification curve runs many of them over the same request.
    """

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(pattern=SLUG, description="e.g. 'synthetic-control', 'did'.")
    variant: str = Field(default="default", description="e.g. 'ridge-0.01', 'rainfall-weighted'.")
    parameters: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.model_id}:{self.variant}"


def new_run_id() -> str:
    """Generate a fresh analysis run identifier."""
    return f"run_{uuid.uuid4().hex[:16]}"


def is_run_id(value: str) -> bool:
    """True if ``value`` looks like a run identifier."""
    return bool(re.fullmatch(r"run_[0-9a-f]{16}", value))


def spec_hash(payload: Any) -> str:
    """Deterministic hash of an analysis specification.

    Two requests with the same specification hash must produce the same result
    given the same engine version and datasets. Used as a cache key by the
    platform and as a reproducibility check in validation.

    Uses ``blake2b`` rather than ``hash()`` because Python salts string hashing
    per process, which would make the key differ between runs.
    """
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=16).hexdigest()
