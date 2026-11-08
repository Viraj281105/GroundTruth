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


class ClaimVerificationStatus(StrEnum):
    """Verification outcome for a quantitative developer claim against an evidence bundle."""

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ClaimVerificationRecord:
    """Structured verification result linking a claim to bundle evidence."""

    claim: Claim
    status: ClaimVerificationStatus
    evidence_id: str | None
    observed_value: float | None
    observed_unit: str | None
    relative_difference: float | None
    rationale: str


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


def _get_bundle_item(bundle: Any, item_id: str) -> Any | None:
    if hasattr(bundle, "get") and callable(bundle.get):
        item = bundle.get(item_id)
        if item is not None:
            return item
    for item in getattr(bundle, "items", ()):
        if getattr(item, "id", None) == item_id:
            return item
    return None


def _is_robustness_inconclusive(bundle: Any) -> bool:
    verdict = getattr(bundle, "verdict", None)
    if verdict is None:
        return False
    label = getattr(verdict, "label", verdict)
    label_val = getattr(label, "value", str(label)).lower()
    if label_val != "inconclusive":
        return False
    rationale = (getattr(verdict, "rationale", "") or "").lower()
    return not any(k in rationale for k in ("not calibrated", "commensurable", "no validated"))


def _extract_area_evidence(bundle: Any) -> tuple[str, float, str] | None:
    area_item = _get_bundle_item(bundle, "claim.project_area_ha")
    if area_item is not None and isinstance(area_item.value, (int, float)) and not isinstance(
        area_item.value, bool
    ):
        return (
            "claim.project_area_ha",
            float(area_item.value),
            getattr(area_item, "unit", "") or "ha",
        )

    for candidate_id in ("carbon.estimated_tco2e", "biomass.delta_agb_t_per_ha"):
        item = _get_bundle_item(bundle, candidate_id)
        if item is None:
            continue
        qualifiers = getattr(item, "qualifiers", None) or {}
        area_val = qualifiers.get("area_ha")
        if area_val is None:
            prov = getattr(item, "provenance", None)
            params = getattr(prov, "parameters", None) or {}
            area_val = params.get("area_ha")
        if isinstance(area_val, (int, float)) and not isinstance(area_val, bool):
            return (candidate_id, float(area_val), "ha")

    return None


def verify_claims_against_bundle(
    claims: list[Claim], bundle: Any
) -> list[ClaimVerificationRecord]:
    """Verify extracted quantitative claims against an :class:`EvidenceBundle`."""
    records: list[ClaimVerificationRecord] = []
    for claim in claims:
        if claim.kind in (ClaimKind.CREDITS_ISSUED, ClaimKind.BASELINE):
            carbon_item = _get_bundle_item(bundle, "carbon.estimated_tco2e")
            if (
                carbon_item is None
                or isinstance(carbon_item.value, bool)
                or not isinstance(carbon_item.value, (int, float))
            ):
                if _is_robustness_inconclusive(bundle):
                    status = ClaimVerificationStatus.INSUFFICIENT_EVIDENCE
                    rationale = (
                        "The screening verdict is inconclusive due to failed robustness gates, "
                        "and no calibrated biomass model (`carbon.estimated_tco2e`) is available "
                        "in the bundle; NDVI is not carbon and cannot verify tCO2e credit claims."
                    )
                else:
                    status = ClaimVerificationStatus.NOT_VERIFIABLE
                    rationale = (
                        "NDVI is not carbon and no calibrated biomass model "
                        "(`carbon.estimated_tco2e`) is available in the bundle to verify "
                        "tCO2e credit claims."
                    )
                records.append(
                    ClaimVerificationRecord(
                        claim=claim,
                        status=status,
                        evidence_id=None,
                        observed_value=None,
                        observed_unit=None,
                        relative_difference=None,
                        rationale=rationale,
                    )
                )
                continue

            observed = float(carbon_item.value)
            observed_unit = getattr(carbon_item, "unit", "") or "tCO2e"
            scale = max(abs(claim.value), abs(observed))
            rel = abs(claim.value - observed) / scale if scale else 0.0
            if rel <= 0.10:
                status = ClaimVerificationStatus.SUPPORTED
                verdict_desc = "is supported by"
            elif rel <= 0.30:
                status = ClaimVerificationStatus.PARTIALLY_SUPPORTED
                verdict_desc = "is partially supported by"
            else:
                status = ClaimVerificationStatus.CONTRADICTED
                verdict_desc = "diverges from"

            records.append(
                ClaimVerificationRecord(
                    claim=claim,
                    status=status,
                    evidence_id="carbon.estimated_tco2e",
                    observed_value=observed,
                    observed_unit=observed_unit,
                    relative_difference=rel,
                    rationale=(
                        f"Claimed {claim.kind.value} ({claim.value:g} {claim.unit}) {verdict_desc} "
                        f"the calibration-conditional carbon estimate "
                        f"({observed:g} {observed_unit}; relative difference {rel:.1%})."
                    ),
                )
            )

        elif claim.kind is ClaimKind.AREA_HECTARES:
            area_evidence = _extract_area_evidence(bundle)
            if area_evidence is None:
                records.append(
                    ClaimVerificationRecord(
                        claim=claim,
                        status=ClaimVerificationStatus.INSUFFICIENT_EVIDENCE,
                        evidence_id=None,
                        observed_value=None,
                        observed_unit=None,
                        relative_difference=None,
                        rationale=(
                            "No project area evidence (`claim.project_area_ha` or `area_ha` "
                            "qualifier on `carbon.estimated_tco2e`) is present in the bundle."
                        ),
                    )
                )
                continue

            ev_id, observed, observed_unit = area_evidence
            scale = max(abs(claim.value), abs(observed))
            rel = abs(claim.value - observed) / scale if scale else 0.0
            if rel <= 0.05:
                status = ClaimVerificationStatus.SUPPORTED
            elif rel <= 0.20:
                status = ClaimVerificationStatus.PARTIALLY_SUPPORTED
            else:
                status = ClaimVerificationStatus.CONTRADICTED

            records.append(
                ClaimVerificationRecord(
                    claim=claim,
                    status=status,
                    evidence_id=ev_id,
                    observed_value=observed,
                    observed_unit=observed_unit,
                    relative_difference=rel,
                    rationale=(
                        f"Claimed area ({claim.value:g} {claim.unit}) compared against "
                        f"`{ev_id}` ({observed:g} {observed_unit}; relative difference {rel:.1%})."
                    ),
                )
            )

        elif claim.kind is ClaimKind.REDUCTION_PERCENT:
            pct_item = _get_bundle_item(bundle, "effect.reduction_percent") or _get_bundle_item(
                bundle, "reduction_pct"
            )
            if (
                pct_item is None
                or isinstance(pct_item.value, bool)
                or not isinstance(pct_item.value, (int, float))
            ):
                records.append(
                    ClaimVerificationRecord(
                        claim=claim,
                        status=ClaimVerificationStatus.NOT_VERIFIABLE,
                        evidence_id=None,
                        observed_value=None,
                        observed_unit=None,
                        relative_difference=None,
                        rationale=(
                            "No commensurable percentage reduction evidence exists in the bundle; "
                            "spectral index deltas cannot verify percentage emission reductions."
                        ),
                    )
                )
                continue

            observed = float(pct_item.value)
            observed_unit = getattr(pct_item, "unit", "") or "percent"
            scale = max(abs(claim.value), abs(observed))
            rel = abs(claim.value - observed) / scale if scale else 0.0
            if rel <= 0.10:
                status = ClaimVerificationStatus.SUPPORTED
            elif rel <= 0.30:
                status = ClaimVerificationStatus.PARTIALLY_SUPPORTED
            else:
                status = ClaimVerificationStatus.CONTRADICTED
            records.append(
                ClaimVerificationRecord(
                    claim=claim,
                    status=status,
                    evidence_id=getattr(pct_item, "id", "effect.reduction_percent"),
                    observed_value=observed,
                    observed_unit=observed_unit,
                    relative_difference=rel,
                    rationale=(
                        f"Claimed reduction ({claim.value:g} {claim.unit}) compared against "
                        f"observed percentage change ({observed:g} {observed_unit}; "
                        f"relative difference {rel:.1%})."
                    ),
                )
            )

    return records
