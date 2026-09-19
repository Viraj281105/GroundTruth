"""The analytical engine entrypoint.

    AnalysisRequest  ->  run_analysis  ->  AnalysisResult

One function. The platform calls it and never reaches past it. Everything else
under ``groundtruth.engine`` is private to the engine and may be restructured
without touching the platform.

The engine is a pure computational module:

- it reads nothing but its request and its data ports;
- it writes nothing — no files, no database, no logs of record;
- it opens no sockets and reads no credentials;
- it is deterministic given a request, a seed and the same data;
- it returns a typed result for every domain outcome, including refusal.

Owner: Viraj. See ``OWNERSHIP.md``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import numpy as np

from groundtruth.contracts.errors import (
    DataUnavailableError,
    DonorPoolError,
    EstimationError,
    InsufficientDataError,
)
from groundtruth.contracts.identifiers import EngineRef, new_run_id
from groundtruth.contracts.ports import DataAccess, ObservationSpec
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import AnalysisRequest, UnitRef
from groundtruth.contracts.result import (
    AnalysisError,
    AnalysisResult,
    EngineStatus,
    ErrorCode,
    RunMetrics,
)
from groundtruth.contracts.types import INDICATOR_UNITS, TimeSeries
from groundtruth.contracts.version import CONTRACT_VERSION, is_compatible
from groundtruth.engine.assembler import AssemblyInputs, assemble_evidence
from groundtruth.engine.causal.did import estimate_did
from groundtruth.engine.causal.synthetic_control import fit_synthetic_control
from groundtruth.engine.matching.donors import MatchingConfig, match_donors
from groundtruth.engine.uncertainty.placebo import in_space_placebo
from groundtruth.engine.uncertainty.robustness import leave_one_out

ENGINE_VERSION = "0.3.0"
"""Version of the analytical engine. Bumped when results could change."""


def engine_ref(git_sha: str | None = None) -> EngineRef:
    """Identify this engine build, for the result's audit trail."""
    return EngineRef(
        engine_version=ENGINE_VERSION,
        contract_version=CONTRACT_VERSION,
        git_sha=git_sha,
    )


class _Stopwatch:
    """Accumulates per-stage timings for the result metrics."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.stages: dict[str, float] = {}
        self._mark = self.started

    def lap(self, stage: str) -> None:
        """Record elapsed time since the previous lap under ``stage``."""
        now = time.perf_counter()
        self.stages[stage] = (now - self._mark) * 1000.0
        self._mark = now

    @property
    def total_ms(self) -> float:
        """Total elapsed milliseconds."""
        return (time.perf_counter() - self.started) * 1000.0


def _observe(data: DataAccess, request: AnalysisRequest, unit: UnitRef) -> TimeSeries:
    return data.observations.series(
        ObservationSpec(
            unit=unit,
            indicator=request.indicator,
            start_period=request.window.pre_start,
            end_period=request.window.post_end,
        )
    )


def _failure(
    request: AnalysisRequest,
    run_id: str,
    code: ErrorCode,
    message: str,
    *,
    stage: str,
    detail: dict[str, Any] | None = None,
    remediation: str | None = None,
    started_at: str,
    metrics: RunMetrics,
    git_sha: str | None,
) -> AnalysisResult:
    """Build a typed failure result. The engine never raises for these."""
    return AnalysisResult(
        run_id=run_id,
        case_id=request.case_id,
        spec_hash=request.spec_hash,
        status=EngineStatus.REFUSED if code.is_refusal else EngineStatus.ERROR,
        engine=engine_ref(git_sha),
        datasets=request.datasets,
        seed=request.seed,
        data_mode=request.data_mode,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        error=AnalysisError(
            code=code,
            message=message,
            stage=stage,
            detail=detail or {},
            remediation=remediation,
        ),
        metrics=metrics,
    )


def run_analysis(
    request: AnalysisRequest,
    data: DataAccess,
    *,
    git_sha: str | None = None,
) -> AnalysisResult:
    """Run one analysis and return a typed result.

    Args:
        request: The complete, self-contained analysis specification.
        data: The platform's implementations of the engine's data ports.
        git_sha: Commit the run was executed from, recorded for reproducibility.

    Returns:
        An :class:`AnalysisResult`. ``EngineStatus.COMPLETED`` carries an
        evidence bundle; ``REFUSED`` and ``ERROR`` carry a structured
        :class:`AnalysisError`.

    Raises:
        Nothing for domain outcomes. Programming errors propagate, because a
        bug should fail loudly rather than be recorded as a scientific refusal.
    """
    run_id = new_run_id()
    started_at = datetime.now(UTC).isoformat()
    watch = _Stopwatch()
    metrics = RunMetrics()

    def fail(code: ErrorCode, message: str, **kwargs: Any) -> AnalysisResult:
        return _failure(
            request,
            run_id,
            code,
            message,
            started_at=started_at,
            metrics=metrics.model_copy(update={"duration_ms": watch.total_ms}),
            git_sha=git_sha,
            **kwargs,
        )

    if not is_compatible(request.contract_version):
        return fail(
            ErrorCode.CONTRACT_VERSION_MISMATCH,
            f"request targets contract {request.contract_version}, engine serves "
            f"{CONTRACT_VERSION}",
            stage="validation",
            remediation="Upgrade the platform or pin an engine build for that contract.",
        )

    # --- observe -----------------------------------------------------------
    try:
        project_series = _observe(data, request, request.project)

        candidates = list(request.donors.candidates)
        if not candidates:
            if data.donors is None:
                return fail(
                    ErrorCode.INVALID_REQUEST,
                    "no donor candidates were supplied and no donor access port is available",
                    stage="matching",
                    remediation="Resolve candidates in the platform, or provide a donor port.",
                )
            candidates = data.donors.candidates(request)

        if not candidates:
            return fail(
                ErrorCode.DONOR_POOL_INADEQUATE,
                f"no candidate control regions were found for {request.case_id}",
                stage="matching",
                remediation="Widen the donor search region.",
            )

        donor_series: dict[str, TimeSeries] = {}
        candidate_covariates: dict[str, dict[str, float]] = {}
        for unit in candidates:
            donor_series[unit.unit_id] = _observe(data, request, unit)
            candidate_covariates[unit.unit_id] = data.covariates.covariates(
                unit, request.donors.covariates
            )
        project_covariates = data.covariates.covariates(request.project, request.donors.covariates)
    except DataUnavailableError as exc:
        return fail(
            ErrorCode.DATA_UNAVAILABLE,
            str(exc),
            stage="ingestion",
            remediation="Check dataset availability and credentials, then retry.",
        )
    except NotImplementedError as exc:
        return fail(ErrorCode.NOT_IMPLEMENTED, str(exc), stage="ingestion")

    watch.lap("observation")
    metrics = metrics.model_copy(update={"n_units_observed": len(candidates) + 1})

    # --- match -------------------------------------------------------------
    try:
        pool = match_donors(
            request.case_id,
            project_covariates,
            candidate_covariates,
            MatchingConfig(
                covariates=request.donors.covariates,
                weights=dict(request.donors.covariate_weights),
                max_donors=request.donors.max_donors,
                min_donors=request.donors.min_donors,
                caliper_sd=request.donors.caliper_sd,
                excluded_unit_ids=frozenset(request.donors.excluded_unit_ids),
                min_pre_observations=request.donors.min_pre_observations,
            ),
        )
    except DonorPoolError as exc:
        return fail(
            ErrorCode.DONOR_POOL_INADEQUATE,
            str(exc),
            stage="matching",
            detail={
                "n_candidates": len(candidates),
                "min_donors_required": request.donors.min_donors,
            },
            remediation=(
                "Widen the donor search region or relax the common-support caliper. Do not "
                "lower min_donors to force a result."
            ),
        )

    watch.lap("matching")
    donor_ids = pool.unit_ids
    metrics = metrics.model_copy(update={"n_donors_admitted": len(donor_ids)})

    # --- estimate ----------------------------------------------------------
    treated = project_series.as_array()
    donor_matrix = np.column_stack([donor_series[uid].as_array() for uid in donor_ids])
    n_pre = request.window.n_pre_periods

    try:
        fit = fit_synthetic_control(
            treated,
            donor_matrix,
            donor_ids,
            n_pre,
            ridge=request.estimation.ridge,
            min_pre_periods=request.estimation.min_pre_periods,
        )
    except InsufficientDataError as exc:
        return fail(
            ErrorCode.INSUFFICIENT_DATA,
            str(exc),
            stage="causal",
            remediation="Extend the pre-treatment window, or accept that this case cannot "
            "be screened with this indicator.",
        )
    except EstimationError as exc:
        return fail(ErrorCode.ESTIMATION_FAILED, str(exc), stage="causal")

    watch.lap("estimation")
    n_fits = 1

    # --- robustness --------------------------------------------------------
    placebo = None
    if request.robustness.in_space_placebo:
        try:
            placebo = in_space_placebo(
                np.column_stack([treated, donor_matrix]),
                (request.case_id, *donor_ids),
                0,
                n_pre,
                ridge=request.estimation.ridge,
                max_pre_rmspe_multiple=request.robustness.max_placebo_pre_rmspe_multiple,
                min_pre_periods=request.estimation.min_pre_periods,
            )
            n_fits += len(donor_ids) + 1
        except (EstimationError, InsufficientDataError):
            placebo = None

    loo = None
    if request.robustness.leave_one_out:
        loo = leave_one_out(
            treated,
            donor_matrix,
            donor_ids,
            n_pre,
            baseline_effect=fit.average_effect,
            only_contributing=fit.contributing_donors(),
            min_pre_periods=request.estimation.min_pre_periods,
        )
        n_fits += len(loo.effects)

    did = None
    if any(m.model_id == "difference-in-differences" for m in request.estimation.cross_checks):
        try:
            did = estimate_did(treated, donor_matrix, n_pre)
            n_fits += 1
        except (EstimationError, InsufficientDataError):
            did = None

    watch.lap("robustness")

    # --- assemble ----------------------------------------------------------
    data_provenance = data.observations.provenance(
        ObservationSpec(
            unit=request.project,
            indicator=request.indicator,
            start_period=request.window.pre_start,
            end_period=request.window.post_end,
        )
    )
    bundle = assemble_evidence(
        AssemblyInputs(
            request=request,
            donor_pool=pool,
            fit=fit,
            placebo=placebo,
            leave_one_out=loo,
            did=did,
            data_provenance=data_provenance,
            indicator_unit=INDICATOR_UNITS[request.indicator],
        ),
        # No divergence ratio is passed: comparing a spectral-index effect to a
        # tCO2e claim requires a biomass conversion that does not exist yet.
        # See docs/05-causal-inference.md, "NDVI is not carbon".
        divergence_ratio=None,
        min_donors=request.donors.min_donors,
    )
    watch.lap("assembly")

    return AnalysisResult(
        run_id=run_id,
        case_id=request.case_id,
        spec_hash=request.spec_hash,
        status=EngineStatus.COMPLETED,
        engine=engine_ref(git_sha),
        datasets=request.datasets,
        seed=request.seed,
        data_mode=request.data_mode,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        bundle=bundle,
        metrics=RunMetrics(
            duration_ms=watch.total_ms,
            stage_durations_ms=watch.stages,
            n_units_observed=len(candidates) + 1,
            n_donors_admitted=len(donor_ids),
            n_estimator_fits=n_fits,
        ),
    )


def describe_engine() -> dict[str, Any]:
    """Machine-readable capability report.

    Served by the platform's health endpoint so the API can state what the
    engine can actually do without importing any of it.
    """
    return {
        "engine_version": ENGINE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "estimators": ["synthetic-control", "difference-in-differences"],
        "indicators": ["ndvi", "evi", "nbr", "tree_cover_fraction", "forest_area_ha"],
        "robustness": ["in-space-placebo", "in-time-placebo", "leave-one-out"],
        "implemented": {
            "synthetic_control": True,
            "placebo_inference": True,
            "leave_one_out": True,
            "specification_curve": False,
            "biomass_carbon_conversion": False,
        },
    }


__all__ = ["ENGINE_VERSION", "Provenance", "describe_engine", "engine_ref", "run_analysis"]
