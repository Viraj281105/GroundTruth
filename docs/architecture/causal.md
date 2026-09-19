# Causal intelligence architecture

How estimators are structured, and how additional causal methods plug in without
rewriting the application.

**Status: synthetic control and difference-in-differences are implemented.**
Everything else on this page is an extension point.

---

## The pipeline inside the engine

```
observe → features → match → estimate → test → assemble
```

Each stage is a separate module with a narrow input and output, which is what
lets a new estimator be added at one point rather than threaded through.

| Stage | Module | Produces |
| --- | --- | --- |
| Observe | `engine/observation/` | `TimeSeries` per unit |
| Features | `engine/features/` | Covariates per unit *(not built)* |
| Match | `engine/matching/` | `DonorPool` with exclusions and balance |
| Estimate | `engine/causal/` | A fit with diagnostics |
| Test | `engine/uncertainty/` | Placebo distribution, sensitivity |
| Assemble | `engine/assembler.py` | `EvidenceBundle` with a verdict |

---

## Estimator selection

Estimators are named, not hard-coded:

```python
EstimationSpec(
    primary      = ModelRef(model_id="synthetic-control", variant="default"),
    cross_checks = (ModelRef(model_id="difference-in-differences"),),
)
```

`ModelRef` carries `model_id`, a `variant` and free-form `parameters`. A
specification curve is many `ModelRef`s over one request. Adding an estimator
means implementing it, registering a `model_id`, and making it selectable — not
changing the request shape, the result shape or anything in the platform.

### Requirements on any estimator added here

Non-negotiable, because they are what makes the output defensible:

1. **Report its own diagnostics.** An estimator that cannot say when it is
   unreliable does not go in. DiD reports pre-trend divergence; synthetic
   control reports pre-period RMSPE and weight identification.
2. **Refuse rather than extrapolate.** Raise `InsufficientDataError` or
   `DonorPoolError` instead of returning a fragile number.
3. **Be deterministic given a seed.**
4. **Emit provenance** naming the method and every parameter.
5. **Never emit a carbon unit** from an index-valued input.

---

## Implemented

### Synthetic control (primary)

Weights donors to track the treated unit through the pre-period; the
post-period gap is the estimated effect.

Weights are constrained to the unit simplex (`w ≥ 0, Σw = 1`). That constraint
is the point: it forbids extrapolation outside the convex hull of observed
donors, so the counterfactual is always an attainable combination of real
places. Unconstrained regression fits the pre-period better, by inventing a
counterfactual built from places that do not exist.

Solved with FISTA — accelerated projected gradient with Duchi et al. simplex
projection — on numpy alone. No SciPy, no CVXPY, so the analytical pipeline and
CI run anywhere.

Reports: pre/post RMSPE, the ratio, contributing donors, convergence, and
`weights_are_identified` (false when donors outnumber pre-periods, where the
counterfactual path is determined but individual weights are not).

### Difference-in-differences (cross-check)

Cheaper and more transparent, and entirely dependent on parallel trends — which
is not testable. Its pre-period analogue is, so the implementation always
reports pre-trend slope divergence *and* the level bias that divergence would
produce if it simply continued. Comparing a per-period slope directly against a
level difference is dimensionally wrong; this was a real bug, caught by a test.

When DiD and synthetic control disagree substantially, **the disagreement is
reported as a finding**, not reconciled. It usually means parallel trends fails.

### Inference

With one treated unit there is no sampling distribution, so significance comes
from permutation:

- **In-space placebos** — refit pretending each donor was treated; rank the
  real unit's post/pre RMSPE ratio in that distribution. Phipson–Smyth add-one
  correction, so a p-value is never zero and its floor `1/(J+1)` is stated.
- **In-time placebos** — move the treatment date earlier inside the pre-period.
  An effect detected before anything happened is misspecification.
- **Leave-one-out** — drop each contributing donor; a sign flip means the
  finding belongs to one region and is not a project-level conclusion.
- **Permutation intervals** and **specification curves** for spread.

---

## Extension points

| Method | Why it is wanted | Attaches as | Contract change? |
| --- | --- | --- | --- |
| **Matched controls** | Simpler, more interpretable than SCM for some audiences | `model_id="matched-controls"` | No |
| **Event study** | Effect dynamics over time rather than one average | New `model_id`; emits per-period evidence | Minor (new evidence ids) |
| **Causal forests** | Heterogeneous effects across subregions | New `model_id`; needs unit-level covariates | Minor |
| **Heterogeneous treatment effects** | Which parts of a project worked | Consumes the above | Minor |
| **Augmented SCM** | Bias correction when pre-fit is imperfect | `variant="augmented"` | No |
| **Synthetic DiD** | Combines both identification strategies | New `model_id` | No |
| **Spillover analysis** | Quantify leakage rather than only excluding it | New stage; leakage-belt units as a second treated group | Minor |
| **Sensitivity bounds** (Rosenbaum) | How strong must unobserved confounding be to overturn this? | `RobustnessSpec` flag | Minor (additive flag) |
| **Multi-method agreement** | Report concordance across estimators | Assembler consumes several fits | Minor |

**Multi-method agreement is the architecturally interesting one.** The honest
version reports the spread across methods and treats disagreement as
information, rather than picking a winner. The assembler already accepts
multiple fits; making this real is mostly a reporting decision, not a
structural one.

---

## The verdict gate chain

The verdict is decided by explicit rules, not by a model and not by a score:

```
1. enough admitted donors
2. pre-treatment fit good enough that the post gap means something
3. placebo inference available and the divergence distinguishable from it
4. leave-one-out sign stability
5. covariate balance within the conventional guideline
```

**Any failed gate short-circuits to `INCONCLUSIVE`.** There is no weak-positive
path, by construction. Adding one would be the single most damaging change
possible to this codebase, which is why `AGENTS.md` lists the gate chain as a
thing not to modify without agreement.

---

## The carbon gap

The pipeline estimates an effect on a spectral index. Claims are in tCO2e. These
are **not commensurable**, so `run_analysis` passes no divergence ratio and the
verdict returns `INCONCLUSIVE` with that as its stated reason.

That is the correct answer, not a missing feature. Closing it honestly requires:

```
index → canopy structure → above-ground biomass density
      → carbon fraction (~0.47, species-dependent)
      → CO2-equivalent (× 44/12)
```

Every arrow adds error, which must be propagated rather than dropped. The
resulting interval will be wide, and **a wide honest interval is the
deliverable**. A narrow one would be evidence of a mistake.

Deliberately scheduled after the indicator-level estimate is validated on
Kariba: stacking a conversion on an unvalidated estimate compounds two
uncertainties.

---

See also: [`docs/science/causal-inference.md`](../science/causal-inference.md)
for the estimand, the mathematics and the identifying assumptions.
