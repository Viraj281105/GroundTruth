# 2. Methodology

## The question being answered

For a project claiming a climate benefit, GroundTruth estimates:

> How much did the observed ecological indicator inside the project boundary
> change **relative to what comparable regions did over the same period**?

That relative quantity — the gap between the project and its counterfactual —
is what the method estimates. It is not the same as a carbon quantity, and the
system never presents it as one.

## Why before-and-after comparison fails

The naive approach compares the project area before and after the intervention:

```
effect_naive = indicator_after - indicator_before
```

This absorbs every regional trend into the estimate. Rainfall cycles, commodity
prices, road construction, conflict and macroeconomic shocks move forest cover
across whole regions. A project in a region where deforestation slowed for
unrelated reasons looks successful; a project in a region hit by drought looks
like a failure. Neither reading is about the project.

## The counterfactual approach

```
effect = indicator_project_after - indicator_synthetic_counterfactual_after
```

The counterfactual is built from regions that are similar to the project on
observable characteristics and were **not** subject to the intervention. If a
weighted combination of those regions tracks the project closely for a decade
before the intervention, their subsequent path is a defensible estimate of what
the project area would have done.

## Pipeline stages

```
 1. INGEST     project claim, boundary, crediting period
 2. OBSERVE    multi-temporal indicator series for project + candidate regions
 3. MATCH      donor pool built on rainfall, elevation, slope, access, pressure
 4. ESTIMATE   synthetic control (primary) + difference-in-differences (check)
 5. TEST       in-space and in-time placebos, leave-one-out, spec curve
 6. ASSEMBLE   verified evidence bundle with full provenance
 7. REPORT     deterministic renderer, optional grounded narration
```

Stages 1–6 are deterministic and contain no language model. Stage 7 is the only
place a model may run, and it may only narrate what stage 6 produced.

## Stage 1 — Ingest

The developer's claim is loaded as an **assertion under test**. Nothing in it
feeds the counterfactual. Boundaries come from the registry record; a
hand-redrawn boundary changes the estimate and cannot be audited.

Boundaries are buffered inward to avoid mixed edge pixels, and that buffer is
recorded as a caveat because it changes what the estimate is *of*.

## Stage 2 — Observe

Annual median composites from Sentinel-2 and Landsat, cloud- and shadow-masked
via the SCL band. Median rather than mean, because residual undetected cloud is
a heavy positive-reflectance outlier that a mean would absorb.

Clear-observation counts are carried per period. A year with two usable scenes
is not the same measurement as a year with twenty, and the pipeline surfaces
that rather than interpolating over it.

## Stage 3 — Match

Before anything can be matched, *what counts as one region* has to be defined.
A candidate is one administrative district intersected with a pre-treatment
eligibility mask — baseline forest, target ecoregion, no permanent water, no
protected area gazetted before the window, inward-buffered. The project is
built by the same rule from its registry boundary, because a treated unit
masked differently from its donors is not comparable to them. The full rule,
the exclusions and the inputs it needs are in
[ADR-011](../decisions/ADR-011-unit-of-analysis.md).

The mask is deliberately built from information dated before the pre-period.
Masking with a present-day land-cover product would condition on a
post-treatment outcome — it would remove exactly the pixels that were cleared
during the study window, in the direction of manufacturing a project effect.

Candidate regions are then admitted or excluded by explicit rules, each recorded
with a reason:

| Rule | Why |
| --- | --- |
| Leakage-belt exclusion | If the project displaced deforestation into a region, that region is a treated unit in disguise and would bias the effect upward |
| Common-support caliper | Extrapolating beyond the observed covariate range is not matching, it is guessing |
| Pre-treatment coverage | Weights are fitted on the pre-period; a donor with no pre-period contributes nothing but noise |

Post-match balance is reported as standardised mean differences. A worst-case
SMD above 0.25 is treated as poor balance and blocks a substantive verdict.

If fewer than the configured minimum survive, the pipeline raises
`DonorPoolError` rather than estimating. See
[5. Causal inference](causal-inference.md).

## Stage 4 — Estimate

**Synthetic control** is the primary estimator. Donor weights are constrained to
the unit simplex — non-negative and summing to one — which forbids extrapolation
outside the convex hull of observed donors. The counterfactual is always an
attainable combination of places that actually exist.

**Difference-in-differences** runs as a transparent cross-check and always
reports its own pre-trend divergence diagnostic, so a reader can see how much
faith the parallel-trends assumption deserves in that particular case.

## Stage 5 — Test

With one treated unit there is no sampling distribution, so significance is
assessed by permutation:

- **In-space placebos** refit the model pretending each donor was treated. The
  project's post/pre RMSPE ratio is ranked within that distribution.
- **In-time placebos** move the treatment date earlier inside the pre-period. A
  model that "detects" an effect before anything happened is detecting its own
  misspecification.
- **Leave-one-out** removes each contributing donor in turn. If the sign flips,
  the finding belongs to one comparison region and is not reported as a
  project-level conclusion.
- **Specification curve** reports the spread across equally defensible
  specifications rather than the single best-looking one.

## Stage 6 — Assemble

Outputs become an immutable `EvidenceBundle`. The verdict is decided by an
explicit gate chain, not by a model:

1. Enough admitted donors
2. Pre-treatment fit good enough that the post-period gap means something
3. Placebo inference available and the divergence distinguishable from it
4. Leave-one-out sign stability
5. Covariate balance within the conventional guideline

**Any failed gate short-circuits to `INCONCLUSIVE`.** There is no weak-positive
path.

## Stage 7 — Report

See [7. GenAI grounding](../architecture/genai.md).

## What the method does not do

- It does not estimate carbon. See [5. Causal inference](causal-inference.md),
  "NDVI is not carbon".
- It does not detect fraud. It detects divergence between an independent
  estimate and a claim, which is a reason to look, not a conclusion.
- It does not replace field measurement. Allometric ground plots measure things
  no satellite can see.

---

Previous: [1. Problem](../product/problem.md) · Next: [3. Architecture](../architecture/system.md)
