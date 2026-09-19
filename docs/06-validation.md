# 6. Validation

> **No validation has been run.** This document is the plan and its
> pre-registered success criteria. It contains no results, and it will not
> contain any until the Earth Engine integration lands and a run is reviewed.

## Why pre-registering matters here

A verification method that is tuned until it reproduces a known answer has
proved nothing except that it can be tuned. The criteria below are written
before any real data has touched the pipeline, specifically so that a later
result cannot be quietly graded against a moved goalpost.

## Level 1 — Recovery on synthetic data

**Implemented and passing.** `tests/test_causal.py` generates a latent-factor
panel with a known injected effect and asserts the estimator recovers it.

| Check | Criterion | Status |
| --- | --- | --- |
| Recovers a known effect | Within 0.015 of the truth on a clean panel | Passing |
| Reports no effect when none exists | \|estimate\| < 0.02 | Passing |
| Pre-period fit is tight | RMSPE < 0.02 | Passing |
| Placebo flags a real effect | Rank 1, p below 0.10 | Passing |
| Placebo does not flag a null | Not extreme | Passing |
| Weights satisfy the simplex constraint | Sum 1, all non-negative | Passing |
| Leave-one-out sign stability on a real effect | No sign flips | Passing |

This establishes that the machinery is correct. It establishes nothing about
real forests.

## Level 2 — Kariba REDD+ benchmark

The primary external test. Kariba is the only case in scope with a published,
third-party correction to compare against.

**Reference figure (not ours).** Following a two-year investigation concluded in
2025, Verra found that a reported 57% of the approximately 27 million credits
issued by the Kariba REDD+ project (VCS 902) were in excess of the emission
reductions achieved.
*Source: Verra investigation findings, as reported by Carbon Herald and Climate
Home News, September 2025.*

### Pre-registered criteria

| Outcome | Interpretation |
| --- | --- |
| **Strong** | Independent estimate implies substantial over-issuance, placebo p < 0.10, sign stable under leave-one-out, and the implied excess share is within a factor of two of 57% |
| **Partial** | Direction agrees and robustness checks pass, but the magnitude does not land within a factor of two |
| **Weak** | Direction agrees but placebo or leave-one-out checks fail |
| **Negative** | Direction disagrees, or the pipeline returns INCONCLUSIVE |

**A negative result will be reported.** It is a finding about the limits of
satellite-based causal screening, which is worth knowing and worth publishing.
Suppressing it would make every other claim in this repository worthless.

### Known difficulty

The Verra figure is expressed in tCO2e. Our estimate is on a spectral index.
Comparing them requires the biomass conversion layer described in
[5. Causal inference](05-causal-inference.md), with its error propagated. Until
that exists, the Kariba comparison can only be made on **direction and relative
magnitude on the observed indicator**, not on a credit count. The design already
enforces this: the verdict returns INCONCLUSIVE rather than manufacturing a
comparison.

## Level 3 — Cross-ecosystem behaviour

| Case | Tests | Expected behaviour |
| --- | --- | --- |
| Southern Cardamom REDD+ | Canopy saturation, persistent cloud | EVI must be used; sparse years must be surfaced by the masking audit, not interpolated |
| Mikoko Pamoja | Scale and tidal confounding | **INCONCLUSIVE is the correct answer.** At ~117 ha the project is far below what a 30 m annual composite can resolve |

Mikoko Pamoja is a deliberate negative control **on the method**. A pipeline
that returns a confident number for a 117 ha mangrove project is broken, and
this case is how we find out. It is not a project under suspicion.

## Level 4 — Method robustness

| Check | Question |
| --- | --- |
| Donor-pool sensitivity | Does the estimate survive re-drawing the candidate region? |
| Specification curve | Do NDVI, EVI and forest-area specifications agree in sign? |
| Pre-period length | Is the estimate stable across 8, 10 and 12 pre-period years? |
| Treatment date | Does moving the date to project validation rather than crediting start change the conclusion? |
| Sensor transition | Does placing the Landsat/Sentinel boundary in the pre-period versus the post-period change the sign? |

Any check that flips a sign is reported as a limitation of that case, not
dropped from the specification set.

## Level 5 — GenAI grounding evaluation

**Implemented for the grounding verifier; the model comparison has not been
run.**

The verifier is tested against adversarial narration in
`tests/test_grounding.py`: invented figures, plausible-but-wrong figures, fraud
allegations, legal conclusions, overclaiming, and index-to-carbon phrasing. All
are rejected, and the system falls back to the deterministic renderer.

The planned comparison — Nugen's alignment stack against an unaligned baseline,
measuring ungrounded-figure rate and prohibited-assertion rate on the same
bundles — is specified in `experiments/genai_grounding_eval/` and **has not been
executed**. No comparative claim about any provider is made anywhere in this
repository.

## Reporting standard

Every published result must carry:

1. Point estimate with an interval, labelled by `kind`
2. Placebo p-value with its add-one caveat
3. Donor pool size and worst covariate SMD
4. Pre-treatment fit quality
5. Leave-one-out sensitivity range
6. The specification curve, not just the headline specification
7. Full provenance for every number
8. The standard caveats

Anything missing an item on that list is not a result. It is a work in progress.

---

Previous: [5. Causal inference](05-causal-inference.md) · Next: [7. GenAI grounding](07-genai-grounding.md)
