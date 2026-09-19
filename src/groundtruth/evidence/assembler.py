"""Assembles pipeline outputs into a verified evidence bundle.

This is the last deterministic stage. After it runs, no further computation is
permitted: the reporting layer may only read what the assembler produced.

The assembler is also where the verdict is decided, by explicit rules rather
than by a model. The rules are conservative by construction: anything that fails
a robustness gate becomes ``INCONCLUSIVE`` rather than a weak positive finding.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundtruth.causal.did import DiDResult
from groundtruth.causal.synthetic_control import SyntheticControlFit
from groundtruth.core.evidence import EvidenceBuilder, EvidenceBundle
from groundtruth.core.provenance import Provenance
from groundtruth.core.types import (
    STANDARD_CAVEATS,
    Indicator,
    ProjectClaim,
    VerdictLabel,
    VerificationVerdict,
)
from groundtruth.ingestion.synthetic import SYNTHETIC_MARKER
from groundtruth.matching.donors import DonorPool
from groundtruth.uncertainty.placebo import PlaceboResult
from groundtruth.uncertainty.robustness import LeaveOneOutResult

DIVERGENCE_THRESHOLD = 0.30
"""Relative divergence beyond which a claim is flagged for accredited review."""


@dataclass(frozen=True)
class AssemblyInputs:
    """Everything the assembler needs from the upstream pipeline."""

    claim: ProjectClaim
    indicator: Indicator
    indicator_unit: str
    donor_pool: DonorPool
    fit: SyntheticControlFit
    placebo: PlaceboResult | None = None
    leave_one_out: LeaveOneOutResult | None = None
    did: DiDResult | None = None
    data_provenance: Provenance | None = None
    treatment_period: int | None = None


def _is_synthetic_run(inputs: AssemblyInputs) -> bool:
    prov = inputs.data_provenance
    return prov is not None and (
        prov.method == SYNTHETIC_MARKER or SYNTHETIC_MARKER in (prov.notes or "")
    )


def decide_verdict(
    inputs: AssemblyInputs,
    *,
    divergence_ratio: float | None = None,
    min_donors: int = 10,
    max_pre_rmspe_ratio: float = 0.30,
) -> VerificationVerdict:
    """Apply the screening rules and return a verdict.

    The rules run as a gate chain. Any failed gate short-circuits to
    ``INCONCLUSIVE``; only a fully passing run can produce a substantive label.

    Gates, in order:

    1. Enough admitted donors to support a counterfactual.
    2. Pre-treatment fit good enough that the post-period gap means something.
    3. Placebo inference available and the divergence distinguishable from the
       placebo distribution.
    4. Leave-one-out sign stability, so the result is not one donor's artefact.
    """
    failures: list[str] = []

    n_donors = len(inputs.donor_pool.admitted)
    if n_donors < min_donors:
        failures.append(f"donor pool has {n_donors} units, below the minimum of {min_donors}")

    outcome_scale = float(abs(inputs.fit.treated_pre.mean())) or 1.0
    relative_fit = inputs.fit.pre_rmspe / outcome_scale
    if relative_fit > max_pre_rmspe_ratio:
        failures.append(
            f"pre-treatment fit is poor (RMSPE {relative_fit:.1%} of the outcome level, "
            f"limit {max_pre_rmspe_ratio:.0%})"
        )

    if inputs.placebo is None:
        failures.append("no placebo distribution was constructed, so significance is unassessed")
    elif not inputs.placebo.is_extreme:
        failures.append(
            f"divergence is within the placebo range (p = {inputs.placebo.p_value:.3f}); the "
            "observed gap is not distinguishable from what untreated regions produce"
        )

    if inputs.leave_one_out is not None and not inputs.leave_one_out.sign_is_stable:
        failures.append(
            "the estimate changes sign when a single contributing donor is removed"
        )

    if not inputs.donor_pool.is_balanced:
        failures.append(
            f"covariate balance is poor (worst SMD {inputs.donor_pool.worst_balance:.2f} "
            "against a 0.25 guideline)"
        )

    caveats = list(STANDARD_CAVEATS)
    if _is_synthetic_run(inputs):
        caveats.insert(
            0,
            "THIS RUN USED SIMULATED DATA. The figures below describe a synthetic test "
            "fixture and say nothing about any real project.",
        )

    if failures:
        return VerificationVerdict(
            label=VerdictLabel.INCONCLUSIVE,
            rationale=(
                "The pipeline ran but the result does not meet the robustness bar required to "
                "report a screening outcome: " + "; ".join(failures) + "."
            ),
            divergence_ratio=divergence_ratio,
            caveats=tuple(caveats),
        )

    if divergence_ratio is None:
        return VerificationVerdict(
            label=VerdictLabel.INCONCLUSIVE,
            rationale=(
                "A robust incremental effect on the observed indicator was estimated, but the "
                "developer's claim is not expressed in commensurable units, so no comparison "
                "against the claim can be made without a biomass conversion step."
            ),
            caveats=tuple(caveats),
        )

    if abs(divergence_ratio - 1.0) <= DIVERGENCE_THRESHOLD:
        return VerificationVerdict(
            label=VerdictLabel.CONSISTENT_WITH_CLAIM,
            rationale=(
                f"The independent estimate is within {DIVERGENCE_THRESHOLD:.0%} of the "
                "developer's claim, and survives placebo and leave-one-out checks."
            ),
            divergence_ratio=divergence_ratio,
            caveats=tuple(caveats),
        )

    return VerificationVerdict(
        label=VerdictLabel.DIVERGENT_FROM_CLAIM,
        rationale=(
            f"The independent estimate is {divergence_ratio:.2f}x the developer's claim, a "
            f"divergence beyond the {DIVERGENCE_THRESHOLD:.0%} screening threshold. The "
            "divergence survives placebo and leave-one-out robustness checks and warrants "
            "accredited review of the project's baseline."
        ),
        divergence_ratio=divergence_ratio,
        caveats=tuple(caveats),
    )


def assemble_evidence(
    inputs: AssemblyInputs,
    *,
    divergence_ratio: float | None = None,
    min_donors: int = 10,
) -> EvidenceBundle:
    """Turn pipeline outputs into an immutable, fully provenanced bundle."""
    builder = EvidenceBuilder(inputs.claim.case_id)
    synthetic = _is_synthetic_run(inputs)
    if synthetic:
        builder.warn(
            "SIMULATED DATA: this bundle was produced from the synthetic fixture provider and "
            "must not be published as a finding about a real project."
        )

    data_source = inputs.data_provenance.source if inputs.data_provenance else "unspecified"
    matching_prov = Provenance.computed(
        source=data_source,
        method="standardised-covariate-distance",
        stage="matching",
        parameters={"covariates": list(inputs.donor_pool.covariates)},
    )
    scm_prov = Provenance.computed(
        source=data_source,
        method="synthetic-control/simplex-constrained-least-squares",
        stage="causal",
        parameters={
            "n_pre_periods": int(inputs.fit.treated_pre.size),
            "n_post_periods": int(inputs.fit.treated_post.size),
            "n_donors": len(inputs.fit.donor_ids),
            "converged": inputs.fit.converged,
            "iterations": inputs.fit.n_iterations,
        },
        inputs=("matching.n_donors_admitted",),
        notes=(
            "Effect is on the observed indicator only. It is not a carbon quantity and has "
            "not been converted to one."
        ),
    )

    builder.add(
        "claim.case_id", "Case identifier", inputs.claim.case_id, provenance=Provenance.external(
            source=inputs.claim.claim_source_uri or "case definition",
            source_uri=inputs.claim.claim_source_uri,
        )
    )
    if inputs.claim.claimed_credits_tco2e is not None:
        builder.add(
            "claim.credits_tco2e",
            "Credits claimed or issued, as reported by the registry",
            float(inputs.claim.claimed_credits_tco2e),
            unit="tCO2e",
            provenance=Provenance.external(
                source=f"{inputs.claim.standard.value} registry",
                source_uri=inputs.claim.claim_source_uri,
                notes="Developer-reported figure under test. Not computed by GroundTruth.",
            ),
            qualifiers={"developer_reported": True, "under_test": True},
        )

    builder.add(
        "matching.n_candidates",
        "Candidate control regions considered",
        len(inputs.donor_pool.matches),
        provenance=matching_prov,
    )
    builder.add(
        "matching.n_donors_admitted",
        "Control regions admitted to the donor pool",
        len(inputs.donor_pool.admitted),
        provenance=matching_prov,
    )
    builder.add(
        "matching.worst_covariate_smd",
        "Worst post-match standardised mean difference across covariates",
        float(inputs.donor_pool.worst_balance),
        provenance=matching_prov,
        qualifiers={"guideline_threshold": 0.25, "balanced": inputs.donor_pool.is_balanced},
    )

    builder.add(
        "effect.point_estimate",
        f"Estimated incremental effect on {inputs.indicator.value} (mean post-treatment gap)",
        float(inputs.fit.average_effect),
        unit=inputs.indicator_unit,
        confidence=(
            inputs.leave_one_out.envelope() if inputs.leave_one_out is not None else None
        ),
        provenance=scm_prov,
        qualifiers={
            "observed_not_causal_without_assumptions": True,
            "is_carbon_quantity": False,
            "indicator": inputs.indicator.value,
        },
    )
    builder.add(
        "effect.cumulative",
        f"Cumulative post-treatment gap in {inputs.indicator.value}",
        float(inputs.fit.cumulative_effect),
        unit=inputs.indicator_unit,
        provenance=scm_prov,
    )
    builder.add(
        "fit.pre_rmspe",
        "Pre-treatment root mean squared prediction error",
        float(inputs.fit.pre_rmspe),
        unit=inputs.indicator_unit,
        provenance=scm_prov,
    )
    builder.add(
        "fit.rmspe_ratio",
        "Post/pre RMSPE ratio",
        float(inputs.fit.rmspe_ratio),
        provenance=scm_prov,
    )
    builder.add(
        "fit.converged",
        "Weight optimiser reached its convergence tolerance",
        bool(inputs.fit.converged),
        provenance=scm_prov,
    )

    for rank, (donor_id, weight) in enumerate(inputs.fit.contributing_donors().items(), start=1):
        if rank > 5:
            break
        builder.add(
            f"fit.donor_weight.{rank}",
            f"Weight on contributing control region {donor_id}",
            float(weight),
            provenance=scm_prov,
            qualifiers={"donor_unit_id": donor_id},
        )

    if inputs.placebo is not None:
        placebo_prov = Provenance.computed(
            source=data_source,
            method="in-space-placebo-permutation",
            stage="uncertainty",
            parameters={
                "n_placebos": inputs.placebo.n_placebos,
                "statistic": inputs.placebo.statistic_name,
            },
            inputs=("fit.rmspe_ratio",),
        )
        builder.add(
            "placebo.p_value",
            "Permutation p-value from in-space placebo tests",
            float(inputs.placebo.p_value),
            provenance=placebo_prov,
            qualifiers={
                "interpretation": (
                    "Share of untreated comparison regions producing a divergence at least as "
                    "large. Not a probability of misreporting."
                ),
                "rank": inputs.placebo.rank,
            },
        )
        builder.add(
            "placebo.n_units",
            "Placebo units in the permutation distribution",
            inputs.placebo.n_placebos,
            provenance=placebo_prov,
        )

    if inputs.leave_one_out is not None:
        loo_prov = Provenance.computed(
            source=data_source,
            method="leave-one-donor-out-refit",
            stage="uncertainty",
            parameters={"n_refits": len(inputs.leave_one_out.effects)},
            inputs=("effect.point_estimate",),
        )
        builder.add(
            "robustness.max_absolute_shift",
            "Largest change in the estimate from removing one contributing donor",
            float(inputs.leave_one_out.max_absolute_shift),
            unit=inputs.indicator_unit,
            provenance=loo_prov,
        )
        builder.add(
            "robustness.sign_stable",
            "Estimate keeps its sign across all leave-one-out refits",
            bool(inputs.leave_one_out.sign_is_stable),
            provenance=loo_prov,
        )

    if inputs.did is not None:
        did_prov = Provenance.computed(
            source=data_source,
            method="difference-in-differences",
            stage="causal",
            parameters={"n_control_units": inputs.did.n_control_units},
            notes="Cross-check estimator; valid only under parallel trends.",
        )
        builder.add(
            "crosscheck.did_estimate",
            "Difference-in-differences cross-check estimate",
            float(inputs.did.estimate),
            unit=inputs.indicator_unit,
            provenance=did_prov,
            qualifiers={"parallel_trends_plausible": inputs.did.parallel_trends_plausible},
        )
        builder.add(
            "crosscheck.did_pre_trend_divergence",
            "Pre-treatment slope divergence between project and controls",
            float(inputs.did.pre_trend_divergence),
            unit=inputs.indicator_unit,
            provenance=did_prov,
        )
        if not inputs.did.parallel_trends_plausible:
            builder.warn(
                "The difference-in-differences cross-check fails its parallel-trends screen; "
                "treat it as uninformative here and rely on the synthetic control."
            )

    if inputs.donor_pool.excluded:
        builder.warn(
            f"{len(inputs.donor_pool.excluded)} candidate regions were excluded from the donor "
            "pool; see the donor-pool table for per-unit reasons."
        )

    verdict = decide_verdict(
        inputs, divergence_ratio=divergence_ratio, min_donors=min_donors
    )
    return builder.build(verdict)
