# Glossary

Terms that mean something specific here. Where a word has a loose everyday
meaning and a precise meaning in this repository, the precise one wins.

## Domain

**Additionality** — the climate benefit that exists *because* a project
happened and would not have existed otherwise. Counterfactual by definition, so
it must be estimated rather than measured. The quantity carbon markets actually
sell.

**Baseline** — the developer's claimed counterfactual: what they assert would
have happened without the project. Under test here, never an input to our
estimate.

**Counterfactual** — what the project area would have done absent the
intervention. Unobservable. Estimated from a weighted combination of comparable
untreated regions.

**Donor pool** — the admitted set of untreated regions from which the
counterfactual is built. Its composition determines the answer, which is why the
pool, its exclusions and its balance statistics are reported as evidence rather
than kept as implementation detail.

**Leakage** — deforestation displaced by a project into surrounding areas. A
region inside the leakage belt is a treated unit in disguise and is excluded
from the donor pool.

**Leakage belt** — the monitored ring around a project boundary (10 km by
default) whose units are excluded from donor eligibility.

**Crediting period** — the window over which a project issues credits. Used as
the default treatment date, with an earlier validation date available as an
anticipation sensitivity check.

**REDD+** — Reducing Emissions from Deforestation and forest Degradation. The
project category most of our cases fall under.

**Registry** — the body that certifies and issues credits (Verra/VCS, Gold
Standard, Plan Vivo).

## Method

**Synthetic control** — the primary estimator. Weights donors to track the
treated unit through the pre-period, then reads the post-period gap as the
estimated effect. Weights are constrained to the unit simplex.

**Unit simplex** — the constraint `w ≥ 0, Σw = 1`. Forbids extrapolation outside
the convex hull of observed donors, so the counterfactual is always an
attainable combination of real places.

**Difference-in-differences (DiD)** — a transparent cross-check estimator. Valid
only under parallel trends, so it always reports its own pre-trend divergence
diagnostic.

**Parallel trends** — the DiD identifying assumption: absent the intervention,
treated and control units would have moved together. Not testable; its
pre-period analogue is.

**RMSPE** — root mean squared prediction error. Pre-period RMSPE measures fit
quality; the post/pre ratio is the placebo test statistic.

**In-space placebo** — refitting the model pretending each donor was treated, to
build a reference distribution. Answers "would a gap this large appear for an
untreated place?"

**In-time placebo** — moving the treatment date earlier within the pre-period. A
model that detects an effect before anything happened is detecting its own
misspecification.

**Add-one correction** — Phipson–Smyth. A permutation p-value is
`(1 + #{placebos ≥ observed}) / (1 + J)`, so it is never reported as zero. With
*J* donors the floor is `1/(J+1)`.

**Leave-one-out** — refitting with each contributing donor removed. If the sign
flips, the finding belongs to one comparison region and is not a project-level
conclusion.

**Specification curve** — the estimate across all equally defensible
specifications, reported instead of the single best-looking one.

**Standardised mean difference (SMD)** — post-match covariate balance. Above
~0.25 is conventionally poor and blocks a substantive verdict here.

**Common support** — the covariate range spanned by the donor pool. Candidates
outside it are excluded rather than extrapolated over.

**Sensitivity envelope** — the *range* across specifications or leave-one-out
refits. **Not a confidence interval**, and must never be rendered as one.
Carried as `Confidence.kind = "sensitivity-envelope"`.

## Remote sensing

**NDVI** — Normalised Difference Vegetation Index, `(NIR − Red)/(NIR + Red)`. A
reflectance ratio. Saturates over closed canopy. **Not carbon.**

**EVI** — Enhanced Vegetation Index. Less prone to canopy saturation, used where
NDVI would lose sensitivity.

**NBR** — Normalised Burn Ratio. Separates fire disturbance from clearing.

**SCL** — Sentinel-2 Scene Classification Layer, the band used for cloud and
shadow masking.

**Composite** — the temporal reduction of many scenes to one value per period.
Median, not mean, because residual undetected cloud is a heavy positive outlier.

**Clear observation count** — how many usable scenes back a period. A year with
two is not the same measurement as a year with twenty, and the difference is
carried rather than smoothed over.

**Canopy saturation** — above roughly NDVI 0.8, additional biomass produces no
index change. Why a forest can double its carbon with no NDVI signal.

**Allometry** — species- and site-specific equations relating structure to
biomass. Typically 20–30% error at plot level, worse extrapolated.

## Codebase

**Contract** — `groundtruth.contracts`. The shared, versioned boundary between
engine and platform. Changing it requires both owners.

**Engine** — `groundtruth.engine`. Pure computation, no I/O. Viraj.

**Platform** — `groundtruth.platform`. API, data services, jobs, persistence,
reporting, deployment. Bhumi.

**AnalysisRequest** — the engine's only input. Self-contained and serialisable.

**AnalysisResult** — the engine's only output, returned for every outcome
including refusal.

**EvidenceBundle** — the structured evidence object. Immutable collection of
`Evidence` items with a verdict and warnings.

**Evidence** — one auditable value with unit, optional interval, mandatory
provenance and structured qualifiers.

**Provenance** — where a value came from and how it was produced: source,
method, parameters, upstream evidence ids, fingerprint.

**spec_hash** — deterministic hash of an analysis specification. The
reproducibility key and the platform cache key. Same hash + same seed + same
engine version yields identical numbers.

**DataAccess ports** — the interfaces through which the engine asks for data.
The seam between methodology and plumbing.

**Refusal** — `EngineStatus.REFUSED`. The system correctly declining to produce
a fragile number. A legitimate scientific outcome, styled differently from an
error.

**Verdict gate chain** — the ordered checks (donor count, pre-treatment fit,
placebo distinguishability, leave-one-out sign stability, covariate balance).
Any failure short-circuits to `INCONCLUSIVE`; there is no weak-positive path.

**Grounding** — verification that generated narrative contains only numbers
present in the evidence bundle and no prohibited assertions.

**data_mode** — `observed` or `simulated`. Declared by the platform, validated so
synthetic datasets cannot be labelled observed, and propagated to the UI banner.

**known_reference** — a published third-party finding recorded in a case
definition for post-hoc validation. The pipeline never reads it.
