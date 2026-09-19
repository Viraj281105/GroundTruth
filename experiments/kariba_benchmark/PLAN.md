# Kariba REDD+ benchmark — pre-registered plan

**Status: NOT RUN.** Blocked on roadmap milestones M1 (real observation data)
and M2 (real donor pools). This file is written before any real data has touched
the pipeline, so that a later result cannot be graded against a moved goalpost.

## Question

Does an independent, satellite-based causal estimate of the Kariba REDD+
project's incremental effect agree in direction and relative magnitude with the
published third-party correction?

## Reference figure (not ours)

Following a two-year investigation concluded in 2025, Verra found that a
reported 57% of the approximately 27 million credits issued by the Kariba REDD+
project (VCS 902, Zimbabwe, ~785,000 ha) were in excess of the emission
reductions the project achieved.

*Source: Verra investigation findings, as reported by Carbon Herald and Climate
Home News, September 2025.*

This figure is recorded in `cases/kariba-redd.yaml` under `known_reference`.
**The pipeline never reads it.** It is used only for post-hoc comparison.

## Specification, fixed in advance

| Parameter | Value |
| --- | --- |
| Primary indicator | NDVI, annual median composite |
| Secondary indicators | EVI, Hansen forest area |
| Pre-period | 2001–2010 |
| Post-period | 2011–2022 |
| Treatment date | 2011 (crediting period start) |
| Sensitivity treatment date | 2009 (validation, tests anticipation) |
| Donor search region | Miombo woodland in Zimbabwe, Zambia and Mozambique, outside any registered REDD+ project or protected area |
| Donor pool size | Up to 50 admitted from 80+ candidates |
| Leakage belt | 10 km, excluded from the donor pool |
| Covariates | Rainfall, elevation, slope, road distance, population density |
| Estimator | Synthetic control (primary), DiD (cross-check) |
| Inference | In-space placebo, add-one permutation p-value |
| Robustness | Leave-one-out, in-time placebo, specification curve |

## Pre-registered outcomes

| Outcome | Criterion |
| --- | --- |
| **Strong agreement** | Independent estimate implies substantial over-issuance; placebo p < 0.10; sign stable under leave-one-out; implied excess share within a factor of two of 57% |
| **Partial agreement** | Direction agrees and robustness checks pass, but magnitude falls outside a factor of two |
| **Weak agreement** | Direction agrees but placebo or leave-one-out fails |
| **Disagreement** | Direction disagrees, or the pipeline returns INCONCLUSIVE |

## Commitments

1. **All four outcomes will be reported.** A disagreement is a finding about the
   limits of satellite-based causal screening, and it will be published.
2. **The specification above will not be changed after seeing results.** If a
   different specification is later explored, it is reported as an additional
   specification-curve point, not as a replacement headline.
3. **No carbon comparison without a conversion layer.** Until milestone M4, the
   comparison is on direction and relative magnitude of the observed indicator
   only. The verdict gate already enforces this.
4. **Nothing found here is a finding of misconduct.** Whatever the result, it is
   a screening signal recommending accredited review.

## Threats to validity, listed in advance

| Threat | Why it matters here |
| --- | --- |
| Sensor transition | The 2001–2022 window crosses Landsat 5/7/8 and Sentinel-2; a miscalibrated step looks like land-cover change |
| Rainfall dominance | Miombo NDVI is strongly rainfall-driven; rainfall matching is load-bearing, and a rainfall-only placebo specification must be reported |
| Anticipation | Project activity likely began before 2011 |
| Convex hull | A 785,000 ha project may have no comparably large unprotected donor |
| Leakage beyond the belt | Displacement past 10 km is invisible to this design |

## Outputs

On completion, `results/` will contain the evidence bundle JSON, the
specification curve, the placebo distribution, the donor pool with exclusions,
and a comparison note against the reference figure. The seed, package version,
git SHA and data retrieval date will be recorded with them.
