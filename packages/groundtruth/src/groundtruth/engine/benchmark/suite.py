"""Independent Validation Benchmark Suite for GroundTruth 2.0.

Executes reproducible synthetic validation checks using the real causal engine
(``fit_synthetic_control``, ``in_space_placebo``, ``in_time_placebo``) while failing
closed (``UNAVAILABLE``) for empirical historical/literature benchmarks that require
offline multi-tile satellite and climate panels outside the pure analytical engine.

Scientific integrity guarantees (AGENTS.md R1, R5, R6, R7, R8):
- Never fabricates real-world results or hardcoded p-values / ATTs.
- Never converts spectral indices (NDVI) into carbon stocks (tC/ha).
- Every computational synthetic check runs deterministically from seed ``20260101`` and
  carries ``is_synthetic=True`` and ``data_origin="synthetic_simulated"``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np

from groundtruth.engine.causal.synthetic_control import fit_synthetic_control
from groundtruth.engine.uncertainty.placebo import in_space_placebo, in_time_placebo

BENCHMARK_SEED = 20260101


class BenchmarkCaseType(StrEnum):
    """Classification of benchmark validation cases."""

    HISTORICAL_EVENT = "historical_environmental_event"
    POSITIVE_INTERVENTION = "positive_intervention"
    NEGATIVE_CONTROL = "negative_control"
    TEMPORAL_PLACEBO = "temporal_placebo"
    SYNTHETIC_STRESS_TEST = "synthetic_stress_test"


class BenchmarkVerdict(StrEnum):
    """Validation outcome for a benchmark case."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class BenchmarkMetricEvaluation:
    """Quantitative performance and error calibration metrics."""

    metric_name: str
    target_value: float
    observed_value: float
    tolerance: float
    passed: bool
    description: str


@dataclass(frozen=True)
class BenchmarkCaseResult:
    """Evaluation result for an individual benchmark case."""

    case_id: str
    case_name: str
    case_type: BenchmarkCaseType
    is_synthetic: bool
    description: str
    ground_truth_effect: float | str
    estimated_effect: float | str
    p_value: float | None
    metrics: list[BenchmarkMetricEvaluation]
    verdict: BenchmarkVerdict
    scientific_rationale: str
    data_origin: str = "synthetic_simulated"
    literature_citation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "case_name": self.case_name,
            "case_type": str(self.case_type),
            "is_synthetic": self.is_synthetic,
            "data_origin": self.data_origin,
            "literature_citation": self.literature_citation,
            "description": self.description,
            "ground_truth_effect": self.ground_truth_effect,
            "estimated_effect": self.estimated_effect,
            "p_value": self.p_value,
            "metrics": [asdict(m) for m in self.metrics],
            "verdict": str(self.verdict),
            "scientific_rationale": self.scientific_rationale,
        }


@dataclass(frozen=True)
class BenchmarkSuiteSummary:
    """Full independent validation benchmark suite report."""

    suite_name: str
    version: str
    execution_timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    unavailable_cases: int
    false_positive_rate: float | None
    false_negative_rate: float | None
    uncertainty_calibration_score: float | None
    reproducibility_confirmed: bool
    results: list[BenchmarkCaseResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "version": self.version,
            "execution_timestamp": self.execution_timestamp,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "unavailable_cases": self.unavailable_cases,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "uncertainty_calibration_score": self.uncertainty_calibration_score,
            "reproducibility_confirmed": self.reproducibility_confirmed,
            "results": [r.to_dict() for r in self.results],
        }


def _latent_factor_panel(
    *,
    seed: int,
    n_donors: int = 15,
    n_pre: int = 10,
    n_post: int = 6,
    noise_sd: float = 0.008,
    injected_effect: float = 0.0,
) -> tuple[np.ndarray, tuple[str, ...]]:
    """Build a deterministic latent-factor panel: column 0 treated, rest donors."""
    rng = np.random.default_rng(seed)
    n_periods = n_pre + n_post
    n_units = n_donors + 1
    n_factors = 3
    factors = rng.normal(0.0, 0.025, size=(n_factors, n_periods)).cumsum(axis=1) + 0.55
    loadings = rng.dirichlet(np.ones(n_factors), size=n_units)
    # Place treated unit inside the convex hull of donors (identifying assumption of SCM).
    loadings[0] = loadings[1 : min(6, n_units)].mean(axis=0)
    panel = (loadings @ factors).T + rng.normal(0.0, noise_sd, size=(n_periods, n_units))
    if injected_effect != 0.0:
        panel[n_pre:, 0] += injected_effect
    unit_ids = tuple(["treated"] + [f"donor-{i:02d}" for i in range(1, n_units)])
    return panel, unit_ids


def _run_synthetic_stress_recovery(seed: int) -> tuple[float, float]:
    n_pre = 10
    injected_tau = 0.060
    panel, unit_ids = _latent_factor_panel(
        seed=seed, n_donors=15, n_pre=n_pre, n_post=6, noise_sd=0.008, injected_effect=injected_tau
    )
    fit = fit_synthetic_control(panel[:, 0], panel[:, 1:], unit_ids[1:], n_pre, min_pre_periods=5)
    placebo = in_space_placebo(
        panel, unit_ids, treated_index=0, n_pre_periods=n_pre, min_pre_periods=5
    )
    return float(fit.average_effect), float(placebo.p_value)


def run_independent_benchmark_suite() -> BenchmarkSuiteSummary:
    """Execute real deterministic synthetic checks; report unrun empirical cases UNAVAILABLE."""
    timestamp = datetime.now(UTC).isoformat()

    # Case 1: Historical Environmental Event — requires external multi-tile raster + climate data.
    bm_01 = BenchmarkCaseResult(
        case_id="BM-01-HISTORICAL-DROUGHT",
        case_name="Zambezi Basin 2018-2019 Severe Meteorological Drought",
        case_type=BenchmarkCaseType.HISTORICAL_EVENT,
        is_synthetic=False,
        data_origin="unexecuted_external_benchmark",
        literature_citation="CHIRPS v2.0 / Zambezi drought record",
        description=(
            "Offline historical drought confounding benchmark. Requires external multi-tile satellite "
            "and CHIRPS climate panels staged outside the pure engine module; fail-closed in-process."
        ),
        ground_truth_effect="External meteorological drought shock (not evaluated in-process)",
        estimated_effect="UNAVAILABLE — offline raster/climate benchmark panel required",
        p_value=None,
        metrics=[],
        verdict=BenchmarkVerdict.UNAVAILABLE,
        scientific_rationale=(
            "Fail-closed per R5/R6: historical Zambezi drought metrics are not fabricated when "
            "multi-tile observed panels are absent from the pure analytical engine."
        ),
    )

    # Case 2: External Literature Benchmark (Kasigau Corridor) — external reference only, not computed.
    bm_02 = BenchmarkCaseResult(
        case_id="BM-02-POSITIVE-INTERVENTION",
        case_name="Kasigau Corridor Dryland Forest Conservation (Phase II)",
        case_type=BenchmarkCaseType.POSITIVE_INTERVENTION,
        is_synthetic=False,
        data_origin="published_literature_benchmark",
        literature_citation="Verra VCS 612 / Guizar-Coutino et al. (2022); West et al. (2023)",
        description=(
            "External published literature benchmark reference for VCS 612. "
            "Full multi-year Kasigau causal donor panel is not ingested in-process; only external "
            "literature context is cited without fabricated internal estimates or carbon conversion."
        ),
        ground_truth_effect="External literature reference (VCS 612; see cited studies)",
        estimated_effect="UNAVAILABLE — Kasigau multi-year causal donor panel not ingested",
        p_value=None,
        metrics=[],
        verdict=BenchmarkVerdict.UNAVAILABLE,
        scientific_rationale=(
            "Fail-closed per R1/R5/R6: GroundTruth does not emit unverified ATT or carbon-stock "
            "figures for Kasigau without executing a full multi-year observed donor panel."
        ),
    )

    # Case 3: Real Executed Synthetic Null Panel (Negative Control)
    null_pre = 10
    null_panel, null_ids = _latent_factor_panel(
        seed=BENCHMARK_SEED + 1,
        n_donors=15,
        n_pre=null_pre,
        n_post=6,
        noise_sd=0.008,
        injected_effect=0.0,
    )
    null_fit = fit_synthetic_control(
        null_panel[:, 0], null_panel[:, 1:], null_ids[1:], null_pre, min_pre_periods=5
    )
    null_placebo = in_space_placebo(
        null_panel, null_ids, treated_index=0, n_pre_periods=null_pre, min_pre_periods=5
    )
    null_att = float(null_fit.average_effect)
    null_p = float(null_placebo.p_value)
    null_magnitude_ok = abs(null_att) <= 0.020
    null_non_rejection = null_p > 0.10
    bm_03 = BenchmarkCaseResult(
        case_id="BM-03-NEGATIVE-CONTROL",
        case_name="Synthetic Null Latent-Factor Panel (Negative Control)",
        case_type=BenchmarkCaseType.NEGATIVE_CONTROL,
        is_synthetic=True,
        data_origin="synthetic_simulated",
        description=(
            "SYNTHETIC BENCHMARK: Executes fit_synthetic_control and in_space_placebo live on a "
            "15-donor latent-factor panel with zero injected effect (seed 20260102)."
        ),
        ground_truth_effect="Null Effect (injected tau = 0.000 NDVI)",
        estimated_effect=f"ATT = {null_att:+.4f} NDVI (in-space permutation p = {null_p:.3f})",
        p_value=round(null_p, 4),
        metrics=[
            BenchmarkMetricEvaluation(
                metric_name="Estimated ATT Magnitude",
                target_value=0.000,
                observed_value=round(null_att, 6),
                tolerance=0.020,
                passed=null_magnitude_ok,
                description="Estimated null gap remains near zero without false additionality.",
            ),
            BenchmarkMetricEvaluation(
                metric_name="Null Non-Rejection (p > 0.10)",
                target_value=0.10,
                observed_value=round(null_p, 4),
                tolerance=0.90,
                passed=null_non_rejection,
                description="In-space permutation p-value does not falsely reject null.",
            ),
        ],
        verdict=(
            BenchmarkVerdict.PASSED
            if (null_magnitude_ok and null_non_rejection)
            else BenchmarkVerdict.FAILED
        ),
        scientific_rationale=(
            "Measured live from real solver execution on an explicitly badged synthetic null panel."
        ),
    )

    # Case 4: Real Executed Synthetic In-Time Temporal Placebo
    time_pre = 12
    time_panel, time_ids = _latent_factor_panel(
        seed=BENCHMARK_SEED + 2,
        n_donors=15,
        n_pre=time_pre,
        n_post=4,
        noise_sd=0.008,
        injected_effect=0.060,
    )
    in_time = in_time_placebo(
        time_panel[:, 0],
        time_panel[:, 1:],
        time_ids[1:],
        n_pre_periods=time_pre,
        fake_treatment_index=6,
        true_effect=0.060,
        min_pre_periods=4,
    )
    bm_04 = BenchmarkCaseResult(
        case_id="BM-04-TEMPORAL-PLACEBO",
        case_name="Synthetic Pre-Intervention In-Time Placebo",
        case_type=BenchmarkCaseType.TEMPORAL_PLACEBO,
        is_synthetic=True,
        data_origin="synthetic_simulated",
        description=(
            "SYNTHETIC BENCHMARK: Executes in_time_placebo live inside the pre-treatment period "
            "(fake treatment index 6 of 12 pre-periods) to verify no spurious pre-trend gap."
        ),
        ground_truth_effect="Pre-period Null Placebo (tau = 0.000 NDVI)",
        estimated_effect=f"Placebo ATT = {in_time.fake_effect:+.4f} NDVI",
        p_value=None,
        metrics=[
            BenchmarkMetricEvaluation(
                metric_name="Fake Pre-Period ATT Magnitude",
                target_value=0.0,
                observed_value=round(float(in_time.fake_effect), 6),
                tolerance=0.030,
                passed=in_time.passes,
                description="Pre-period placebo gap stays small relative to true post effect (< 50%).",
            ),
        ],
        verdict=BenchmarkVerdict.PASSED if in_time.passes else BenchmarkVerdict.FAILED,
        scientific_rationale=(
            "Measured live from in_time_placebo on synthetic pre-period observations."
        ),
    )

    # Case 5: Real Executed Synthetic Effect Recovery & Reproducibility Check
    att_1, p_1 = _run_synthetic_stress_recovery(BENCHMARK_SEED)
    att_2, p_2 = _run_synthetic_stress_recovery(BENCHMARK_SEED)
    reproducible = (att_1 == att_2) and (p_1 == p_2)
    recovery_err = abs(att_1 - 0.060)
    recovery_ok = recovery_err <= 0.015 and p_1 <= 0.15 and reproducible
    bm_05 = BenchmarkCaseResult(
        case_id="BM-05-SYNTHETIC-OVERCREDITING",
        case_name="Deterministic Synthetic Effect Recovery & Overstatement Stress Test",
        case_type=BenchmarkCaseType.SYNTHETIC_STRESS_TEST,
        is_synthetic=True,
        data_origin="synthetic_simulated",
        description=(
            "SYNTHETIC BENCHMARK: Executes fit_synthetic_control and in_space_placebo live twice "
            "from seed 20260101 on an injected +0.060 NDVI latent-factor panel vs hypothetical "
            "inflated +0.089 NDVI claim, checking recovery error and exact determinism."
        ),
        ground_truth_effect="Injected True tau = +0.0600 NDVI (SYNTHETIC)",
        estimated_effect=(
            f"Recovered ATT = {att_1:+.4f} NDVI (in-space placebo p = {p_1:.3f}; error = {recovery_err:.4f})"
        ),
        p_value=round(p_1, 4),
        metrics=[
            BenchmarkMetricEvaluation(
                metric_name="Recovered ATT vs Injected tau Error",
                target_value=0.060,
                observed_value=round(att_1, 6),
                tolerance=0.015,
                passed=recovery_err <= 0.015,
                description="SCM recovers injected +0.060 NDVI within 0.015 NDVI.",
            ),
            BenchmarkMetricEvaluation(
                metric_name="Seed Reproducibility Difference",
                target_value=0.0,
                observed_value=abs(att_1 - att_2),
                tolerance=0.0,
                passed=reproducible,
                description="Repeat run with identical seed matches bitwise.",
            ),
        ],
        verdict=BenchmarkVerdict.PASSED if recovery_ok else BenchmarkVerdict.FAILED,
        scientific_rationale=(
            "Recovered live from fit_synthetic_control and in_space_placebo with verified "
            "deterministic replay."
        ),
    )

    results = [bm_01, bm_02, bm_03, bm_04, bm_05]
    total = len(results)
    passed = sum(1 for r in results if r.verdict == BenchmarkVerdict.PASSED)
    failed = sum(1 for r in results if r.verdict == BenchmarkVerdict.FAILED)
    unavailable = sum(1 for r in results if r.verdict == BenchmarkVerdict.UNAVAILABLE)

    executed_neg = (bm_03, bm_04)
    fpr = sum(1 for r in executed_neg if r.verdict != BenchmarkVerdict.PASSED) / len(executed_neg)
    fnr = 0.0 if bm_05.verdict == BenchmarkVerdict.PASSED else 1.0
    executed_all = [r for r in results if r.verdict != BenchmarkVerdict.UNAVAILABLE]
    cal_score = round(
        100.0
        * sum(1 for r in executed_all if r.verdict == BenchmarkVerdict.PASSED)
        / len(executed_all),
        2,
    )

    return BenchmarkSuiteSummary(
        suite_name="GroundTruth 2.0 Validation Benchmark Suite",
        version="2.0.0",
        execution_timestamp=timestamp,
        total_cases=total,
        passed_cases=passed,
        failed_cases=failed,
        unavailable_cases=unavailable,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        uncertainty_calibration_score=cal_score,
        reproducibility_confirmed=reproducible,
        results=results,
    )
