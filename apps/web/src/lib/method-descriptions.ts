/**
 * What each engine method actually does, keyed by `provenance.method`.
 *
 * Every entry was checked against the producing code in
 * `packages/groundtruth/src/groundtruth/engine/` (and `contracts/provenance.py`
 * for third-party figures). An entry must not describe anything the engine
 * does not do: no V-matrix, no covariate term in the weight objective, no
 * thresholds that are not either fixed in code or recorded in the item's
 * `provenance.parameters`.
 *
 * A method missing from this table gets no description at all. The drawer then
 * shows the method string and its parameters only, never a guessed formula.
 */

export interface MethodDescription {
  /** Human-readable name of the method. */
  title: string;
  /** Plain-language account of what the engine computes, one paragraph each. */
  summary: string[];
  /** Formula lines, in display order. Omitted where a formula would add nothing. */
  formula?: string[];
  /** A limit on how the value may be read. */
  caveat?: string;
}

const DESCRIPTIONS: Readonly<Record<string, MethodDescription>> = {
  'synthetic-control/simplex-constrained-least-squares': {
    title: 'Synthetic control, simplex-constrained least squares',
    summary: [
      "Donor weights are fitted to the project's pre-treatment outcome path, every pre-period weighted equally. The weights are non-negative and sum to one, so the counterfactual is a convex combination of the admitted donors and never extrapolates beyond them.",
      'Covariates decide which donors are admitted; they do not enter the weight objective. There is no predictor-weighting (V) matrix, no intercept and no demeaning: the fit is in levels. The problem is solved by accelerated projected gradient (FISTA).',
      'The effect estimate is the mean post-treatment gap between the project and its weighted donors. Fit diagnostics such as pre-period RMSPE and the post/pre RMSPE ratio come from the same fit.',
    ],
    formula: [
      'min_w  Σ_pre (y₁ₜ − Σᵢ wᵢ yᵢₜ)² + λ ‖w‖²',
      'subject to  wᵢ ≥ 0,  Σᵢ wᵢ = 1',
      'effect = mean over post-periods of (y₁ₜ − Σᵢ wᵢ yᵢₜ)',
    ],
    caveat:
      "λ is the ridge penalty from the request's estimation settings (0 unless the request sets one); its value is not part of this item's parameters.",
  },
  'in-space-placebo-permutation': {
    title: 'In-space placebo permutation test',
    summary: [
      "The synthetic control is refitted once for each donor, treating that donor as if it were the project. The project is never a donor in these placebo fits. Unless the request turns the screen off, placebo units whose own pre-period fit is worse than a set multiple of the project's are dropped, because their ratios would be meaningless; the number dropped is listed in the parameters.",
      "The p-value is the share of units whose post/pre RMSPE ratio is at least as large as the project's, with an add-one correction, so it can never be smaller than 1 / (J + 1).",
    ],
    formula: [
      'r = RMSPE_post / RMSPE_pre',
      'p = (1 + #{ j : r_j ≥ r_project }) / (J + 1),  J = placebo units retained',
    ],
    caveat:
      'This measures how unusual the divergence is among untreated regions. It is not a probability of misreporting.',
  },
  'in-time-placebo/pre-period-refit': {
    title: 'In-time placebo, pre-period refit',
    summary: [
      'The synthetic control is refitted on pre-treatment periods only, with a fake treatment date inside the pre-period. Nothing happened at that date, so any effect the model finds there is spurious and points to misspecification.',
      'The check passes when the absolute fake effect is below half the absolute estimated effect.',
    ],
    formula: ['passes  ⇔  |fake effect| < 0.5 × |estimated effect|'],
  },
  'convex-hull-necessary-conditions/level-and-envelope': {
    title: 'Convex-hull check, level and envelope conditions',
    summary: [
      "Two necessary conditions for the project's pre-treatment path to be reachable by a convex combination of donors. Level: the project's pre-period mean must lie within the range of donor pre-period means. Envelope: in each pre-period the project must lie between the lowest and highest donor.",
      'The project counts as materially outside the hull when its level excess, in pre-period standard deviations, exceeds the level threshold, or the share of pre-periods outside the envelope exceeds the envelope share threshold. Both thresholds are listed in the parameters.',
    ],
    caveat:
      'These conditions are necessary, not sufficient: passing them does not prove the path lies inside the hull.',
  },
  'leave-one-donor-out-refit': {
    title: 'Leave-one-donor-out refit',
    summary: [
      'The synthetic control is refitted once for each donor that carried non-negligible weight in the main fit, with that donor removed. Donors with negligible weight are skipped because removing them cannot move the estimate.',
      'Reported: the largest absolute change from the main estimate, and whether every refit keeps the main estimate\'s sign.',
    ],
    formula: ['max shift = maxₖ |effect without donor k − main effect|'],
  },
  'specification-curve/one-at-a-time': {
    title: 'Specification curve, one choice at a time',
    summary: [
      "Starting from the request's own specification (the centre), one analytic choice is changed at a time and the synthetic control is refitted, so each deviation can be attributed to the choice it changed. The choices varied in this run are listed in the parameters.",
      'The median, the share of specifications agreeing with the median\'s sign, and the minimum-to-maximum range are computed over every specification; the centre is marked but not privileged.',
    ],
    caveat:
      'The range is a sensitivity envelope, not a confidence interval. Choices listed as not varied in this run need new observations or a re-run of matching.',
  },
  'difference-in-differences': {
    title: 'Difference-in-differences cross-check',
    summary: [
      "A cross-check on the synthetic control, not the primary estimate. It is the change in the project's mean outcome from the pre- to the post-treatment period, minus the same change in the equally weighted mean of the control units (the admitted donors).",
      'A pre-treatment trend comparison between the project and the control mean is reported alongside it.',
    ],
    formula: ['DiD = (ȳ_project,post − ȳ_project,pre) − (ȳ_control,post − ȳ_control,pre)'],
    caveat: 'Valid only under parallel trends, which cannot be tested directly.',
  },
  'cluster-robust-cr1/wild-cluster-bootstrap': {
    title: 'Cluster-robust (CR1) standard error and wild cluster bootstrap',
    summary: [
      "Uncertainty in the difference-in-differences cross-check, from the spread of each control unit's pre-to-post change. The CR1 standard error clusters those changes on the supplied labels; with one unit per cluster it reduces to the unclustered s² / N.",
      'A wild cluster bootstrap multiplies every residual in a cluster by the same random weight (Webb six-point weights below 12 clusters, Rademacher at 12 or more) and gives the interval. The weights, number of draws and seed are listed in the parameters.',
    ],
    formula: [
      'eᵢ = dᵢ − d̄,  dᵢ = control unit i\'s post-minus-pre mean change',
      'SE²_CR1 = G / (G − 1) · Σ_g (Σ_{i∈g} eᵢ)² / N²',
    ],
    caveat:
      "Control-side uncertainty only. With one treated unit, the project's own noise cannot be estimated, so this understates the full uncertainty.",
  },
  'standardised-covariate-distance': {
    title: 'Standardised covariate distance matching',
    summary: [
      "Each candidate's covariates are z-scored with the candidate pool's mean and standard deviation, and candidates are ranked by weighted Euclidean distance to the project. The covariates used are listed in the parameters.",
      "A candidate is excluded if it lies inside the project's leakage belt, falls outside the caliper on any covariate when one is set (common support), or has too few clear pre-treatment observations. Admitted donors beyond the pool cap are excluded by rank.",
    ],
    formula: ['distance = √( Σ_c weight_c · (z_candidate,c − z_project,c)² )'],
  },
  'window-alignment/period-labels': {
    title: 'Window alignment by period label',
    summary: [
      "The pre/post split is taken from period labels, not array positions. Every included series, the project's and each donor's, must carry a finite value for every pre- and post-treatment period; a series that does not stops the run with a refusal rather than being fitted against the wrong treatment date.",
      'Periods returned outside the window, or in a gap between the pre-period end and the post-period start, are dropped and belong to neither side.',
    ],
  },
  'published-third-party-figure': {
    title: 'Published third-party figure',
    summary: [
      'A value taken from a third-party source or the case definition, such as a registry. GroundTruth did not compute it.',
    ],
  },
};

/** The description for a method string, or `null` if the method is not known. */
export function describeMethod(method: string): MethodDescription | null {
  return Object.prototype.hasOwnProperty.call(DESCRIPTIONS, method) ? DESCRIPTIONS[method] : null;
}

/** Every method string with a description, for tests and coverage checks. */
export const DESCRIBED_METHODS: readonly string[] = Object.keys(DESCRIPTIONS);
