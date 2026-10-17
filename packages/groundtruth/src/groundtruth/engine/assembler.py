"""Assembles pipeline outputs into a verified evidence bundle.

This is the last deterministic stage. After it runs, no further computation is
permitted: the reporting layer may only read what the assembler produced.

The assembler is also where the verdict is decided, by explicit rules rather
than by a model. The rules are conservative by construction: anything that fails
a robustness gate becomes ``INCONCLUSIVE`` rather than a weak positive finding.
"""

from __future__ import annotations

from dataclasses import dataclass

from groundtruth.contracts.evidence import EvidenceBuilder, EvidenceBundle
from groundtruth.contracts.provenance import Provenance
from groundtruth.contracts.request import AnalysisRequest
from groundtruth.contracts.types import (
    STANDARD_CAVEATS,
    Indicator,
    VerdictLabel,
    VerificationVerdict,
)
from groundtruth.engine.causal.did import DiDResult
from groundtruth.engine.causal.synthetic_control import (
    HULL_ENVELOPE_SHARE,
    HULL_LEVEL_EXCESS_SD,
    SyntheticControlFit,
)
from groundtruth.engine.matching.donors import DonorPool
from groundtruth.engine.observation.alignment import AlignedPanel
from groundtruth.engine.uncertainty.placebo import InTimePlaceboResult, PlaceboResult
from groundtruth.engine.uncertainty.robustness import LeaveOneOutResult, SpecificationCurve
from groundtruth.engine.uncertainty.specification import NOT_VARIED_IN_RUN

DIVERGENCE_THRESHOLD = 0.30
"""Relative divergence beyond which a claim is flagged for accredited review."""

MAX_RELATIVE_PRE_FIT = 0.30
"""Largest pre-period RMSPE, as a share of the pre-period outcome SD, that still
licenses reading the post-period gap as an effect. 0.30 means the synthetic path
explains roughly 90% of the pre-period variance. It matches the default of
``EstimationSpec.max_pre_rmse_ratio`` and the platform's documented intent for it."""


@dataclass(frozen=True)
class AssemblyInputs:
    """Everything the assembler needs from the upstream pipeline."""

    request: AnalysisRequest
    indicator_unit: str
    donor_pool: DonorPool
    fit: SyntheticControlFit
    panel: AlignedPanel | None = None
    placebo: PlaceboResult | None = None
    in_time_placebo: InTimePlaceboResult | None = None
    leave_one_out: LeaveOneOutResult | None = None
    specification_curve: SpecificationCurve | None = None
    did: DiDResult | None = None
    data_provenance: Provenance | None = None
    notices: tuple[str, ...] = ()
    """Requested options the run could not honour, surfaced as bundle warnings."""

    @property
    def claim(self) -> object:
        """The developer claim under test. Never an input to the counterfactual."""
        return self.request.claim

    @property
    def indicator(self) -> Indicator:
        """The observed indicator this analysis estimates an effect on."""
        return self.request.indicator


def _is_synthetic_run(inputs: AssemblyInputs) -> bool:
    """True if this run used simulated data.

    Read from the request rather than sniffed from provenance strings. The
    platform declares data_mode; the engine does not guess at it.
    """
    return inputs.request.is_simulated


def _fit_limit(inputs: AssemblyInputs, override: float | None) -> float:
    return override if override is not None else inputs.request.estimation.max_pre_rmse_ratio


def decide_verdict(
    inputs: AssemblyInputs,
    *,
    divergence_ratio: float | None = None,
    min_donors: int = 10,
    max_relative_pre_fit: float | None = None,
) -> VerificationVerdict:
    """Apply the screening rules and return a verdict.

    The rules run as a gate chain. Any failed gate short-circuits to
    ``INCONCLUSIVE``; only a fully passing run can produce a substantive label.

    Gates, in order:

    1. Enough admitted donors to support a counterfactual.
    2. Pre-treatment fit good enough that the post-period gap means something,
       measured against the pre-period outcome SD, not its level.
    3. The treated unit inside the donors' convex hull, so the fit is not
       structurally offset.
    4. Placebo inference available and the divergence distinguishable from the
       placebo distribution.
    5. An in-time placebo, when one was run, finding no spurious effect at a
       fake treatment date.
    6. Leave-one-out sign stability, so the result is not one donor's artefact.
    7. A specification curve, when one was run, agreeing on the sign, so the
       result is not one analytic choice's artefact.
    8. Covariate balance within the conventional guideline.

    ``max_relative_pre_fit`` defaults to the request's
    ``estimation.max_pre_rmse_ratio``, read as a share of the pre-period SD.
    """
    failures: list[str] = []
    fit_limit = _fit_limit(inputs, max_relative_pre_fit)

    n_donors = len(inputs.donor_pool.admitted)
    if n_donors < min_donors:
        failures.append(f"donor pool has {n_donors} units, below the minimum of {min_donors}")

    relative_fit = inputs.fit.relative_pre_fit
    if relative_fit > fit_limit:
        failures.append(
            f"pre-treatment fit is poor (RMSPE {relative_fit:.2f} of the pre-period outcome SD, "
            f"limit {fit_limit:.2f})"
        )

    hull = inputs.fit.hull
    if hull is not None and hull.materially_outside:
        failures.append(
            "the project lies outside the convex hull of its donors (pre-period level "
            f"{hull.level_excess_sd:.2f} SD outside the donor range; outside the donor envelope "
            f"in {hull.share_periods_outside_envelope:.0%} of pre-periods), so no donor "
            "weighting can fit it without a structural offset"
        )

    if inputs.placebo is None:
        failures.append("no placebo distribution was constructed, so significance is unassessed")
    elif not inputs.placebo.can_reject:
        failures.append(
            f"with {inputs.placebo.n_placebos} placebo units the smallest attainable p-value is "
            f"{inputs.placebo.p_value_floor:.3f}, above the significance level of "
            f"{inputs.placebo.significance_level:.3f}, so the placebo test cannot distinguish "
            "the observed gap from what untreated regions produce"
        )
    elif not inputs.placebo.is_extreme:
        failures.append(
            f"divergence is within the placebo range (p = {inputs.placebo.p_value:.3f}, "
            f"significance level {inputs.placebo.significance_level:.3f}); the observed gap is "
            "not distinguishable from what untreated regions produce"
        )

    if inputs.in_time_placebo is not None and not inputs.in_time_placebo.passes:
        failures.append(
            "the in-time placebo finds a spurious effect of "
            f"{inputs.in_time_placebo.fake_effect:.4f} at a fake treatment date inside the "
            "pre-period, at least half the size of the estimated effect, which points to "
            "misspecification rather than an intervention"
        )

    if inputs.leave_one_out is not None and not inputs.leave_one_out.sign_is_stable:
        failures.append("the estimate changes sign when a single contributing donor is removed")

    curve = inputs.specification_curve
    if curve is not None and curve.estimates and curve.sign_flips:
        failures.append(
            f"{len(curve.sign_flips)} of {len(curve.estimates)} alternative specifications give "
            f"the opposite sign ({', '.join(curve.sign_flips)})"
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
    builder = EvidenceBuilder(inputs.request.case_id)
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
        "claim.case_id",
        "Case identifier",
        inputs.request.case_id,
        provenance=Provenance.external(
            source=inputs.request.claim.source_uri or "case definition",
            source_uri=inputs.request.claim.source_uri,
        ),
    )
    if inputs.request.claim.claimed_credits_tco2e is not None:
        builder.add(
            "claim.credits_tco2e",
            "Credits claimed or issued, as reported by the registry",
            float(inputs.request.claim.claimed_credits_tco2e),
            unit="tCO2e",
            provenance=Provenance.external(
                source=f"{inputs.request.claim.standard} registry",
                source_uri=inputs.request.claim.source_uri,
                notes="Developer-reported figure under test. Not computed by GroundTruth.",
            ),
            qualifiers={"developer_reported": True, "under_test": True},
        )

    if inputs.panel is not None:
        panel = inputs.panel
        alignment_prov = Provenance.computed(
            source=data_source,
            method="window-alignment/period-labels",
            stage="alignment",
            parameters={
                "pre_periods": [panel.pre_periods[0], panel.pre_periods[-1]],
                "post_periods": [panel.post_periods[0], panel.post_periods[-1]],
                "n_units": len(panel.donor_ids) + 1,
            },
            notes=(
                "Every included series was checked to carry a finite value for every window "
                "period. The pre/post split is taken from period labels, not array positions."
            ),
        )
        builder.add(
            "fit.n_pre_periods",
            "Pre-treatment periods observed for the project and every donor",
            len(panel.pre_periods),
            provenance=alignment_prov,
            qualifiers={"first_period": panel.pre_periods[0], "last_period": panel.pre_periods[-1]},
        )
        builder.add(
            "fit.n_post_periods",
            "Post-treatment periods observed for the project and every donor",
            len(panel.post_periods),
            provenance=alignment_prov,
            qualifiers={
                "first_period": panel.post_periods[0],
                "last_period": panel.post_periods[-1],
            },
        )
        builder.add(
            "fit.treatment_boundary_period",
            "First period treated as post-treatment by the estimators",
            panel.post_periods[0],
            provenance=alignment_prov,
            qualifiers={"dropped_periods": list(panel.dropped_periods)},
        )
        if panel.dropped_periods:
            builder.warn(
                f"Periods {list(panel.dropped_periods)} were returned by the data provider but "
                "fall outside the analysis window's pre- and post-treatment ranges, so no "
                "estimator used them."
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
        "matching.n_candidates_excluded",
        "Candidate regions excluded by an eligibility rule",
        len(inputs.donor_pool.excluded),
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
        f"Estimated incremental effect on {inputs.request.indicator.value} "
        "(mean post-treatment gap)",
        float(inputs.fit.average_effect),
        unit=inputs.indicator_unit,
        confidence=(inputs.leave_one_out.envelope() if inputs.leave_one_out is not None else None),
        provenance=scm_prov,
        qualifiers={
            "observed_not_causal_without_assumptions": True,
            "is_carbon_quantity": False,
            "indicator": inputs.request.indicator.value,
        },
    )
    builder.add(
        "effect.cumulative",
        f"Cumulative post-treatment gap in {inputs.request.indicator.value}",
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
        "fit.relative_pre_rmspe",
        "Pre-treatment RMSPE as a share of the pre-period outcome SD",
        float(inputs.fit.relative_pre_fit),
        provenance=scm_prov,
        qualifiers={"gate_threshold": _fit_limit(inputs, None)},
    )
    hull = inputs.fit.hull
    if hull is not None:
        hull_prov = Provenance.computed(
            source=data_source,
            method="convex-hull-necessary-conditions/level-and-envelope",
            stage="causal",
            parameters={
                "level_excess_sd_threshold": HULL_LEVEL_EXCESS_SD,
                "envelope_share_threshold": HULL_ENVELOPE_SHARE,
            },
            notes=(
                "Necessary conditions for the project to be spanned by its donors. A failure "
                "means every simplex weighting carries a structural offset into the "
                "post-treatment gap."
            ),
        )
        builder.add(
            "fit.inside_donor_hull",
            "Project's pre-treatment path is within the donors' convex hull",
            not hull.materially_outside,
            provenance=hull_prov,
        )
        builder.add(
            "fit.hull_level_excess",
            "Distance of the project's pre-period mean outside the range of donor means",
            float(hull.level_excess),
            unit=inputs.indicator_unit,
            provenance=hull_prov,
            qualifiers={"in_pre_period_sd": float(hull.level_excess_sd)},
        )
        builder.add(
            "fit.hull_periods_outside_envelope",
            "Share of pre-periods where the project is outside every donor's range",
            float(hull.share_periods_outside_envelope),
            provenance=hull_prov,
            qualifiers={"max_excess": float(hull.max_envelope_excess)},
        )
        if hull.materially_outside:
            builder.warn(
                "The project's pre-treatment path lies outside the convex hull of its donor "
                "pool, so the synthetic control cannot match its level and any post-treatment "
                "gap includes a structural offset. The donor pool is inadequate for this "
                "project as specified."
            )

    builder.add(
        "fit.converged",
        "Weight optimiser reached its convergence tolerance",
        bool(inputs.fit.converged),
        provenance=scm_prov,
    )

    builder.add(
        "fit.weights_identified",
        "Donor weights are uniquely determined by the pre-treatment fit",
        bool(inputs.fit.weights_are_identified),
        provenance=scm_prov,
    )
    if not inputs.fit.weights_are_identified:
        builder.warn(
            "There are more donors than pre-treatment periods, so the individual donor weights "
            "are not uniquely identified. The counterfactual path and the effect estimate are "
            "still well determined, but the listed contributing regions are one of several "
            "equally good weightings, and should be read as an illustration of the comparison "
            "set rather than as the only one consistent with the data."
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
                "excluded_from_placebo_pools": list(inputs.placebo.excluded_from_placebo_pools),
                "excluded_poor_fit": inputs.placebo.excluded_poor_fit,
            },
            inputs=("fit.rmspe_ratio",),
            notes=(
                "The project is never a donor in a placebo fit, so no placebo counterfactual "
                "inherits the project's post-treatment path."
            ),
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
                "significance_level": inputs.placebo.significance_level,
                "p_value_floor": inputs.placebo.p_value_floor,
            },
        )
        builder.add(
            "placebo.n_units",
            "Placebo units in the permutation distribution",
            inputs.placebo.n_placebos,
            provenance=placebo_prov,
        )

    if inputs.in_time_placebo is not None:
        in_time = inputs.in_time_placebo
        fake_period = (
            inputs.panel.pre_periods[in_time.fake_treatment_index]
            if inputs.panel is not None
            else None
        )
        in_time_prov = Provenance.computed(
            source=data_source,
            method="in-time-placebo/pre-period-refit",
            stage="uncertainty",
            parameters={
                "fake_treatment_index": in_time.fake_treatment_index,
                "fake_treatment_period": fake_period,
                "pass_rule": "absolute fake effect below half the absolute estimated effect",
            },
            inputs=("effect.point_estimate",),
            notes="Fitted on pre-treatment periods only, so any effect it finds is spurious.",
        )
        builder.add(
            "placebo.in_time_fake_effect",
            "Effect the model finds at a fake treatment date inside the pre-period",
            float(in_time.fake_effect),
            unit=inputs.indicator_unit,
            provenance=in_time_prov,
            qualifiers={"fake_treatment_period": fake_period},
        )
        builder.add(
            "placebo.in_time_passes",
            "In-time placebo finds no material spurious effect",
            bool(in_time.passes),
            provenance=in_time_prov,
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

    curve = inputs.specification_curve
    if curve is not None and curve.estimates:
        curve_prov = Provenance.computed(
            source=data_source,
            method="specification-curve/one-at-a-time",
            stage="uncertainty",
            parameters={
                "centre": curve.centre_id,
                "n_specifications": len(curve.estimates),
                "n_failed": len(curve.failed),
                "dimensions_varied": sorted(set(curve.dimensions.values()) - {"centre"}),
                "dimensions_not_varied_in_run": list(NOT_VARIED_IN_RUN),
            },
            inputs=("effect.point_estimate",),
            notes=(
                "Each specification changes one analytic choice from the centre. The centre is "
                "marked but not privileged: the median, sign agreement and range are computed "
                "over every specification."
            ),
        )
        builder.add(
            "robustness.spec_curve.median",
            f"Median effect on {inputs.request.indicator.value} across specifications",
            float(curve.median),
            unit=inputs.indicator_unit,
            confidence=curve.envelope(),
            provenance=curve_prov,
            qualifiers={
                "range_is": "sensitivity-envelope, not a confidence interval",
                "n_specifications": len(curve.estimates),
            },
        )
        builder.add(
            "robustness.spec_curve.sign_agreement",
            "Share of specifications agreeing with the median's sign",
            float(curve.sign_agreement),
            provenance=curve_prov,
            qualifiers={"sign_flips": list(curve.sign_flips)},
        )
        ordered = sorted(curve.estimates.items(), key=lambda kv: kv[1])
        for spec_id, estimate in ordered:
            builder.add(
                f"robustness.spec_curve.estimate.{spec_id}",
                f"Effect under specification {spec_id}",
                float(estimate),
                unit=inputs.indicator_unit,
                provenance=curve_prov,
                qualifiers={
                    "dimension": curve.dimensions.get(spec_id, "unknown"),
                    "is_centre": spec_id == curve.centre_id,
                    "flips_sign": spec_id in curve.sign_flips,
                },
            )
        if curve.sign_flips:
            builder.warn(
                "The sign of the estimate is not stable across specifications: "
                f"{', '.join(curve.sign_flips)} give the opposite sign to the median. This is a "
                "limitation of the result for this case."
            )
        if curve.failed:
            builder.warn(
                "Some specifications could not be estimated and are absent from the curve: "
                + "; ".join(f"{sid} ({reason})" for sid, reason in sorted(curve.failed.items()))
                + "."
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

    for notice in inputs.notices:
        builder.warn(notice)

    verdict = decide_verdict(inputs, divergence_ratio=divergence_ratio, min_donors=min_donors)
    return builder.build(verdict)
