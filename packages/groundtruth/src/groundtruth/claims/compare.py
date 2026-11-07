"""Compare document claims with an analysis result.

Wording is deliberately neutral: a discrepancy means two figures differ and the
difference warrants review. It does not say why, and carries no legal meaning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from groundtruth.claims.extract import Claim, ClaimKind


class Severity(StrEnum):
    """How far apart the two figures are."""

    MINOR = "minor"
    NOTABLE = "notable"
    LARGE = "large"


@dataclass(frozen=True)
class Discrepancy:
    """A difference between a documented figure and the analysis figure."""

    kind: ClaimKind
    claimed: float
    observed: float
    relative_difference: float
    severity: Severity
    citation: str
    message: str


# AnalysisResult-like dict key for each claim kind.
RESULT_KEYS: dict[ClaimKind, str] = {
    ClaimKind.BASELINE: "baseline",
    ClaimKind.CREDITS_ISSUED: "credits_issued",
    ClaimKind.AREA_HECTARES: "area_ha",
    ClaimKind.REDUCTION_PERCENT: "reduction_pct",
}


def _severity(rel: float) -> Severity:
    if rel >= 0.5:
        return Severity.LARGE
    if rel >= 0.2:
        return Severity.NOTABLE
    return Severity.MINOR


def compare_claims(
    claims: list[Claim], result: Mapping[str, Any], tolerance: float = 0.05
) -> list[Discrepancy]:
    """Return a record for each claim differing from ``result`` by more than ``tolerance``.

    Claims whose kind has no numeric entry in ``result`` are skipped, not flagged.
    """
    out: list[Discrepancy] = []
    for claim in claims:
        raw = result.get(RESULT_KEYS[claim.kind])
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        observed = float(raw)
        scale = max(abs(claim.value), abs(observed))
        rel = abs(claim.value - observed) / scale if scale else 0.0
        if rel <= tolerance:
            continue
        label = claim.kind.value.replace("_", " ")
        out.append(
            Discrepancy(
                kind=claim.kind,
                claimed=claim.value,
                observed=observed,
                relative_difference=rel,
                severity=_severity(rel),
                citation=claim.citation(),
                message=(
                    f"The documented {label} ({claim.value:g} {claim.unit}) differs from the "
                    f"independent estimate ({observed:g}). The difference may reflect "
                    f"definitions, scope or data; it is flagged for review at {claim.citation()}."
                ),
            )
        )
    return out
