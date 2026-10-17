import { CaseDetail, CaseSummary, Evidence, VerificationResponse } from '../types';
import { GeneratedCompletedFixture, KARIBA_COMPLETED } from './generated';

/**
 * SIMULATED FIXTURE DATA
 * 
 * IMPORTANT: These fixtures are strictly for frontend UI development and offline demos.
 * All fixtures are explicitly flagged with `data_mode: "simulated"` and carry persistent warnings.
 * No analysis of a real project has been run yet.
 */

export const MOCK_CASES_SUMMARY: CaseSummary[] = [
  {
    case_id: 'kariba-redd',
    name: 'Kariba REDD+ Project',
    country: 'Zimbabwe',
    standard: 'VCS',
    registry_id: 'VCS 902',
    ecosystem: 'miombo woodland / dry forest',
    indicator: 'ndvi',
    pre_period: '2001-2010',
    post_period: '2011-2022',
    status: 'scaffolded',
    has_known_reference: true,
  },
  {
    case_id: 'mikoko-pamoja',
    name: 'Mikoko Pamoja',
    country: 'Kenya',
    standard: 'PlanVivo',
    registry_id: 'PlanVivo 1000',
    ecosystem: 'mangrove (blue carbon)',
    indicator: 'ndvi',
    pre_period: '2003-2012',
    post_period: '2013-2022',
    status: 'scaffolded',
    has_known_reference: true,
  },
  {
    case_id: 'southern-cardamom-redd',
    name: 'Southern Cardamom REDD+ Project',
    country: 'Cambodia',
    standard: 'VCS',
    registry_id: 'VCS 1748',
    ecosystem: 'lowland & montane evergreen forest',
    indicator: 'evi',
    pre_period: '2005-2014',
    post_period: '2015-2022',
    status: 'scaffolded',
    has_known_reference: true,
  },
];

export const MOCK_CASE_DETAILS: Record<string, CaseDetail> = {
  'kariba-redd': {
    case_id: 'kariba-redd',
    name: 'Kariba REDD+ Project',
    country: 'Zimbabwe',
    standard: 'VCS',
    registry_id: 'VCS 902',
    ecosystem: 'miombo woodland / dry forest',
    indicator: 'ndvi',
    pre_period: '2001-2010',
    post_period: '2011-2022',
    status: 'scaffolded',
    has_known_reference: true,
    area_ha: 785000,
    donor_search_region: 'Zimbabwe, Zambia and Mozambique miombo woodland outside any registered REDD+ or protected-area boundary',
    donor_pool_size: 80,
    covariates: [
      'rainfall_mm',
      'elevation_m',
      'slope_deg',
      'road_distance_km',
      'population_density',
    ],
    known_reference: {
      description: 'An investigation by Verra into the Kariba REDD+ project concluded in 2025 that a majority of credits issued by the project were in excess of the emission reductions actually achieved.',
      reported_excess_share: 0.57,
      reported_credits_issued_approx: 27000000,
      source: 'Verra investigation findings, as reported by Carbon Herald and Climate Home News',
      source_date: '2025-09',
      source_uri: 'https://registry.verra.org/app/projectDetail/VCS/902',
      caveat: 'This figure belongs to Verra, not to GroundTruth. It is recorded here as a validation target. Reproducing it is not guaranteed, and a mismatch would be a finding about our method, not about the project.',
    },
    notes: 'Miombo woodland has strong rainfall-driven interannual NDVI variability, so rainfall matching is load-bearing for this case and a rainfall-only placebo specification must be reported alongside the main estimate.',
  },
  'mikoko-pamoja': {
    case_id: 'mikoko-pamoja',
    name: 'Mikoko Pamoja',
    country: 'Kenya',
    standard: 'PlanVivo',
    registry_id: 'PlanVivo 1000',
    ecosystem: 'mangrove (blue carbon)',
    indicator: 'ndvi',
    pre_period: '2003-2012',
    post_period: '2013-2022',
    status: 'scaffolded',
    has_known_reference: true,
    area_ha: 117,
    donor_search_region: 'Kenyan and Tanzanian coastal mangrove stands outside any registered carbon project',
    donor_pool_size: 40,
    covariates: [
      'rainfall_mm',
      'elevation_m',
      'slope_deg',
      'road_distance_km',
      'population_density',
    ],
    known_reference: {
      description: 'Mikoko Pamoja is a small, community-run mangrove project generally regarded as methodologically careful. It is used here as a control on the method, not as a project under suspicion.',
      source: 'Plan Vivo registry and published project documentation',
      caveat: 'The expected outcome for this case is INCONCLUSIVE on grounds of scale (~117 ha). That is a statement about the resolution of the method, not about the project.',
    },
    notes: 'Mangrove NDVI depends on tidal state at acquisition. Composites must be restricted to a consistent tidal window before this case can be run at all.',
  },
  'southern-cardamom-redd': {
    case_id: 'southern-cardamom-redd',
    name: 'Southern Cardamom REDD+ Project',
    country: 'Cambodia',
    standard: 'VCS',
    registry_id: 'VCS 1748',
    ecosystem: 'lowland & montane evergreen forest',
    indicator: 'evi',
    pre_period: '2005-2014',
    post_period: '2015-2022',
    status: 'scaffolded',
    has_known_reference: true,
    area_ha: 497000,
    donor_search_region: 'Cambodian and adjacent Thai lowland evergreen forest outside registered concessions, protected areas and REDD+ project boundaries',
    donor_pool_size: 60,
    covariates: [
      'rainfall_mm',
      'elevation_m',
      'slope_deg',
      'road_distance_km',
      'population_density',
    ],
    known_reference: {
      description: 'The project has been the subject of published journalistic and academic scrutiny regarding its baseline and its social safeguards. No registry correction comparable to the Kariba case has been issued.',
      source: 'public reporting; no official credit correction on record as of this case definition',
      caveat: 'Unlike Kariba there is no official corrected figure to benchmark against, so this case tests method behaviour and cloud robustness, not accuracy against a known answer.',
    },
    notes: 'Persistent cloud cover means annual composites here will have low clear-scene counts in several years.',
  },
};

export interface ChartDataPoint {
  year: number;
  observed: number;
  synthetic: number;
  gap: number;
  ciLower?: number;
  ciUpper?: number;
  isPost: boolean;
}

export interface DonorMapUnit {
  id: string;
  name: string;
  lat: number;
  lng: number;
  status: 'project' | 'admitted' | 'excluded';
  weight?: number;
  smd?: number;
  exclusionReason?: string;
  distanceKm: number;
}

export interface PlaceboDistributionData {
  bins: { min: number; max: number; count: number }[];
  projectStatistic: number;
  pValue: number;
  rank: number;
  totalUnits: number;
  /** From the `placebo.p_value` qualifiers; absent on bundles that predate them. */
  significanceLevel?: number;
  pValueFloor?: number;
}

export interface VerificationFixtureData {
  verification: VerificationResponse;
  chartSeries: ChartDataPoint[];
  donors: DonorMapUnit[];
  placebos: PlaceboDistributionData;
  timeline: {
    year: number;
    title: string;
    description: string;
    type: 'baseline' | 'crediting' | 'sensor' | 'disturbance';
  }[];
}

/**
 * The engine's counterfactual path as chart points. No per-period interval is
 * emitted by the engine, so none is drawn: `ciLower`/`ciUpper` stay undefined
 * rather than being invented.
 */
export function chartSeriesFrom(fixture: GeneratedCompletedFixture): ChartDataPoint[] {
  const { periods, observed, synthetic, treatment_boundary_period } =
    fixture.not_served_by_api.counterfactual_path;
  return periods.map((year, i) => ({
    year,
    observed: observed[i],
    synthetic: synthetic[i],
    gap: observed[i] - synthetic[i],
    isPost: year >= treatment_boundary_period,
  }));
}

function numberOrUndefined(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

function evidenceById(fixture: GeneratedCompletedFixture, id: string): Evidence {
  const item = fixture.verification.bundle.items.find((e) => e.id === id);
  if (!item) {
    throw new Error(`Generated fixture has no ${id} evidence item.`);
  }
  return item;
}

/**
 * Bin the engine's placebo statistics for the histogram. The p-value, rank and
 * unit count are read from the evidence bundle, never recomputed here.
 */
export function placeboDistributionFrom(
  fixture: GeneratedCompletedFixture,
  binWidth = 1,
): PlaceboDistributionData {
  const { observed_statistic, placebo_statistics } =
    fixture.not_served_by_api.placebo_distribution;
  const pValue = evidenceById(fixture, 'placebo.p_value');
  const nUnits = evidenceById(fixture, 'placebo.n_units');
  const upper = Math.ceil(Math.max(observed_statistic, ...placebo_statistics) / binWidth) + 1;
  const bins = Array.from({ length: upper }, (_, i) => ({
    min: i * binWidth,
    max: (i + 1) * binWidth,
    count: 0,
  }));
  for (const stat of placebo_statistics) {
    bins[Math.min(Math.floor(stat / binWidth), bins.length - 1)].count += 1;
  }
  return {
    bins,
    projectStatistic: observed_statistic,
    pValue: Number(pValue.value),
    rank: Number(pValue.qualifiers.rank),
    // The project plus every placebo unit in the permutation distribution.
    totalUnits: Number(nUnits.value) + 1,
    significanceLevel: numberOrUndefined(pValue.qualifiers.significance_level),
    pValueFloor: numberOrUndefined(pValue.qualifiers.p_value_floor),
  };
}

export const MOCK_VERIFICATION_RESULTS: Record<string, VerificationFixtureData> = {
  'kariba-redd': {
    // Engine-generated: see ./generated.ts and apps/web/scripts/generate_fixtures.py.
    verification: KARIBA_COMPLETED.verification,
    chartSeries: chartSeriesFrom(KARIBA_COMPLETED),
    placebos: placeboDistributionFrom(KARIBA_COMPLETED),
    // Hand-drawn layout for the map view only. The synthetic provider has no
    // geography, so these coordinates and names illustrate the map component
    // and are not engine output.
    donors: [
      { id: 'project-kariba', name: 'Kariba Project Area', lat: -17.5, lng: 28.2, status: 'project', distanceKm: 0 },
      { id: 'zw-matabeleland-n-d03', name: 'Matabeleland North D03', lat: -18.2, lng: 27.6, status: 'admitted', weight: 0.342, smd: 0.08, distanceKm: 85 },
      { id: 'zm-southern-d07', name: 'Zambia Southern D07', lat: -16.8, lng: 27.9, status: 'admitted', weight: 0.281, smd: 0.12, distanceKm: 110 },
      { id: 'mz-tete-d12', name: 'Mozambique Tete D12', lat: -16.1, lng: 32.4, status: 'admitted', weight: 0.194, smd: 0.18, distanceKm: 420 },
      { id: 'zw-mashonaland-w-d04', name: 'Mashonaland West D04', lat: -17.1, lng: 29.4, status: 'admitted', weight: 0.112, smd: 0.15, distanceKm: 140 },
      { id: 'zm-lusaka-d02', name: 'Zambia Lusaka D02', lat: -15.6, lng: 28.6, status: 'admitted', weight: 0.071, smd: 0.14, distanceKm: 190 },
      { id: 'zw-ex-leakage-01', name: 'Buffer Zone East', lat: -17.3, lng: 28.9, status: 'excluded', distanceKm: 8, exclusionReason: 'Within 10 km leakage belt' },
      { id: 'zw-ex-wdpa-02', name: 'Matusadona National Park', lat: -16.9, lng: 28.4, status: 'excluded', distanceKm: 35, exclusionReason: 'WDPA Protected Area overlap' },
      { id: 'zm-ex-cloud-03', name: 'Kafue Flats East', lat: -15.8, lng: 27.2, status: 'excluded', distanceKm: 210, exclusionReason: 'Cloud cover > 25% in > 3 pre-treatment years' },
      { id: 'mz-ex-caliper-04', name: 'Cahora Bassa Hills', lat: -15.5, lng: 31.8, status: 'excluded', distanceKm: 380, exclusionReason: 'Exceeds common support covariate distance caliper' },
    ],
    timeline: [
      { year: 2001, title: 'Pre-period fit begins', description: 'Baseline monitoring window starts on annual Landsat composites.', type: 'baseline' },
      { year: 2003, title: 'Landsat 7 SLC-off transition', description: 'Scan Line Corrector anomaly; masked in compositing pipeline.', type: 'sensor' },
      { year: 2008, title: 'Regional drought anomaly', description: 'Severe dry season across southern African miombo woodland.', type: 'disturbance' },
      { year: 2011, title: 'Crediting period begins (Treatment)', description: 'Kariba REDD+ activities officially start (July 1, 2011).', type: 'crediting' },
      { year: 2013, title: 'Landsat 8 OLI enters service', description: 'Cross-calibrated with Landsat 7 in pre-treatment baseline.', type: 'sensor' },
      { year: 2015, title: 'Sentinel-2 MSI enters service', description: '10m / 20m high-resolution multispectral imagery becomes available.', type: 'sensor' },
      { year: 2022, title: 'Analysis evaluation window ends', description: 'Current end of annual evaluation time series.', type: 'baseline' },
    ],
  },
};
