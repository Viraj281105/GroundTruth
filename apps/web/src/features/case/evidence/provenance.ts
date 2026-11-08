/**
 * Where every number on an evidence screen comes from. Three kinds only, and a
 * screen must say which one it is showing. Pure data, no React, so it is tested
 * directly and shared by the evidence, robustness, overview and report views.
 */

export type EvidenceKind = 'real-observation' | 'synthetic-benchmark' | 'derived-analysis';

export interface KindInfo {
  label: string;
  /** One sentence a reader can act on. */
  meaning: string;
}

export const EVIDENCE_KINDS: Record<EvidenceKind, KindInfo> = {
  'real-observation': {
    label: 'Real observation',
    meaning: 'Measured by an instrument or station and retrieved from a public source.',
  },
  'synthetic-benchmark': {
    label: 'Synthetic benchmark',
    meaning: 'Generated offline by the benchmark data provider. It is not a satellite observation of any real place.',
  },
  'derived-analysis': {
    label: 'Derived analysis',
    meaning: 'Computed by the engine from the inputs named next to it. Only as real as those inputs.',
  },
};

/** Where the evidence on screen was produced. */
export type EvidenceOrigin = 'precomputed-fixture' | 'fresh-run';

/**
 * Which source wins. A run the reader asked for by id (`?run=<id>`) always wins
 * over the bundled precomputed fixture: a newly completed analysis must never be
 * replaced by an older one. The fixture is used only when no run was named.
 */
export function chooseEvidenceSource(runId: string | null, hasFixture: boolean): 'fresh-run' | 'precomputed-fixture' | 'none' {
  if (runId) return 'fresh-run';
  return hasFixture ? 'precomputed-fixture' : 'none';
}

export const SOURCE_COPY = {
  fixtureTitle: 'Synthetic benchmark - precomputed',
  fixtureBody:
    'Everything on this screen comes from a precomputed synthetic benchmark stored with the app. It was generated offline with a known injected effect. It is not a satellite observation, and it is not the result of a run you started.',
  freshTitle: 'Fresh run on the synthetic benchmark engine',
  freshBody:
    'These numbers come from the stored run named below, computed by the engine on synthetic benchmark data. This is not live satellite ingestion.',
  freshVizLimit:
    'Not available for a fresh run: the API serves the evidence bundle (effect, fit, placebo and specification numbers) but not the counterfactual path, the placebo distribution, the donor map weights or the timeline. They are not drawn here, and nothing has been substituted for them. The precomputed benchmark at /cases/<case>/evidence (without ?run=) is the only place those series exist, and it is a different run.',
  runLabel: 'Run id',
} as const;

export interface ScopeRow {
  kind: EvidenceKind | 'not-integrated' | 'not-calibrated' | 'inconclusive';
  badge: string;
  statement: string;
  /** True when the sentence is about Kariba data and must not appear on another case. */
  karibaOnly?: boolean;
}

/** What the project has and has not shown. Order is the order a reviewer should read it. */
export const EVIDENCE_SCOPE: ScopeRow[] = [
  {
    kind: 'real-observation',
    badge: 'Real observation',
    statement: 'Sentinel-2 L2A zonal composites for Kariba, 2021-2023 only (cached). Three post-treatment years, no donors, no pre-period.',
    karibaOnly: true,
  },
  {
    kind: 'synthetic-benchmark',
    badge: 'Synthetic benchmark',
    statement: 'The vegetation panel behind every causal estimate (Kariba plus donors, 2001-2022) is synthetic. It is not satellite data.',
    karibaOnly: true,
  },
  {
    kind: 'real-observation',
    badge: 'Real observation',
    statement: 'Climate series: CHIRPS rainfall and NASA POWER temperature. These are real but are not part of the synthetic vegetation outcomes.',
    karibaOnly: true,
  },
  {
    kind: 'not-integrated',
    badge: 'Not yet integrated',
    statement: 'Climate diagnostics are implemented separately and are not yet part of the primary verification API. No result on this screen is climate-adjusted.',
  },
  {
    kind: 'not-calibrated',
    badge: 'Not calibrated',
    statement: 'Carbon impact is not calibrated. NDVI change is not carbon, and no tCO2e figure is estimated.',
  },
  {
    kind: 'inconclusive',
    badge: 'Inconclusive',
    statement: 'Causal attribution is inconclusive. Real climate data and synthetic vegetation outcomes are not combined into an observed causal analysis.',
  },
];

/** Rows for one case. Other cases have no real observations wired in, and say so. */
export function scopeFor(caseId: string): ScopeRow[] {
  if (caseId === 'kariba-redd') return EVIDENCE_SCOPE;
  const generic: ScopeRow = {
    kind: 'synthetic-benchmark',
    badge: 'Synthetic benchmark',
    statement: 'The vegetation outcomes behind every estimate for this case are synthetic benchmark data. No real satellite or climate observations are used.',
  };
  return [generic, ...EVIDENCE_SCOPE.filter((r) => !r.karibaOnly && r.kind !== 'synthetic-benchmark')];
}

/** Plain-language account of the numbers that look inconsistent across audit documents. */
export interface Reconciliation {
  id: string;
  label: string;
  value: string;
  explanation: string;
}

export const RECONCILIATION: Reconciliation[] = [
  {
    id: 'headline',
    label: 'Headline effect on this screen: +0.0547 NDVI',
    value: '+0.05474',
    explanation:
      'Precomputed fixture (engine 0.10.0, seed 20260101, injected effect +0.06, 50 admitted donors). The sign is positive; an earlier audit note quoted it as -0.0547, which was a transcription error and exists nowhere in the data.',
  },
  {
    id: 'causal',
    label: 'Causal cross-check: SCM +0.04158, DiD +0.04156',
    value: '+0.04158 / +0.04156',
    explanation:
      'A different synthetic panel (kariba_synthetic_benchmark.json, 2001-2022) analysed on the 37 spatially eligible donors with the climate-integration code. Two estimators on one panel, so they agree closely. Not the same panel or donor pool as the headline.',
  },
  {
    id: 'donors',
    label: 'Donor counts: 37, 50 and 80',
    value: '37 / 50 / 80',
    explanation:
      '37 = real ADM2 districts that pass the spatial rules (32 interior + 5 host-adjacent outside the 10 km belt, out of 50 real districts). 80 = synthetic candidate units configured for the benchmark run (donor_pool_size); 50 = the donors that run admitted, which is the request default cap (max_donors=50). These are different pools, not stale copies of one count; the 37 are not a subset of the 80 synthetic units.',
  },
];
