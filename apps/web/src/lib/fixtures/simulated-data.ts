import { CaseDetail, CaseSummary, VerificationResponse } from '../types';

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

export const MOCK_VERIFICATION_RESULTS: Record<string, VerificationFixtureData> = {
  'kariba-redd': {
    verification: {
      case_id: 'kariba-redd',
      data_mode: 'simulated',
      verdict_label: 'inconclusive',
      verdict_rationale: 'A robust incremental effect on the observed indicator was estimated, but the developer\'s claim is not expressed in commensurable units, so no comparison against the claim can be made without a biomass conversion step.',
      caveats: [
        'THIS RUN USED SIMULATED DATA. The figures below describe a synthetic test fixture and say nothing about any real project.',
        'Observed change is not causal effect without identifying assumptions.',
        'A divergence between an independent estimate and a developer claim is a reason to review the project\'s baseline, not evidence of fraud.',
        'NDVI is a spectral index, not carbon; converting to carbon requires site-specific allometry.',
      ],
      warnings: [
        'SIMULATED DATA: this bundle was produced from the synthetic fixture provider and must not be published as a finding about a real project.',
        'There are more donors than pre-treatment periods, so the individual donor weights are not uniquely identified. The counterfactual path and the effect estimate are still well determined, but the listed contributing regions are one of several equally good weightings, and should be read as an illustration of the comparison set rather than as the only one consistent with the data.',
      ],
      bundle: {
        case_id: 'kariba-redd',
        schema_version: '0.2.0',
        verdict: {
          label: 'inconclusive',
          rationale: 'A robust incremental effect on the observed indicator was estimated, but the developer\'s claim is not expressed in commensurable units, so no comparison against the claim can be made without a biomass conversion step.',
          divergence_ratio: null,
          caveats: [
            'THIS RUN USED SIMULATED DATA. The figures below describe a synthetic test fixture and say nothing about any real project.',
            'Observed change is not causal effect without identifying assumptions.',
            'A divergence between an independent estimate and a developer claim is a reason to review the project\'s baseline, not evidence of fraud.',
            'NDVI is a spectral index, not carbon; converting to carbon requires site-specific allometry.',
          ],
          supporting_evidence_ids: [
            'effect.point_estimate',
            'fit.pre_rmspe',
            'placebo.p_value',
            'robustness.sign_stable',
          ],
        },
        warnings: [
          'SIMULATED DATA: this bundle was produced from the synthetic fixture provider and must not be published as a finding about a real project.',
        ],
        items: [
          {
            id: 'claim.case_id',
            label: 'Case identifier',
            value: 'kariba-redd',
            unit: '',
            confidence: null,
            provenance: {
              source: 'cases/kariba-redd.yaml',
              method: 'file-load',
              stage: 'ingestion',
              source_uri: 'https://registry.verra.org/app/projectDetail/VCS/902',
              retrieved_at: '2026-03-01T00:00:00Z',
              code_version: '0.2.0',
              parameters: {},
              inputs: [],
              notes: 'Benchmarked validation case',
            },
            qualifiers: {},
          },
          {
            id: 'effect.point_estimate',
            label: 'Estimated incremental effect on ndvi (mean post-treatment gap)',
            value: 0.042,
            unit: 'ndvi',
            confidence: {
              lower: -0.012,
              upper: 0.084,
              level: 0.95,
              kind: 'sensitivity-envelope',
            },
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'synthetic-control/simplex-constrained-least-squares',
              stage: 'causal',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: {
                n_pre_periods: 10,
                n_post_periods: 12,
                n_donors: 24,
                converged: true,
                iterations: 142,
              },
              inputs: ['matching.n_donors_admitted'],
              notes: 'Effect is on the observed indicator only. It is not a carbon quantity and has not been converted to one.',
            },
            qualifiers: {
              observed_not_causal_without_assumptions: true,
              is_carbon_quantity: false,
              indicator: 'ndvi',
            },
          },
          {
            id: 'effect.cumulative',
            label: 'Cumulative post-treatment gap in ndvi',
            value: 0.504,
            unit: 'ndvi',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'synthetic-control/simplex-constrained-least-squares',
              stage: 'causal',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: { n_post_periods: 12 },
              inputs: ['effect.point_estimate'],
              notes: null,
            },
            qualifiers: {},
          },
          {
            id: 'fit.pre_rmspe',
            label: 'Pre-treatment root mean squared prediction error',
            value: 0.0082,
            unit: 'ndvi',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'synthetic-control/simplex-constrained-least-squares',
              stage: 'causal',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: { n_pre_periods: 10 },
              inputs: [],
              notes: 'Pre-period fit quality diagnostic',
            },
            qualifiers: {},
          },
          {
            id: 'fit.rmspe_ratio',
            label: 'Post/pre RMSPE ratio',
            value: 4.12,
            unit: '',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'synthetic-control/simplex-constrained-least-squares',
              stage: 'causal',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: {},
              inputs: ['fit.pre_rmspe'],
              notes: 'Test statistic for permutation placebo suite',
            },
            qualifiers: {},
          },
          {
            id: 'matching.worst_covariate_smd',
            label: 'Worst post-match standardised mean difference across covariates',
            value: 0.182,
            unit: '',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'standardised-covariate-distance',
              stage: 'matching',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: {
                covariates: ['rainfall_mm', 'elevation_m', 'slope_deg', 'road_distance_km', 'population_density'],
              },
              inputs: [],
              notes: 'Target SMD <= 0.25',
            },
            qualifiers: {
              guideline_threshold: 0.25,
              balanced: true,
            },
          },
          {
            id: 'placebo.p_value',
            label: 'Permutation p-value from in-space placebo tests',
            value: 0.042,
            unit: '',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'in-space-placebo-permutation',
              stage: 'uncertainty',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: { n_placebos: 24, statistic: 'post_pre_rmspe_ratio' },
              inputs: ['fit.rmspe_ratio'],
              notes: 'Share of untreated comparison regions producing a divergence at least as large.',
            },
            qualifiers: {
              interpretation: 'Share of untreated comparison regions producing a divergence at least as large. Not a probability of misreporting.',
              rank: 2,
            },
          },
          {
            id: 'robustness.sign_stable',
            label: 'Estimate keeps its sign across all leave-one-out refits',
            value: true,
            unit: '',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'leave-one-donor-out-refit',
              stage: 'uncertainty',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: { n_refits: 24 },
              inputs: ['effect.point_estimate'],
              notes: 'Sign stability gate',
            },
            qualifiers: {},
          },
          {
            id: 'crosscheck.did_estimate',
            label: 'Difference-in-differences cross-check estimate',
            value: 0.039,
            unit: 'ndvi',
            confidence: null,
            provenance: {
              source: 'synthetic-fixture-provider',
              method: 'difference-in-differences',
              stage: 'causal',
              source_uri: null,
              retrieved_at: '2026-03-01T12:00:00Z',
              code_version: '0.2.0',
              parameters: { n_control_units: 24 },
              inputs: [],
              notes: 'Cross-check estimator; valid only under parallel trends.',
            },
            qualifiers: { parallel_trends_plausible: true },
          },
        ],
      },
      report_markdown: `# GroundTruth Verification Screening Report\n\n**Case:** Kariba REDD+ Project (VCS 902)\n**Status:** Inconclusive (Incommensurable Units)\n\n## Summary\n\nAn independent causal analysis of the Kariba REDD+ project was performed using simplex-constrained synthetic control over annual NDVI composites from 2001 to 2022.\n\n### Key Findings\n- **Estimated incremental effect:** +0.0420 ndvi (95% sensitivity envelope [-0.0120, +0.0840] ndvi).\n- **Permutation significance:** p = 0.042 (rank 2 of 25 units in the in-space placebo distribution).\n- **Donor pool balance:** Worst standardised mean difference across 5 terrain and climate covariates is 0.182, within the 0.25 balance guideline.\n- **Robustness:** Sign stability confirmed across all leave-one-out donor refits.\n\n### Why Inconclusive?\nThe estimated effect is expressed in NDVI (spectral reflectance ratio), whereas the project claim is registered in tCO2e (mass). Converting between these quantities requires site-specific allometric equations with known error propagation, which has not yet been implemented. No comparison against the claim can be made without this biomass model.\n\n> *Caveat:* Divergence between an independent estimate and a developer claim warrants accredited field review and is never a finding of fraud.`,
      report_generator: 'deterministic-renderer',
    },
    chartSeries: [
      { year: 2001, observed: 0.542, synthetic: 0.539, gap: 0.003, isPost: false },
      { year: 2002, observed: 0.521, synthetic: 0.524, gap: -0.003, isPost: false },
      { year: 2003, observed: 0.555, synthetic: 0.551, gap: 0.004, isPost: false },
      { year: 2004, observed: 0.538, synthetic: 0.540, gap: -0.002, isPost: false },
      { year: 2005, observed: 0.512, synthetic: 0.518, gap: -0.006, isPost: false },
      { year: 2006, observed: 0.564, synthetic: 0.560, gap: 0.004, isPost: false },
      { year: 2007, observed: 0.548, synthetic: 0.545, gap: 0.003, isPost: false },
      { year: 2008, observed: 0.531, synthetic: 0.535, gap: -0.004, isPost: false },
      { year: 2009, observed: 0.558, synthetic: 0.553, gap: 0.005, isPost: false },
      { year: 2010, observed: 0.544, synthetic: 0.546, gap: -0.002, isPost: false },
      // Post-treatment begins 2011
      { year: 2011, observed: 0.562, synthetic: 0.538, gap: 0.024, ciLower: 0.008, ciUpper: 0.040, isPost: true },
      { year: 2012, observed: 0.575, synthetic: 0.532, gap: 0.043, ciLower: 0.015, ciUpper: 0.065, isPost: true },
      { year: 2013, observed: 0.581, synthetic: 0.529, gap: 0.052, ciLower: 0.020, ciUpper: 0.080, isPost: true },
      { year: 2014, observed: 0.568, synthetic: 0.524, gap: 0.044, ciLower: 0.014, ciUpper: 0.072, isPost: true },
      { year: 2015, observed: 0.554, synthetic: 0.518, gap: 0.036, ciLower: 0.006, ciUpper: 0.062, isPost: true },
      { year: 2016, observed: 0.570, synthetic: 0.522, gap: 0.048, ciLower: 0.018, ciUpper: 0.076, isPost: true },
      { year: 2017, observed: 0.585, synthetic: 0.535, gap: 0.050, ciLower: 0.022, ciUpper: 0.082, isPost: true },
      { year: 2018, observed: 0.578, synthetic: 0.530, gap: 0.048, ciLower: 0.016, ciUpper: 0.078, isPost: true },
      { year: 2019, observed: 0.565, synthetic: 0.526, gap: 0.039, ciLower: 0.008, ciUpper: 0.068, isPost: true },
      { year: 2020, observed: 0.572, synthetic: 0.531, gap: 0.041, ciLower: 0.010, ciUpper: 0.070, isPost: true },
      { year: 2021, observed: 0.580, synthetic: 0.538, gap: 0.042, ciLower: 0.012, ciUpper: 0.074, isPost: true },
      { year: 2022, observed: 0.574, synthetic: 0.537, gap: 0.037, ciLower: 0.005, ciUpper: 0.068, isPost: true },
    ],
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
    placebos: {
      projectStatistic: 4.12,
      pValue: 0.042,
      rank: 2,
      totalUnits: 25,
      bins: [
        { min: 0.5, max: 1.0, count: 4 },
        { min: 1.0, max: 1.5, count: 8 },
        { min: 1.5, max: 2.0, count: 6 },
        { min: 2.0, max: 2.5, count: 3 },
        { min: 2.5, max: 3.0, count: 2 },
        { min: 3.0, max: 3.5, count: 1 },
        { min: 3.5, max: 4.0, count: 0 },
        { min: 4.0, max: 4.5, count: 1 }, // Kariba project is here
      ],
    },
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
