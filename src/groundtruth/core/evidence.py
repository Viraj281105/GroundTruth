"""Evidence objects: the only currency the reporting layer is allowed to spend.

The analytical engine emits :class:`Evidence` items. Each one is a single value
with a unit, an optional interval, and mandatory :class:`Provenance`. The GenAI
reporting layer receives an :class:`EvidenceBundle` and may only narrate values
that appear in it.

This is a deliberate architectural boundary. A language model that is handed raw
satellite data and asked "was this project additional?" is guessing. A language
model handed a verified bundle and asked "explain these numbers" is doing the
job it is actually good at.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from groundtruth.core.errors import ProvenanceError
from groundtruth.core.provenance import Provenance
from groundtruth.core.types import Confidence, VerificationVerdict
from groundtruth.core.units import unit_family


class Evidence(BaseModel):
    """One auditable value with its unit, uncertainty and origin."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        description="Stable, human-readable id, e.g. 'effect.ndvi.point_estimate'.",
        pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$",
    )
    label: str = Field(description="Short human-readable description of the quantity.")
    value: float | int | str | bool
    unit: str = Field(default="", description="Unit from the declared vocabulary, or '' if none.")
    confidence: Confidence | None = None
    provenance: Provenance
    qualifiers: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured caveats, e.g. {'observed_not_causal': True}.",
    )

    @model_validator(mode="after")
    def _validate(self) -> Evidence:
        if self.unit:
            unit_family(self.unit)  # raises on unknown units
        if not self.provenance.source or not self.provenance.method:
            raise ProvenanceError(f"evidence {self.id!r} has incomplete provenance")
        return self

    @property
    def is_numeric(self) -> bool:
        """True if the value is a number (and not a bool, which is not a measurement)."""
        return isinstance(self.value, int | float) and not isinstance(self.value, bool)

    def rendered_value(self, precision: int = 4) -> str:
        """Value formatted for display, without inventing precision."""
        if self.is_numeric:
            return f"{float(self.value):.{precision}g}"
        return str(self.value)


class EvidenceBundle(BaseModel):
    """An immutable, verified collection of evidence for one case.

    The bundle is the hand-off point from the deterministic pipeline to the
    reporting layer. It is serialisable, diffable and fully reproducible from
    its provenance records.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str
    schema_version: str = "1.0"
    items: tuple[Evidence, ...] = ()
    verdict: VerificationVerdict | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _unique_ids(self) -> EvidenceBundle:
        ids = [item.id for item in self.items]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate evidence ids in bundle: {sorted(duplicates)}")
        return self

    def __iter__(self) -> Iterator[Evidence]:  # type: ignore[override]
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, evidence_id: object) -> bool:
        return any(item.id == evidence_id for item in self.items)

    def get(self, evidence_id: str) -> Evidence | None:
        """Return the evidence item with this id, or ``None``."""
        return next((item for item in self.items if item.id == evidence_id), None)

    def require(self, evidence_id: str) -> Evidence:
        """Return the evidence item with this id, or raise."""
        item = self.get(evidence_id)
        if item is None:
            raise KeyError(f"evidence {evidence_id!r} not present in bundle {self.case_id!r}")
        return item

    def numeric_values(self) -> dict[str, float]:
        """Every numeric value in the bundle, keyed by evidence id.

        Used by the grounding verifier to check that narrated figures exist.
        """
        return {item.id: float(item.value) for item in self.items if item.is_numeric}

    def with_items(self, *new_items: Evidence) -> EvidenceBundle:
        """Return a new bundle with additional evidence appended."""
        return self.model_copy(update={"items": self.items + new_items})

    def with_verdict(self, verdict: VerificationVerdict) -> EvidenceBundle:
        """Return a new bundle carrying the given verdict."""
        return self.model_copy(update={"verdict": verdict})

    def with_warning(self, warning: str) -> EvidenceBundle:
        """Return a new bundle with an additional analyst-facing warning."""
        return self.model_copy(update={"warnings": (*self.warnings, warning)})

    def to_json(self, indent: int = 2) -> str:
        """Serialise the bundle to JSON for archiving or diffing."""
        return json.dumps(self.model_dump(mode="json"), indent=indent, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> EvidenceBundle:
        """Reconstruct a bundle from its JSON serialisation."""
        return cls.model_validate(json.loads(payload))


class EvidenceBuilder:
    """Accumulates evidence items during a pipeline run.

    Using a builder keeps the pipeline stages from mutating a shared bundle,
    while still producing one immutable artefact at the end.
    """

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self._items: list[Evidence] = []
        self._warnings: list[str] = []

    def add(
        self,
        evidence_id: str,
        label: str,
        value: float | int | str | bool,
        *,
        unit: str = "",
        provenance: Provenance,
        confidence: Confidence | None = None,
        qualifiers: dict[str, Any] | None = None,
    ) -> Evidence:
        """Record one evidence item and return it."""
        item = Evidence(
            id=evidence_id,
            label=label,
            value=value,
            unit=unit,
            confidence=confidence,
            provenance=provenance,
            qualifiers=qualifiers or {},
        )
        self._items.append(item)
        return item

    def warn(self, message: str) -> None:
        """Record an analyst-facing warning about this run."""
        self._warnings.append(message)

    def build(self, verdict: VerificationVerdict | None = None) -> EvidenceBundle:
        """Freeze the accumulated items into an :class:`EvidenceBundle`."""
        return EvidenceBundle(
            case_id=self.case_id,
            items=tuple(self._items),
            verdict=verdict,
            warnings=tuple(self._warnings),
        )
