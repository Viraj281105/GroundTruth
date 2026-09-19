# 5. Causal inference

## The estimand

Let $Y_{it}$ be the observed indicator for unit $i$ in period $t$. Unit 1 is the
project, treated from period $T_0+1$. Units $2 \ldots J+1$ are untreated donors.

The quantity of interest is

$$\tau_{1t} = Y_{1t}^{(1)} - Y_{1t}^{(0)}, \qquad t > T_0$$

where $Y_{1t}^{(1)}$ is observed and $Y_{1t}^{(0)}$ — the project's outcome had
it not been treated — never is. Everything below is about estimating that
missing term credibly.

## Synthetic control

Estimate $Y_{1t}^{(0)}$ with a weighted average of donors:

$$\hat{Y}_{1t}^{(0)} = \sum_{j=2}^{J+1} w_j Y_{jt}$$

Weights are chosen to minimise pre-treatment discrepancy:

$$\mathbf{w}^* = \arg\min_{\mathbf{w}} \sum_{t=1}^{T_0} \left(Y_{1t} - \sum_j w_j Y_{jt}\right)^2$$

subject to

$$w_j \ge 0 \quad \forall j, \qquad \sum_j w_j = 1$$

### Why the simplex constraint matters

Unconstrained regression would fit the pre-period better. It would do so by
assigning large positive and negative weights that extrapolate far outside the
range of anything observed — a counterfactual built from places that do not
exist. The simplex constraint forbids that. The counterfactual is always an
attainable convex combination of real regions, which is what makes it arguable
in front of a reviewer.

The cost is that if the project lies outside the convex hull of its donors, no
weighting can fit it. That is not a failure to route around; it is the method
telling you the donor pool is inadequate.

### Solver

`solve_simplex_least_squares` uses FISTA — projected gradient with Nesterov
momentum — with Duchi et al. (2008) simplex projection. numpy only.

### Identification of the weights

When $J > T_0$ (more donors than pre-treatment periods) the fitting problem is
rank-deficient: many different weight vectors reproduce the pre-period path
equally well. The **counterfactual path and the effect estimate remain well
determined**, but the attribution of weight to individual donors does not.

The system reports this as `fit.weights_identified` evidence and attaches a
run warning. A report must not present an unidentified weight vector as the
only comparison set consistent with the data. Convergence is therefore assessed
on the objective, not on the weights.

## Inference

With a single treated unit there is no sampling distribution. Significance comes
from permutation.

### Test statistic

$$R_1 = \frac{\text{RMSPE}_{\text{post}}}{\text{RMSPE}_{\text{pre}}}$$

The ratio, not the raw gap. A large post-period gap is uninformative if the
model never fitted the unit well to begin with; the ratio measures divergence
*relative to the model's own demonstrated accuracy* on that unit.

### In-space placebos

Refit pretending each donor $j$ was treated, giving $R_j$. The permutation
p-value uses the Phipson–Smyth add-one correction:

$$p = \frac{1 + \#\{j : R_j \ge R_1\}}{1 + J}$$

so a p-value is never reported as exactly zero. With 40 donors the smallest
attainable p-value is 0.024, and the system says so rather than implying more
precision than the design supports.

Placebo units whose own pre-period fit is much worse than the treated unit's are
excluded. Units the model cannot fit before treatment produce meaningless ratios
and, if retained, inflate the reference distribution's tail.

### In-time placebos

Move the treatment date earlier inside the pre-period and refit. A detected
"effect" before anything happened is detecting misspecification, not an
intervention.

## Difference-in-differences

$$\hat{\tau}_{\text{DiD}} = (\bar{Y}_{1,\text{post}} - \bar{Y}_{1,\text{pre}}) - (\bar{Y}_{C,\text{post}} - \bar{Y}_{C,\text{pre}})$$

Used only as a cross-check. It rests entirely on parallel trends, which is not
testable. Its pre-period analogue is, so the implementation always reports the
pre-trend slope divergence *and* the level bias that divergence would produce on
its own if it simply continued. The two must be commensurable to be compared,
which is why the raw slope alone is not the screen.

When DiD and synthetic control disagree substantially, that disagreement is
itself reported. It usually means parallel trends fails, and the synthetic
control is the one to trust.

## Identifying assumptions, stated plainly

| Assumption | What it means | How it can fail |
| --- | --- | --- |
| **No interference (SUTVA)** | Donors are unaffected by the project | Leakage: the project displaces deforestation into a donor region |
| **Convex hull** | The project is spanned by its donors | An unusually wet, remote or steep project has no comparable neighbours |
| **No anticipation** | Behaviour did not change before the crediting period | Developers often begin activity during validation, years before crediting |
| **Stable relationship** | The pre-period donor–project relationship persists | A regional shock that hits the project differently breaks it |
| **Measurement comparability** | The indicator means the same thing across units and time | Sensor changes, tidal state, phenological offsets |

Each failure mode has a corresponding mitigation in the pipeline: the leakage
belt exclusion, the common-support caliper, an option to move the treatment date
earlier, the placebo suite, and the masking audit respectively. None of them is
a guarantee.

## NDVI is not carbon

This is the point on which the whole project's credibility rests.

NDVI is a normalised ratio of near-infrared to red reflectance. It responds to
chlorophyll density and canopy structure. Carbon is a mass of stored element.
They are not the same kind of quantity, and no arithmetic converts one to the
other.

Specifically:

- **NDVI saturates.** Above roughly 0.8 it stops responding to additional
  biomass. A forest that doubles its above-ground carbon may show no NDVI
  change at all.
- **NDVI responds to moisture and phenology.** A wet year raises NDVI without
  adding a gram of carbon.
- **NDVI has no depth.** Above-ground biomass, below-ground biomass, deadwood
  and soil carbon are separate pools. Soil carbon alone can exceed the
  above-ground pool in peat and mangrove systems.
- **Allometry is species- and site-specific.** Converting canopy metrics to
  biomass requires local allometric equations with their own substantial error,
  typically 20–30% at plot level and worse when extrapolated.

`groundtruth.core.units.assert_not_index_to_carbon` raises on any attempt to
convert an index to a carbon unit, and a parametrised test asserts it for every
index/carbon pair.

### What this means for the current output

The pipeline estimates an effect on a spectral index. The developer's claim is
in tCO2e. **These are not commensurable**, so `run_verification` passes no
divergence ratio and the verdict is `INCONCLUSIVE` with the rationale that the
claim is not expressed in comparable units.

That is the correct answer, not a gap in the implementation. Closing it
honestly requires a biomass layer — ESA CCI or GEDI L4B above-ground biomass
density — with its own error propagated through to the final interval. That is
tracked as a P1 issue, not quietly approximated.

### The route from index to carbon, when it is built

```
spectral index  →  canopy structure  →  above-ground biomass density
                →  carbon fraction (≈0.47, species-dependent)
                →  CO2-equivalent (×44/12)
```

Every arrow adds error. The error must be propagated, not dropped, and the
resulting interval will be wide. A wide honest interval is the deliverable.

## Divergence is not fraud

If the independent estimate differs materially from the claim, the possible
explanations include, in no particular order:

- the baseline methodology was optimistic;
- the donor pool is inadequate and *our* estimate is wrong;
- leakage occurred and neither figure captures it;
- the indicator does not track what the project actually protects;
- a sensor transition introduced a step;
- the project genuinely over-issued.

Only the last is misconduct, and nothing in a satellite time series can
distinguish it from the others. The system reports divergence and recommends
accredited review. `VerdictLabel` has no value that reads as an accusation, and
the grounding layer blocks text that would supply one.

## References

- Abadie, Diamond & Hainmueller (2010). *Synthetic Control Methods for
  Comparative Case Studies*. JASA 105(490).
- Abadie (2021). *Using Synthetic Controls: Feasibility, Data Requirements, and
  Methodological Aspects*. Journal of Economic Literature 59(2).
- Duchi, Shalev-Shwartz, Singer & Chandra (2008). *Efficient Projections onto
  the L1-Ball*. ICML.
- Beck & Teboulle (2009). *A Fast Iterative Shrinkage-Thresholding Algorithm*.
  SIAM Journal on Imaging Sciences 2(1).
- Phipson & Smyth (2010). *Permutation P-values Should Never Be Zero*.
  Statistical Applications in Genetics and Molecular Biology 9(1).
- West, Börner, Sills & Kontoleon (2020). *Overstated carbon emission
  reductions from voluntary REDD+ projects*. PNAS 117(39).
- Guizar-Coutiño et al. (2022). *A global evaluation of the effectiveness of
  voluntary REDD+ projects*. Conservation Biology 36(6).

---

Previous: [4. Data sources](04-data-sources.md) · Next: [6. Validation](06-validation.md)
