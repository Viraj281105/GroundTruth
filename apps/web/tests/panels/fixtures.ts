import type { components } from '../../src/lib/generated/schema';

type S = components['schemas'];

export const dim = (over: Partial<S['DimensionView']> & Pick<S['DimensionView'], 'id' | 'title' | 'status'>): S['DimensionView'] => ({
  status_kind: 'trend_status',
  finding: 'A deterministic finding.',
  known: [],
  suggested: [],
  cannot_establish: [],
  limitation: 'none',
  evidence_needed: 'Nothing further.',
  confidence: 'Low',
  evidence_refs: [],
  diagnostic_refs: null,
  facts: {},
  ...over,
});

const concl = (summary: string, estimable = true, reason: string | null = null): S['ConclusionView'] => ({ summary, dimension_ids: [], estimable, reason });

/** Kariba-shaped assessment (spec 6A "Kariba today"): Level 2, simulated. */
export const karibaAssessment: S['AssessmentView'] = {
  data_mode: 'simulated',
  access_level: 'contribute',
  level: 2,
  level_name: 'Contextual intelligence (simulated)',
  evidence_confidence: 'Low',
  simulated_banner: 'SIMULATED DATA',
  observed_outcome: concl('NDVI moved from 0.41 (2021) to 0.47 (2023).'),
  ecological_assessment: concl('No ecological risk confirmed; signals need field verification.'),
  climate_adjusted_interpretation: concl('', false, 'Needs at least 8 overlapping years; 3 available.'),
  comparative_assessment: concl('', false, 'No donor vegetation series.'),
  attribution: {
    verdict: 'Inconclusive',
    methodology: 'Synthetic control with placebo inference.',
    limitation: 'missing_data',
    finding: 'No pre-treatment and no donor vegetation series.',
    evidence_needed: 'Pre-treatment and donor vegetation series.',
    evidence_refs: [],
    diagnostic_refs: null,
  },
  dimensions: [
    dim({
      id: 'vegetation_trajectory',
      title: 'Vegetation trajectory',
      status: 'Insufficient evidence',
      limitation: 'weak_statistical_power',
      known: ['NDVI 2021 to 2023: 0.41 to 0.47 (+0.06)'],
      cannot_establish: ['A trend with three periods'],
      evidence_needed: 'At least six annual periods.',
    }),
    dim({ id: 'spatial_performance', title: 'Spatial performance', status: 'Insufficient evidence', limitation: 'missing_data', evidence_needed: 'Per-zone composites.' }),
    dim({ id: 'climate_context', title: 'Climate context', status: 'No clear change' }),
    dim({ id: 'ecological_risk', title: 'Ecological risk', status: 'No clear change', suggested: ['signal - requires field verification'] }),
    dim({ id: 'restoration_progress', title: 'Restoration progress', status: 'Insufficient evidence', limitation: 'weak_statistical_power' }),
    dim({ id: 'comparative_performance', title: 'Comparative performance', status: 'Insufficient evidence', limitation: 'missing_data', evidence_needed: 'Donor vegetation series.' }),
    dim({ id: 'evidence_quality', title: 'Evidence quality', status: 'Low', status_kind: 'quality_rating' }),
    dim({ id: 'intervention_attribution', title: 'Intervention attribution', status: 'Inconclusive', status_kind: 'attribution_verdict', limitation: 'missing_data' }),
  ],
  recommendations: [
    { id: 'review_boundary_or_period', text: 'Review the boundary or monitoring period.', rationale: 'AOI coverage is partial.', priority: 3, personas: ['auditor'], evidence_refs: ['obs.ndvi.2021'], diagnostic_refs: null },
    { id: 'acquire_more_observations', text: 'Acquire more annual observations.', rationale: 'Three periods are too few.', priority: 1, personas: ['ngo', 'auditor'], evidence_refs: ['dim.vegetation_trajectory'], diagnostic_refs: null },
    { id: 'acquire_reference_series', text: 'Acquire reference-area series.', rationale: 'No donor vegetation series.', priority: 2, personas: ['funder', 'ngo'], evidence_refs: ['dim.comparative_performance'], diagnostic_refs: null },
  ],
};

const point = (year: number, value: number | null, over: Partial<S['ObservationPoint']> = {}): S['ObservationPoint'] => ({
  year,
  value,
  evidence_state: 'DERIVED',
  sensor: 'Sentinel-2',
  clear_pixel_fraction: 0.8,
  n_scenes: 12,
  aoi_coverage_pct: 62.5,
  scene_ids: ['S2A_1', 'S2A_2'],
  scenes_sha256: 'abc123',
  ...over,
});

export const observations: S['ObservationsView'] = {
  data_mode: 'simulated',
  access_level: 'contribute',
  indicator: 'ndvi',
  status: 'available',
  reason: null,
  unit_id: 'kariba',
  source: 'sentinel2-l2a',
  points: [point(2020, 0.4), point(2021, null, { evidence_state: 'UNAVAILABLE' }), point(2022, Number.NaN), point(2023, 0.47, { scene_ids: null, scenes_sha256: null })],
};

const year = (y: number, over: Partial<S['ClimateYearView']> = {}): S['ClimateYearView'] => ({
  year: y,
  valid_months: 12,
  is_complete_year: true,
  annual_rainfall_mm: 700,
  rainfall_anomaly_mm: 0,
  rainfall_anomaly_z: 0,
  spi_12: 0,
  drought_classification: 'near_normal',
  mean_temp_c: 24,
  ...over,
});

export const climate: S['ClimateView'] = {
  data_mode: 'simulated',
  access_level: 'contribute',
  status: 'available',
  reason: null,
  case_id: 'kariba-redd',
  sources: [],
  missing_months: ['2023-12', '2022-07'],
  years: [year(2019, { spi_12: -1.4, drought_classification: 'moderate_drought' }), year(2021), year(2022, { valid_months: 11, is_complete_year: false, annual_rainfall_mm: null, spi_12: null }), year(2023, { spi_12: 1.2, drought_classification: 'moderately_wet' }), year(2024, { spi_12: -1.2, drought_classification: 'near_normal' })],
  bundle_sha256: null,
};

export const inventoryFull: S['EvidenceInventoryView'] = {
  data_mode: 'simulated',
  access_level: 'audit',
  status: 'available',
  reason: null,
  kinds: ['ndvi'],
  indicators: [{ indicator: 'ndvi', status: 'available', reason: null, n_records: 3, years: [2021, 2022, 2023], states: { DERIVED: 3 }, sensors: ['Sentinel-2'], source: 'sentinel2-l2a', data_origin: 'simulated' }],
  states: { DERIVED: 3 },
  climate_status: 'available',
  climate_reason: null,
  boundary_sha256: 'deadbeef',
  items: [{ indicator: 'ndvi', year: 2021, n_scenes: 4, scene_ids: ['S2A_1'], scenes_sha256: 'cafe01' }],
  documents_count: 0,
  documents_by_status: {},
  documents: [],
  missing_evidence: [],
  next_steps: [],
  observation_ingestion: null,
};

/** What a `view` caller receives: the removed fields are absent, not null. */
export const inventoryView = (() => {
  const { items: _i, boundary_sha256: _b, ...rest } = inventoryFull;
  return { ...rest, access_level: 'view' } as S['EvidenceInventoryView'];
})();

const project = (name: string, mode: 'observed' | 'simulated'): S['ProjectView'] => ({
  id: name,
  slug: name.toLowerCase(),
  name,
  country: 'ZW',
  ecosystem: 'woodland',
  intervention: 'restoration',
  treatment_start_year: 2020,
  data_mode: mode,
  owner_slug: 'ref',
  owner_name: 'Reference Org',
  access_level: 'view',
  boundary_sha256: null,
  reported_funding_amount: 5,
  reported_funding_currency: 'USD',
  created_at: '2026-01-01T00:00:00Z',
});

const row = (name: string, mode: 'observed' | 'simulated', over: Partial<S['PortfolioRow']> = {}): S['PortfolioRow'] => ({
  project: project(name, mode),
  access_level: 'view',
  assessment_level: 2,
  level_name: 'Contextual intelligence',
  dimension_statuses: { trajectory: 'Insufficient evidence', risk: 'No clear change', evidence_quality: 'Low' },
  top_recommendation: karibaAssessment.recommendations[1],
  attribution_verdict: 'Inconclusive',
  evidence_confidence: 'Low',
  data_mode: mode,
  reported_funding: null,
  degraded: false,
  degraded_reason: null,
  ...over,
});

export const portfolio: S['PortfolioView'] = {
  projects: [
    row('Alpha', 'observed', { reported_funding: { amount: 1000, currency: 'USD', reported_by: 'Alpha Trust' } }),
    row('Beta', 'observed'),
    row('Broken', 'observed', { assessment_level: 0, level_name: 'Not assessable', degraded: true, degraded_reason: 'assessment failed', attribution_verdict: null, evidence_confidence: null, top_recommendation: null }),
  ],
  simulated: [row('Kariba', 'simulated', { reported_funding: { amount: 9, currency: 'USD', reported_by: '' } })],
};

export const activity: S['ActivityItem'][] = [
  { id: 'a1', occurred_at: '2026-11-01T10:00:00Z', action: 'run.completed', outcome: 'success', project_id: 'p1', project_slug: 'kariba', project_name: 'Kariba', own: true },
  { id: 'a2', occurred_at: '2026-11-02T10:00:00Z', action: 'export.created', outcome: 'success', project_id: null, project_slug: null, project_name: null, own: false },
];
