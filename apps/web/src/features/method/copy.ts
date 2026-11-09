/** Methodological notes on causal identification, inference, and covariate balance. */
export const METHODOLOGICAL_NOTES = {
  sutvaDonorEligibility:
    'SUTVA donor pool eligibility requires that host districts and adjacent leakage belts be excluded from untreated controls so spillover cannot contaminate the counterfactual.',
  weightIdentification:
    'Weight identification: weights_identified is False when the number of donors J exceeds pre-treatment periods T_0 (J > T_0), because the convex hull system is underdetermined and simplex weights may not be unique.',
  permutationPValueFloor:
    'Finite-sample permutation inference over N untreated placebos has a strict p-value floor of 1 / (N + 1); p-values cannot be zero in finite donor pools.',
  smdCovariateBalance:
    'Standardized Mean Difference (SMD) measures static baseline covariate balance between the treated unit and the weighted donor pool rather than Difference-in-Differences (DiD) estimation error.',
} as const;

export interface StageDetail {
  id: number;
  label: string;
  sub: string;
  tag: string;
  badge: 'deterministic' | 'verified';
  summary: string;
  math: string;
  inputs: string;
  outputs: string;
  guarantee: string;
}

export const STAGE_DETAILS: StageDetail[] = [
  {
    id: 1,
    label: 'Data',
    sub: 'satellite series',
    tag: 'Earth Observation',
    badge: 'deterministic',
    summary:
      'Extracts multi-spectral surface reflectance time series (e.g. Landsat, Sentinel-2) inside project boundaries and surrounding regions over decades.',
    math: 'Cloud-masking, radiometric normalization, spatial aggregation over verified polygon boundaries.',
    inputs: 'Registry project boundary polygon geometry (.geojson), satellite surface reflectance archive',
    outputs: 'Treated unit time-series panel Y_1t and donor candidates panel Y_jt',
    guarantee: 'Deterministic pipeline execution; never imputed with generative models.',
  },
  {
    id: 2,
    label: 'Donor pool',
    sub: 'similar land',
    tag: 'Causal Identification',
    badge: 'deterministic',
    summary:
      'Screens candidate comparison regions that share ecological, climatic, and topographical conditions with the project area while strictly isolating spillover.',
    math: 'Standardized Mean Difference (SMD) baseline matching; strict SUTVA exclusion of host districts and leakage belts.',
    inputs: 'Biome classification, elevation, slope, annual precipitation, distance to roads and settlements',
    outputs: 'Admitted donor candidate matrix J with zero spillover risk',
    guarantee: 'Algorithmic SUTVA filter; no donor selection by human preference or model steering.',
  },
  {
    id: 3,
    label: 'Synthetic twin',
    sub: 'weighted blend',
    tag: 'Convex Optimization',
    badge: 'deterministic',
    summary:
      'Solves for a non-negative weighted combination of untreated donor units that precisely tracks the project area across pre-treatment years.',
    math: 'Simplex-constrained least squares: min_w ||Y_1^pre - Y_0^pre w||_2^2 subject to w_i >= 0, sum w_i = 1.',
    inputs: 'Pre-period time series Y_1^pre, donor candidate matrix Y_0^pre',
    outputs: 'Optimal simplex weight vector w*, pre-intervention fit RMSE',
    guarantee: 'Convex quadratic program; weights_identified verified against degrees of freedom (T_0 >= J).',
  },
  {
    id: 4,
    label: 'Estimate',
    sub: 'gap + uncertainty',
    tag: 'Causal Effect',
    badge: 'deterministic',
    summary:
      'Projects the synthetic control through the post-intervention era. The difference between satellite observations and the twin is the estimated effect.',
    math: 'Point estimate: tau_hat_t = Y_1t - hat{Y}_0t; cumulative effect over the crediting window with sensitivity envelopes.',
    inputs: 'Trained simplex weights w*, post-period satellite observations',
    outputs: 'Effect time-series tau_hat_t, average treatment effect point estimate',
    guarantee: 'Direct counterfactual subtraction; uncertainty envelopes based on specification refits.',
  },
  {
    id: 5,
    label: 'Stress tests',
    sub: 'placebo, robustness',
    tag: 'Permutation & Sensitivity',
    badge: 'deterministic',
    summary:
      'Subjects the estimate to rigorous placebo refits in space and time, leave-one-out donor deletions, and multiverse specification curves.',
    math: 'In-space permutation p-value: p = (1 + sum I(|tau_j| >= |tau_1|)) / (J + 1); leave-one-out envelope; in-time pre-period refit.',
    inputs: 'Fitted model, untreated donor units, alternative specification grids',
    outputs: 'Finite-sample permutation p-value (floor 1 / (N + 1)), specification curve distribution',
    guarantee: 'Exhaustive permutation checks; inconclusive results reported honestly without stretching.',
  },
  {
    id: 6,
    label: 'Evidence',
    sub: 'bundle of numbers',
    tag: 'Cryptographic Provenance',
    badge: 'deterministic',
    summary:
      'Assembles every calculated point estimate, uncertainty bound, p-value, diagnostic test, parameter, and dataset identifier into an immutable bundle.',
    math: 'Deterministic serialization, SHA-256 specification hash, JSON-LD evidence graph.',
    inputs: 'All intermediate calculation results, random seeds, engine git commit hash',
    outputs: 'Immutable verification bundle (evidence.json), spec_hash fingerprint',
    guarantee: '100% reproducible; tamper-evident cryptographic fingerprint.',
  },
  {
    id: 7,
    label: 'Narration',
    sub: 'verified',
    tag: 'Audited Synthesis',
    badge: 'verified',
    summary:
      'Translates the verification bundle into clear, structured, plain-language reports for reviewers, auditors, and investors.',
    math: 'Bidirectional numerical checking: text regex scanner checks every extracted numeral against Stage 6 bundle items.',
    inputs: 'Stage 6 evidence bundle, deterministic report templates',
    outputs: 'Audit-ready case report, executive briefing, transparency disclosure',
    guarantee: 'Zero hallucinations: any ungrounded number immediately rejects the text.',
  },
];

export const GLOSSARY_CATEGORIES = [
  { id: 'all', label: 'All terms' },
  { id: 'causal', label: 'Causal Inference' },
  { id: 'diagnostics', label: 'Diagnostics & Stress Tests' },
  { id: 'remote-sensing', label: 'Remote Sensing & Data' },
  { id: 'integrity', label: 'Audit & Governance' },
] as const;

export const TERM_CATEGORY_MAP: Record<string, 'causal' | 'diagnostics' | 'remote-sensing' | 'integrity'> = {
  additionality: 'causal',
  counterfactual: 'causal',
  'synthetic-control': 'causal',
  'donor-pool': 'causal',
  placebo: 'diagnostics',
  'p-value': 'diagnostics',
  'pre-fit': 'diagnostics',
  leakage: 'causal',
  'spec-curve': 'diagnostics',
  did: 'causal',
  'parallel-trends': 'causal',
  ndvi: 'remote-sensing',
  refusal: 'integrity',
  provenance: 'integrity',
  'spec-hash': 'integrity',
  simulated: 'remote-sensing',
  review: 'integrity',
};

/** English copy for "How it works". Neutral wording (R2): no accusation, no certainty. */
export const METHOD_COPY = {
  title: 'How it works',
  intro: 'From satellite data to a verified report, in seven stages.',
  pipeline: {
    alt: 'Pipeline in seven stages: data, donor pool, synthetic twin, estimate, placebo and robustness checks, evidence bundle, narration verified against the evidence.',
    caption: 'Every number in the final report is traced to the evidence bundle; narration cannot add one.',
    nodes: [
      { label: 'Data', sub: 'satellite series' },
      { label: 'Donor pool', sub: 'similar land' },
      { label: 'Synthetic twin', sub: 'weighted blend' },
      { label: 'Estimate', sub: 'gap + uncertainty' },
      { label: 'Stress tests', sub: 'placebo, robustness' },
      { label: 'Evidence', sub: 'bundle of numbers' },
      { label: 'Narration', sub: 'verified' },
    ],
  },
  steps: {
    title: 'The method in three steps',
    items: [
      {
        heading: '1. Build a comparison',
        body: 'Satellite records of the project area before the project began are matched against many similar areas that were not part of it. A weighted blend of those areas, a synthetic control, is chosen so that it follows the project area closely over the years before the project.',
      },
      {
        heading: '2. Estimate the difference',
        body: 'After the project start, the blend continues as the estimate of what would likely have happened without the project, the counterfactual. The gap between what satellites observed and that estimate is the estimated effect, reported with its uncertainty.',
      },
      {
        heading: '3. Stress-test the result',
        body: 'The same procedure is repeated on areas that had no project (placebo tests), on earlier dates, with each comparison area left out in turn, and under alternative settings. A result that does not stand out from these checks is reported as inconclusive, not stretched.',
      },
    ],
  },
  ai: {
    title: 'What the AI does and does not do',
    does: [
      'Writes plain-language narration of numbers the engine has already computed.',
      'Every number in that narration is checked against the evidence; text with an unmatched number is rejected and replaced by a fixed template.',
    ],
    doesNot: [
      'It never computes an estimate, a weight, a p-value or a verdict.',
      'It is not used to decide which areas are comparable.',
      'It cannot change a result; it can only describe one.',
    ],
    status: 'AI narration is not switched on in this build. Reports use fixed templates.',
  },
  assumptions: {
    title: 'Assumptions',
    items: [
      'Comparison areas were not themselves affected by the project (no spill-over): under SUTVA donor pool eligibility, host districts and leakage belts must be excluded from untreated controls.',
      'The blend that tracks the project area before the project would have kept tracking it afterwards; weights_identified is False when donors J exceed pre-treatment periods T_0.',
      'Satellite measures such as a vegetation index are consistent over time and across sensors.',
      'The set of comparison areas covers the conditions the project area faced; Standardized Mean Difference (SMD) summarizes static baseline covariate balance rather than DiD estimation error.',
    ],
  },
  limits: {
    title: 'Limits and honest status',
    items: [
      'Analyses currently run on simulated data and are labelled as simulated wherever they appear.',
      'Retrieval of real satellite data is not implemented yet; such requests are refused rather than filled in.',
      'A vegetation index is not carbon. Conversion to tonnes of CO2 is not implemented, because it needs site-specific allometry and an error budget.',
      'A result depends on its comparison areas. A thin or poorly matched set weakens it, and the engine says so. Finite-sample permutation p-values have a floor of 1 / (N + 1).',
      'A divergence between the estimate and a project claim warrants accredited review. It is a screening signal, not a finding about any person or organisation.',
    ],
  },
  methodologicalNotes: METHODOLOGICAL_NOTES,
  glossary: {
    title: 'Glossary',
    intro: 'Every term the interface explains, in plain language first and technical wording second.',
    plain: 'In plain words',
    technical: 'Technically',
  },
} as const;
