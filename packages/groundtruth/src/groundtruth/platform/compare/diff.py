"""A per-evidence-id diff of two evidence bundles.

Bundles are addressed by evidence id (ADR-004), so "what changed between two analyses"
is a join on id: an id in only one bundle was added or removed, and an id in both is
unchanged or changed. This function says *what differs*. It does not say whether the
difference is meaningful, and it must not be called on two bundles that are not
comparable; :mod:`groundtruth.platform.compare.comparison` decides that first.

What counts as a change, per item: the ``value``, the ``unit``, the ``confidence``
interval (bounds, level and kind), the ``qualifiers``, and the ``provenance``
fingerprint (so a value that is the same but was derived differently is flagged). The
human-readable ``label`` is not compared: rewording a description is not a result.

Numbers are compared with a relative tolerance, because ADR-006 guarantees identical
output for the same engine, spec and seed but not bit-exact floating point across
machines. A difference inside the tolerance is reported as unchanged.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from groundtruth.contracts.evidence import Evidence, EvidenceBundle
from groundtruth.contracts.types import Confidence

DEFAULT_REL_TOL = 1e-9
"""Relative tolerance below which two numbers are the same number."""

ChangeStatus = Literal["added", "removed", "changed", "unchanged"]


class FieldChange(BaseModel):
    """One field of one evidence item that differs."""

    model_config = ConfigDict(frozen=True)

    field: str
    """``value``, ``unit``, ``confidence``, ``qualifiers`` or ``provenance``."""
    before: Any
    after: Any


class EvidenceSnapshot(BaseModel):
    """An evidence item as one side of the diff saw it."""

    model_config = ConfigDict(frozen=True)

    value: float | int | str | bool
    unit: str
    confidence: Confidence | None
    qualifiers: dict[str, Any]
    provenance_method: str
    provenance_fingerprint: str


class ItemDiff(BaseModel):
    """One evidence id across the two bundles."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    status: ChangeStatus
    baseline: EvidenceSnapshot | None
    candidate: EvidenceSnapshot | None
    changes: tuple[FieldChange, ...] = ()
    delta: float | None = None
    """``candidate - baseline`` when both values are numbers."""
    relative_delta: float | None = None
    """``delta / |baseline|``; ``None`` when the baseline is zero or not a number."""


class DiffSummary(BaseModel):
    """How many ids fall in each status."""

    model_config = ConfigDict(frozen=True)

    added: int
    removed: int
    changed: int
    unchanged: int


class VerdictDiff(BaseModel):
    """The screening verdicts side by side. Neutral by construction: it states the
    two labels and whether they differ, and ranks neither."""

    model_config = ConfigDict(frozen=True)

    baseline_label: str | None
    candidate_label: str | None
    label_changed: bool
    baseline_divergence_ratio: float | None
    candidate_divergence_ratio: float | None
    divergence_ratio_changed: bool
    rationale_changed: bool


class WarningsDiff(BaseModel):
    """Analyst-facing warnings that appear in only one bundle."""

    model_config = ConfigDict(frozen=True)

    added: tuple[str, ...]
    removed: tuple[str, ...]


class BundleDiff(BaseModel):
    """The difference between a baseline bundle and a candidate bundle."""

    model_config = ConfigDict(frozen=True)

    summary: DiffSummary
    items: tuple[ItemDiff, ...]
    """Every id in either bundle, sorted by id."""
    verdict: VerdictDiff
    warnings: WarningsDiff


def _is_number(value: object) -> bool:
    # bool is an int subclass, but True is not a measurement of 1.
    return isinstance(value, int | float) and not isinstance(value, bool)


def values_equal(a: Any, b: Any, rel_tol: float = DEFAULT_REL_TOL) -> bool:
    """Equality that treats numbers within ``rel_tol`` as the same number.

    Numbers compare as numbers (``1`` equals ``1.0``); a bool equals only a bool;
    two NaNs are equal because "no value" has not changed; containers compare
    element by element. Anything else must match exactly, type included.
    """
    if _is_number(a) and _is_number(b):
        if math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=0.0)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(values_equal(a[k], b[k], rel_tol) for k in a)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return len(a) == len(b) and all(
            values_equal(x, y, rel_tol) for x, y in zip(a, b, strict=True)
        )
    return type(a) is type(b) and bool(a == b)


def _confidence_equal(a: Confidence | None, b: Confidence | None, rel_tol: float) -> bool:
    if a is None or b is None:
        return a is b
    return (
        values_equal(a.lower, b.lower, rel_tol)
        and values_equal(a.upper, b.upper, rel_tol)
        and a.level == b.level
        and a.kind == b.kind
    )


def _snapshot(item: Evidence) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        value=item.value,
        unit=item.unit,
        confidence=item.confidence,
        qualifiers=dict(item.qualifiers),
        provenance_method=item.provenance.method,
        provenance_fingerprint=item.provenance.fingerprint(),
    )


def _field_changes(before: Evidence, after: Evidence, rel_tol: float) -> tuple[FieldChange, ...]:
    changes: list[FieldChange] = []
    if not values_equal(before.value, after.value, rel_tol):
        changes.append(FieldChange(field="value", before=before.value, after=after.value))
    if before.unit != after.unit:
        changes.append(FieldChange(field="unit", before=before.unit, after=after.unit))
    if not _confidence_equal(before.confidence, after.confidence, rel_tol):
        changes.append(
            FieldChange(
                field="confidence",
                before=before.confidence.model_dump() if before.confidence else None,
                after=after.confidence.model_dump() if after.confidence else None,
            )
        )
    if not values_equal(before.qualifiers, after.qualifiers, rel_tol):
        changes.append(
            FieldChange(field="qualifiers", before=before.qualifiers, after=after.qualifiers)
        )
    if before.provenance.fingerprint() != after.provenance.fingerprint():
        changes.append(
            FieldChange(
                field="provenance",
                before={
                    "method": before.provenance.method,
                    "fingerprint": before.provenance.fingerprint(),
                },
                after={
                    "method": after.provenance.method,
                    "fingerprint": after.provenance.fingerprint(),
                },
            )
        )
    return tuple(changes)


def _deltas(before: Evidence, after: Evidence) -> tuple[float | None, float | None]:
    if not (before.is_numeric and after.is_numeric):
        return None, None
    delta = float(after.value) - float(before.value)
    relative = delta / abs(float(before.value)) if float(before.value) != 0.0 else None
    return delta, relative


def _verdict_diff(
    baseline: EvidenceBundle, candidate: EvidenceBundle, rel_tol: float
) -> VerdictDiff:
    a, b = baseline.verdict, candidate.verdict
    ratio_a = a.divergence_ratio if a else None
    ratio_b = b.divergence_ratio if b else None
    return VerdictDiff(
        baseline_label=a.label.value if a else None,
        candidate_label=b.label.value if b else None,
        label_changed=(a.label if a else None) != (b.label if b else None),
        baseline_divergence_ratio=ratio_a,
        candidate_divergence_ratio=ratio_b,
        divergence_ratio_changed=not (
            (ratio_a is None and ratio_b is None)
            or (
                ratio_a is not None
                and ratio_b is not None
                and values_equal(ratio_a, ratio_b, rel_tol)
            )
        ),
        rationale_changed=(a.rationale if a else None) != (b.rationale if b else None),
    )


def diff_bundles(
    baseline: EvidenceBundle, candidate: EvidenceBundle, *, rel_tol: float = DEFAULT_REL_TOL
) -> BundleDiff:
    """Diff two bundles by evidence id.

    Args:
        baseline: The earlier, or reference, bundle.
        candidate: The bundle being compared against it.
        rel_tol: Relative tolerance for numbers.
    """
    before = {item.id: item for item in baseline}
    after = {item.id: item for item in candidate}
    items: list[ItemDiff] = []
    for evidence_id in sorted(before.keys() | after.keys()):
        a, b = before.get(evidence_id), after.get(evidence_id)
        if a is None and b is not None:
            items.append(
                ItemDiff(
                    id=evidence_id,
                    label=b.label,
                    status="added",
                    baseline=None,
                    candidate=_snapshot(b),
                )
            )
        elif b is None and a is not None:
            items.append(
                ItemDiff(
                    id=evidence_id,
                    label=a.label,
                    status="removed",
                    baseline=_snapshot(a),
                    candidate=None,
                )
            )
        elif a is not None and b is not None:
            changes = _field_changes(a, b, rel_tol)
            delta, relative = _deltas(a, b)
            items.append(
                ItemDiff(
                    id=evidence_id,
                    label=b.label,
                    status="changed" if changes else "unchanged",
                    baseline=_snapshot(a),
                    candidate=_snapshot(b),
                    changes=changes,
                    delta=delta,
                    relative_delta=relative,
                )
            )
    counts = {status: sum(1 for i in items if i.status == status) for status in _STATUSES}
    return BundleDiff(
        summary=DiffSummary(**counts),
        items=tuple(items),
        verdict=_verdict_diff(baseline, candidate, rel_tol),
        warnings=WarningsDiff(
            added=tuple(w for w in candidate.warnings if w not in baseline.warnings),
            removed=tuple(w for w in baseline.warnings if w not in candidate.warnings),
        ),
    )


_STATUSES: tuple[ChangeStatus, ...] = ("added", "removed", "changed", "unchanged")
