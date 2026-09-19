"""The verification pipeline orchestrator.

Wires the stages together in one direction:

    ingest -> observe -> match -> estimate -> test -> assemble -> report

Each stage depends only on the protocol of the one before it, so a provider can
be swapped without touching the orchestration. The orchestrator itself contains
no statistics and no prose: it is plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from groundtruth.cases.registry import CaseDefinition
from groundtruth.causal.did import estimate_did
from groundtruth.causal.synthetic_control import fit_synthetic_control
from groundtruth.core.errors import EstimationError, InsufficientDataError
from groundtruth.core.evidence import EvidenceBundle
from groundtruth.core.types import INDICATOR_UNITS, TimeSeries
from groundtruth.evidence.assembler import AssemblyInputs, assemble_evidence
from groundtruth.ingestion.base import (
    AreaOfInterest,
    CovariateProvider,
    DonorPoolProvider,
    ObservationProvider,
    ObservationRequest,
)
from groundtruth.logging import get_logger
from groundtruth.matching.donors import DonorPool, MatchingConfig, match_donors
from groundtruth.reporting.narrative import Report, generate_report
from groundtruth.uncertainty.placebo import in_space_placebo
from groundtruth.uncertainty.robustness import leave_one_out

logger = get_logger("pipeline")


@dataclass
class PipelineConfig:
    """Knobs that control a pipeline run."""

    min_donors: int = 10
    max_donors: int = 50
    min_pre_periods: int = 5
    ridge: float = 0.0
    run_placebo: bool = True
    run_leave_one_out: bool = True
    run_did_crosscheck: bool = True


@dataclass(frozen=True)
class PipelineResult:
    """Everything a run produced, for the API, CLI and experiment harness."""

    case_id: str
    bundle: EvidenceBundle
    report: Report
    donor_pool: DonorPool
    project_series: TimeSeries
    donor_series: tuple[TimeSeries, ...]


def _observe(
    provider: ObservationProvider, area: AreaOfInterest, case: CaseDefinition
) -> TimeSeries:
    request = ObservationRequest(
        area=area,
        indicator=case.indicator,
        start_period=case.window.pre_start,
        end_period=case.window.post_end,
    )
    return provider.fetch(request)


def run_verification(
    case: CaseDefinition,
    observation_provider: ObservationProvider,
    covariate_provider: CovariateProvider,
    donor_pool_provider: DonorPoolProvider,
    *,
    config: PipelineConfig | None = None,
    narrator: object | None = None,
) -> PipelineResult:
    """Run the full verification pipeline for one case.

    Raises:
        InsufficientDataError: if observation coverage is too thin to estimate.
        DonorPoolError: if no admissible donor pool can be constructed.
        EstimationError: if the estimator cannot be fitted.
    """
    cfg = config or PipelineConfig()
    project_area = AreaOfInterest(unit_id=case.case_id)

    logger.info("observing project", extra={"case_id": case.case_id, "stage": "ingestion"})
    project_series = _observe(observation_provider, project_area, case)

    candidates = donor_pool_provider.candidates(project_area, case.donor_pool_size)
    if not candidates:
        raise InsufficientDataError(
            f"donor pool provider returned no candidates for {case.case_id}"
        )

    donor_series_by_id: dict[str, TimeSeries] = {}
    candidate_covariates: dict[str, dict[str, float]] = {}
    for area in candidates:
        donor_series_by_id[area.unit_id] = _observe(observation_provider, area, case)
        candidate_covariates[area.unit_id] = covariate_provider.covariates(area)

    logger.info(
        "matching donors",
        extra={"case_id": case.case_id, "stage": "matching", "n_donors": len(candidates)},
    )
    matching_config = MatchingConfig(
        covariates=case.covariates or MatchingConfig().covariates,
        max_donors=cfg.max_donors,
        min_donors=cfg.min_donors,
        excluded_unit_ids=frozenset(case.excluded_donor_ids),
    )
    pool = match_donors(
        case.case_id,
        covariate_provider.covariates(project_area),
        candidate_covariates,
        matching_config,
    )

    donor_ids = pool.unit_ids
    donor_matrix = np.column_stack([donor_series_by_id[uid].as_array() for uid in donor_ids])
    treated = project_series.as_array()
    n_pre = case.window.n_pre_periods

    logger.info(
        "fitting synthetic control",
        extra={"case_id": case.case_id, "stage": "causal", "estimator": "synthetic-control"},
    )
    fit = fit_synthetic_control(
        treated,
        donor_matrix,
        donor_ids,
        n_pre,
        ridge=cfg.ridge,
        min_pre_periods=cfg.min_pre_periods,
    )

    placebo = None
    if cfg.run_placebo:
        try:
            full_matrix = np.column_stack([treated, donor_matrix])
            placebo = in_space_placebo(
                full_matrix,
                (case.case_id, *donor_ids),
                0,
                n_pre,
                ridge=cfg.ridge,
                min_pre_periods=cfg.min_pre_periods,
            )
        except (EstimationError, InsufficientDataError) as exc:
            logger.warning("placebo inference unavailable: %s", exc)

    loo = None
    if cfg.run_leave_one_out:
        loo = leave_one_out(
            treated,
            donor_matrix,
            donor_ids,
            n_pre,
            baseline_effect=fit.average_effect,
            only_contributing=fit.contributing_donors(),
            min_pre_periods=cfg.min_pre_periods,
        )

    did = None
    if cfg.run_did_crosscheck:
        try:
            did = estimate_did(treated, donor_matrix, n_pre)
        except (EstimationError, InsufficientDataError) as exc:
            logger.warning("difference-in-differences cross-check unavailable: %s", exc)

    inputs = AssemblyInputs(
        claim=case.claim,
        indicator=case.indicator,
        indicator_unit=INDICATOR_UNITS[case.indicator],
        donor_pool=pool,
        fit=fit,
        placebo=placebo,
        leave_one_out=loo,
        did=did,
        data_provenance=observation_provider.provenance(
            ObservationRequest(
                area=project_area,
                indicator=case.indicator,
                start_period=case.window.pre_start,
                end_period=case.window.post_end,
            )
        ),
        treatment_period=case.window.post_start,
    )

    # No divergence ratio is passed: comparing a spectral-index effect against a
    # tCO2e claim requires a biomass conversion step that is not implemented.
    # See docs/05-causal-inference.md.
    bundle = assemble_evidence(inputs, divergence_ratio=None, min_donors=cfg.min_donors)
    report = generate_report(bundle, narrator=narrator)

    return PipelineResult(
        case_id=case.case_id,
        bundle=bundle,
        report=report,
        donor_pool=pool,
        project_series=project_series,
        donor_series=tuple(donor_series_by_id[uid] for uid in donor_ids),
    )
