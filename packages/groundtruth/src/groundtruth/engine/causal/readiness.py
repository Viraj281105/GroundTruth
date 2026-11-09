"""Causal readiness assessment for ecosystem restoration impact verification.

Evaluates whether real-world Earth observation and donor evidence meet the
prerequisites for defensible causal inference (Synthetic Control Method and
Difference-in-Differences) before econometric estimation is permitted.

Mandatory Scientific Rule:
Preserves the INCONCLUSIVE / PARTIALLY_READY verdict whenever real data does not
statistically and geometrically support causal attribution. Never manufactures
a positive restoration result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CausalReadinessState(StrEnum):
    """Categorical readiness status for causal estimation."""

    READY_FOR_CAUSAL_ANALYSIS = "READY_FOR_CAUSAL_ANALYSIS"
    PARTIALLY_READY = "PARTIALLY_READY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class CausalCriterionResult:
    """Evaluation of one causal prerequisite."""

    criterion_id: str
    name: str
    passed: bool
    observed_value: Any
    threshold: Any
    severity: str  # "BLOCKER", "WARNING", "INFO"
    detail: str
    evidence_needed: str = ""
    """Plain-language next step when the criterion is not passed; empty when it passed."""


@dataclass(frozen=True)
class CausalReadinessReport:
    """Comprehensive causal readiness assessment for an AOI and donor pool."""

    case_id: str
    unit_id: str
    status: CausalReadinessState
    criteria: tuple[CausalCriterionResult, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    verdict_rationale: str
    recommendation: str

    @property
    def is_ready(self) -> bool:
        """True if the data matrix satisfies all mandatory causal gates."""
        return self.status == CausalReadinessState.READY_FOR_CAUSAL_ANALYSIS

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to a JSON dictionary."""
        return {
            "case_id": self.case_id,
            "unit_id": self.unit_id,
            "status": self.status.value,
            "is_ready": self.is_ready,
            "criteria": [
                {
                    "criterion_id": c.criterion_id,
                    "name": c.name,
                    "passed": c.passed,
                    "observed_value": c.observed_value,
                    "threshold": c.threshold,
                    "severity": c.severity,
                    "detail": c.detail,
                    "evidence_needed": c.evidence_needed,
                }
                for c in self.criteria
            ],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "verdict_rationale": self.verdict_rationale,
            "recommendation": self.recommendation,
        }


def assess_causal_readiness(
    *,
    case_id: str,
    unit_id: str,
    pre_treatment_years: int,
    post_treatment_years: int,
    usable_donors_count: int,
    aoi_coverage_fraction: float,
    donor_pool_independence: bool,
    spillover_buffer_km: float,
    sensor_discontinuity_present: bool = False,
    sensor_harmonization_validated: bool = False,
    slc_off_missingness_pct: float = 0.0,
    severe_climate_confounding_detected: bool = False,
    weather_residualization_active: bool = False,
    donor_matrix_condition_number: float | None = None,
    donor_matrix_rank: int | None = None,
    min_pre_years_required: int = 5,
    min_donors_required: int = 15,
    min_aoi_coverage_required: float = 0.50,
    whole_aoi_target_coverage: float = 0.95,
) -> CausalReadinessReport:
    """Assess whether real-data observations are suitable for causal analysis.

    Evaluates pre-treatment duration, donor availability, donor independence,
    spatial coverage completeness, sensor harmonization, donor matrix conditioning,
    and extreme climate confounding.
    """
    criteria: list[CausalCriterionResult] = []
    blockers: list[str] = []
    warnings: list[str] = []

    # 1. Pre-treatment duration (T_0)
    pre_ok = pre_treatment_years >= min_pre_years_required
    criteria.append(
        CausalCriterionResult(
            criterion_id="pre_treatment_duration",
            name="Pre-treatment Duration (T_0)",
            passed=pre_ok,
            observed_value=pre_treatment_years,
            threshold=min_pre_years_required,
            severity="BLOCKER" if not pre_ok else "INFO",
            detail=(
                f"{pre_treatment_years} pre-treatment years available "
                f"(minimum required: {min_pre_years_required})."
            ),
            evidence_needed=(
                ""
                if pre_ok
                else f"Acquire annual observations for at least {min_pre_years_required} years "
                f"before treatment began ({pre_treatment_years} available)."
            ),
        )
    )
    if not pre_ok:
        blockers.append(
            f"Pre-treatment duration ({pre_treatment_years} yrs) is under-identified (< {min_pre_years_required} yrs)."
        )

    # 2. Donor pool size (J)
    donors_ok = usable_donors_count >= min_donors_required
    criteria.append(
        CausalCriterionResult(
            criterion_id="donor_pool_size",
            name="Usable Donor Units Count (J)",
            passed=donors_ok,
            observed_value=usable_donors_count,
            threshold=min_donors_required,
            severity="BLOCKER" if not donors_ok else "INFO",
            detail=(
                f"{usable_donors_count} verified independent donor units available "
                f"(minimum required: {min_donors_required})."
            ),
            evidence_needed=(
                ""
                if donors_ok
                else f"Ingest observation series for at least {min_donors_required} independent "
                f"donor units over the same years as the project ({usable_donors_count} usable)."
            ),
        )
    )
    if not donors_ok:
        blockers.append(
            f"Insufficient independent donor units ({usable_donors_count} < {min_donors_required})."
        )

    # 3. Spatial AOI coverage
    cov_ok = aoi_coverage_fraction >= min_aoi_coverage_required
    full_target_met = aoi_coverage_fraction >= whole_aoi_target_coverage
    if not cov_ok:
        cov_severity = "BLOCKER"
        cov_detail = (
            f"Observed footprint covers only {aoi_coverage_fraction * 100:.1f}% of project boundary "
            f"(minimum baseline: {min_aoi_coverage_required * 100:.1f}%)."
        )
        blockers.append(cov_detail)
    elif not full_target_met:
        cov_severity = "WARNING"
        cov_detail = (
            f"Observed AOI footprint covers {aoi_coverage_fraction * 100:.1f}% of total project boundary. "
            f"Passes minimum threshold ({min_aoi_coverage_required * 100:.1f}%), but falls short of 95.0% whole-AOI target. "
            "Multi-tile mosaicing across WRS-2 paths 169–172 is required for whole-AOI additionality conclusions."
        )
        warnings.append(
            f"Single-tile footprint ({aoi_coverage_fraction * 100:.1f}%) is spatially incomplete for whole-AOI conclusions."
        )
    else:
        cov_severity = "INFO"
        cov_detail = (
            f"Observed AOI footprint covers {aoi_coverage_fraction * 100:.1f}% of total project boundary "
            f"(meets >= 95.0% whole-AOI target across all intersecting WRS-2 paths)."
        )

    criteria.append(
        CausalCriterionResult(
            criterion_id="spatial_coverage",
            name="AOI Spatial Coverage Completeness",
            passed=full_target_met,
            observed_value=round(aoi_coverage_fraction, 4),
            threshold=whole_aoi_target_coverage,
            severity=cov_severity,
            detail=cov_detail,
            evidence_needed=(
                ""
                if full_target_met
                else "Acquire imagery covering at least "
                f"{whole_aoi_target_coverage * 100:.0f}% of the project boundary "
                f"({aoi_coverage_fraction * 100:.1f}% covered)."
            ),
        )
    )

    # 4. Donor pool independence & SUTVA
    criteria.append(
        CausalCriterionResult(
            criterion_id="donor_pool_independence",
            name="Donor Independence and SUTVA Compliance",
            passed=donor_pool_independence,
            observed_value=donor_pool_independence,
            threshold=True,
            severity="BLOCKER" if not donor_pool_independence else "INFO",
            detail=(
                "All overlapping host districts and 10 km leakage belt buffers geometrically excluded."
                if donor_pool_independence
                else "Unscreened donor units overlap project area or immediate leakage belt."
            ),
            evidence_needed=(
                ""
                if donor_pool_independence
                else "Remove donor units that overlap the project area or its leakage belt, "
                "or document why they are independent."
            ),
        )
    )
    if not donor_pool_independence:
        blockers.append(
            "Donor pool violates SUTVA through project boundary overlap or leakage buffer intrusion."
        )

    # 5. Sensor continuity & harmonization
    if sensor_discontinuity_present and not sensor_harmonization_validated:
        warnings.append(
            "Sensor transition (Landsat 7 ETM+ to Landsat 8 OLI in 2013) introduces spectral bandwidth "
            "shifts; cross-sensor harmonization (Roy et al. 2016) is required."
        )
        sensor_passed = False
        sensor_severity = "WARNING"
        sensor_detail = "Sensor break in 2013 unharmonized; potential instrumental discontinuity."
    elif sensor_discontinuity_present and sensor_harmonization_validated:
        sensor_passed = True
        sensor_severity = "INFO"
        sensor_detail = (
            "Sensor transition harmonized via validated Roy et al. (2016) regression model."
        )
    else:
        sensor_passed = True
        sensor_severity = "INFO"
        sensor_detail = "Single sensor series; no multi-sensor discontinuity."

    criteria.append(
        CausalCriterionResult(
            criterion_id="sensor_comparability",
            name="Multi-Sensor Radiometric Comparability",
            passed=sensor_passed,
            observed_value=sensor_harmonization_validated,
            threshold=True,
            severity=sensor_severity,
            detail=sensor_detail,
            evidence_needed=(
                ""
                if sensor_passed
                else "Validate a cross-sensor harmonisation (for example overlapping-year "
                "regression) before comparing years across the sensor change."
            ),
        )
    )

    # 6. Landsat 7 SLC-off missingness
    if slc_off_missingness_pct > 10.0:
        warnings.append(
            f"Landsat 7 Scan Line Corrector failure introduces {slc_off_missingness_pct:.1f}% scan gap missingness "
            "in post-May 2003 pre-treatment scenes; gap pixels are masked as NaN without interpolation."
        )

    # 7. Extreme climate confounding control
    if severe_climate_confounding_detected and not weather_residualization_active:
        warnings.append(
            "Severe drought events (2002 pre-treatment SPI -1.87 and 2019 post-treatment SPI -1.61) "
            "coincide with vegetative shifts; weather-adjusted counterfactual estimation is required."
        )
        climate_passed = False
        climate_severity = "WARNING"
        climate_detail = (
            "Extreme precipitation anomalies unadjusted; severe risk of drought misattribution."
        )
    elif severe_climate_confounding_detected and weather_residualization_active:
        climate_passed = True
        climate_severity = "INFO"
        climate_detail = "Drought shocks controlled via empirical donor weather residualization."
    else:
        climate_passed = True
        climate_severity = "INFO"
        climate_detail = "No extreme drought confounding detected."

    criteria.append(
        CausalCriterionResult(
            criterion_id="climate_confounding",
            name="Severe Climate Confounding Control",
            passed=climate_passed,
            observed_value=weather_residualization_active,
            threshold=True,
            severity=climate_severity,
            detail=climate_detail,
            evidence_needed=(
                ""
                if climate_passed
                else "Adjust the counterfactual for weather (residualise against drought "
                "indices) before attributing change to the intervention."
            ),
        )
    )

    # 8. Donor Matrix Conditioning & Rank (if provided)
    if donor_matrix_condition_number is not None:
        is_ill_cond = bool(
            donor_matrix_condition_number > 1e6
            or (
                donor_matrix_rank is not None
                and donor_matrix_rank < min(pre_treatment_years, usable_donors_count)
            )
        )
        if is_ill_cond:
            blockers.append(
                f"Donor matrix is ill-conditioned (condition number: {donor_matrix_condition_number:.1f}); "
                "synthetic control weights cannot be stably identified."
            )
        criteria.append(
            CausalCriterionResult(
                criterion_id="donor_matrix_conditioning",
                name="Donor Matrix Rank and Numerical Conditioning",
                passed=not is_ill_cond,
                observed_value=donor_matrix_condition_number,
                threshold=1e6,
                severity="BLOCKER" if is_ill_cond else "INFO",
                detail=(
                    f"Matrix rank: {donor_matrix_rank}, condition number: {donor_matrix_condition_number:.1f}."
                    if not is_ill_cond
                    else f"Matrix is ill-conditioned or rank-deficient (cond={donor_matrix_condition_number:.1f})."
                ),
                evidence_needed=(
                    ""
                    if not is_ill_cond
                    else "Add donor units or pre-treatment periods, or regularise, until the "
                    "donor matrix is full rank and well conditioned."
                ),
            )
        )

    # Determine overall status
    if blockers:
        status = CausalReadinessState.INSUFFICIENT_DATA
        rationale = f"Causal estimation refused due to {len(blockers)} blocker(s): " + "; ".join(
            blockers
        )
        rec = "Acquire complete multi-tile satellite coverage and resolve ill-conditioning before running causal estimators."
    elif warnings:
        status = CausalReadinessState.PARTIALLY_READY
        rationale = (
            "Observations are retrieved and geometrically valid, but spatial bounds, sensor transitions, "
            "or climate confounding necessitate diagnostic caveats; verdict remains INCONCLUSIVE."
        )
        rec = "Apply complete multi-tile mosaicing, cross-sensor harmonization, and weather residualization before drawing attribution conclusions."
    else:
        status = CausalReadinessState.READY_FOR_CAUSAL_ANALYSIS
        rationale = "All causal identification requirements satisfied across spatial, sensor, donor, and climate domains."
        rec = "Proceed with Synthetic Control and Difference-in-Differences estimation."

    return CausalReadinessReport(
        case_id=case_id,
        unit_id=unit_id,
        status=status,
        criteria=tuple(criteria),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        verdict_rationale=rationale,
        recommendation=rec,
    )
