/**
 * One glossary for the whole UI so every page explains a term the same way.
 * Wording rule (R2): never accusatory, never certain. Sourced from GLOSSARY.md.
 */

export interface GlossaryEntry {
  label: string;
  /** Plain-language meaning, for the Story lens and hover cards. */
  plain: string;
  /** Precise meaning, for the Explorer and Auditor lenses. */
  technical: string;
}

const ENTRIES: Record<string, GlossaryEntry> = {
  additionality: {
    label: 'Additionality',
    plain: 'The climate benefit that exists only because the project happened.',
    technical: 'The difference between observed outcomes and the counterfactual; it cannot be measured directly and must be estimated.',
  },
  counterfactual: {
    label: 'Counterfactual',
    plain: 'What would likely have happened to this land if the project had never existed.',
    technical: 'An unobservable path estimated as a weighted combination of comparable untreated regions.',
  },
  'synthetic-control': {
    label: 'Synthetic control',
    plain: 'A blended "twin" of the project area, built from similar areas that were not part of the project.',
    technical: 'A convex-weighted combination of donor units chosen to track the project area over the pre-intervention period.',
  },
  'donor-pool': {
    label: 'Donor pool',
    plain: 'The set of similar, untouched areas used to build the twin.',
    technical: 'The admitted untreated units from which the counterfactual is formed; its composition determines the estimate and is reported as evidence.',
  },
  placebo: {
    label: 'Placebo test',
    plain: 'A check that pretends other areas were the project, to see whether the project result stands out from chance.',
    technical: 'Re-running the estimator on untreated units (in space) or earlier dates (in time) to build a reference distribution for the effect.',
  },
  'p-value': {
    label: 'Placebo p-value',
    plain: 'How often a made-up project would look at least this good by chance. Smaller means the result stands out more.',
    technical: 'The add-one-corrected share of placebo effects at least as extreme as the estimate; its floor is 1/(J+1) for J donors.',
  },
  'pre-fit': {
    label: 'Pre-period fit',
    plain: 'How closely the twin followed the project area before the project began.',
    technical: 'Root-mean-square prediction error over the pre-intervention window, compared against the effect size.',
  },
  leakage: {
    label: 'Leakage',
    plain: 'Forest loss that moves to nearby land because of a project.',
    technical: 'Displaced deforestation; units inside the leakage belt are excluded from the donor pool.',
  },
  'spec-curve': {
    label: 'Specification curve',
    plain: 'The same question answered many defensible ways, to see whether the answer holds up.',
    technical: 'The estimate recomputed across reasonable analysis choices and shown as a distribution.',
  },
  did: {
    label: 'Difference-in-differences',
    plain: 'A second, simpler way to estimate the effect, used to cross-check the first.',
    technical: 'Compares change over time between project and comparison units; relies on parallel pre-trends.',
  },
  'parallel-trends': {
    label: 'Parallel trends',
    plain: 'The assumption that project and comparison areas were moving the same way before the project.',
    technical: 'The identifying assumption of difference-in-differences; checked on the pre-period.',
  },
  ndvi: {
    label: 'NDVI',
    plain: 'A satellite measure of how green the land is. It is not a measure of carbon.',
    technical: 'A normalized reflectance ratio. Converting an index to carbon needs a separate biomass model with its own error budget.',
  },
  refusal: {
    label: 'Refusal',
    plain: 'GroundTruth declining to give a number because the data cannot support one responsibly.',
    technical: 'A typed outcome (REFUSED) recorded and shown instead of a fragile estimate.',
  },
  provenance: {
    label: 'Provenance',
    plain: 'The record of where every number came from and how it was produced.',
    technical: 'Inputs, dataset versions, engine version, seed and a derivation graph attached to each evidence item.',
  },
  'spec-hash': {
    label: 'Spec hash',
    plain: 'A fingerprint of exactly what was run, so anyone can re-run it and compare.',
    technical: 'A stable hash of the analysis specification; with the seed and engine version it fixes the output.',
  },
  simulated: {
    label: 'Simulated data',
    plain: 'Made-up test data used to demonstrate the system. It says nothing about any real project.',
    technical: 'Output of the deterministic synthetic fixture, labelled is_simulated=true throughout.',
  },
  'attribution-readiness': {
    label: 'Attribution readiness',
    plain: 'A checklist of whether there is enough good evidence to say a change on the ground was caused by the project, rather than by weather or other factors.',
    technical: 'Criteria that must be met (pre-period length, donor-pool size, data coverage, climate adjustment) before a causal estimate is attempted.',
  },
  spi: {
    label: 'SPI-12 (drought index)',
    plain: 'A score for how dry or wet the last 12 months were compared with normal for the area. Below -1 means unusually dry.',
    technical: 'Standardised Precipitation Index over a 12-month window; values at or below -1 flag drought, at or above +1 flag wet conditions.',
  },
  att: {
    label: 'ATT (estimated effect)',
    plain: 'The estimated difference the project made on its own land, compared with what the twin shows would have happened anyway.',
    technical: 'Average treatment effect on the treated: the mean gap between the project area and its synthetic counterfactual after the intervention.',
  },
  review: {
    label: 'Warrants accredited review',
    plain: 'The independent estimate and the project’s claim differ enough that a qualified auditor should look closer. It is not a finding of wrongdoing.',
    technical: 'A screening signal from a divergence between the estimate and the claim; never a legal or intent conclusion.',
  },
};

export const GLOSSARY_TERMS: readonly string[] = Object.keys(ENTRIES);

export function glossary(id: string): GlossaryEntry | null {
  return ENTRIES[id] ?? null;
}
