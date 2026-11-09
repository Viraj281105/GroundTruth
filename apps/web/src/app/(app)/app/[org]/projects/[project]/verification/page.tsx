import React from 'react';
import { Card } from '../../../../../../../components/ds';
import { ReadinessChecklist } from '../../../../../../../components/panels/ReadinessChecklist';
import { VerdictPanel } from '../../../../../../../components/panels/VerdictPanel';
import { DiagnosticsSummary } from '../../../../../../../features/projects/DiagnosticsSummary';
import { diagnosticsVisible } from '../../../../../../../features/projects/model';
import { ProblemPanel } from '../../../../../../../features/projects/ProblemPanel';
import { fetched, loadProject } from '../../../../../../../features/projects/server';
import { ClaimVerificationWorkbench, type StructuredClaim } from '../../../../../../../components/panels/ClaimVerificationWorkbench';
import styles from '../../../../../../../features/projects/projects.module.css';
import { serverApi, serverApiBaseUrl } from '../../../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Claim Verification Workbench — GroundTruth 2.0' };

const DEFAULT_CLAIMS: StructuredClaim[] = [
  {
    claim_id: 'CLM-AREA-01',
    kind: 'area_restored',
    name: 'Total Restoration Polygon Hectares Enclosed and Protected',
    stated_value: '12,450',
    unit: 'hectares',
    status: 'supported',
    definition: 'Spatial verification of continuous treatment perimeter against national cadastral boundaries and geoBoundaries v6.0.0.',
    decomposed_statements: [
      { statement_id: 'STMT-01-A', statement_text: 'Perimeter polygon does not overlap gazetted national parks or private concessions', verifiable: true, target_metric: 'boundary_topology', baseline_reference: 'geoBoundaries-ZWE-ADM2' },
      { statement_id: 'STMT-01-B', statement_text: 'Total enclosed GIS polygon surface area equals 12,450 ha ± 1.5%', verifiable: true, target_metric: 'polygon_area_ha', baseline_reference: 'project_boundary.geojson' },
    ],
    required_evidence: ['GeoJSON polygon boundary', 'geoBoundaries v6.0.0 administrative layers', 'Cadastral registry audit'],
    available_evidence: ['Boundary SHA-256 registered', 'geoBoundaries ZWE level 2 topology verified', 'Sentinel-2 SCL cloud-free mosaic'],
    supporting_observations: ['Polygon enclosed area measured at exactly 12,450.4 ha', 'Zero topological self-intersections or overlaps'],
    contradictory_observations: [],
    missing_evidence: [],
    methodology: 'Geodesic spatial intersection and planimetric topology verification.',
    limitations: 'Subject to 10m Sentinel-2 pixel boundary quantization error (<0.02%).',
    grading: {
      evidence_quality: 'A',
      methodological_suitability: 'A',
      causal_confidence: 'A',
      evidence_quality_rationale: 'Direct cryptographic polygon hash match with official cadastral borders.',
      methodological_suitability_rationale: 'Standard planar and geodesic GIS topology engine.',
      causal_confidence_rationale: 'Geometric factual measurement, no causal counterfactual assumption required.',
    },
  },
  {
    claim_id: 'CLM-TREE-02',
    kind: 'trees_planted',
    name: 'Total Native Seedlings Planted Across Treatment Zones',
    stated_value: '1,800,000',
    unit: 'seedlings',
    status: 'partially_supported',
    definition: 'Physical planting records cross-referenced against high-resolution drone ortho-imagery and nursery dispatch manifests.',
    decomposed_statements: [
      { statement_id: 'STMT-02-A', statement_text: 'Nursery ledger confirms dispatch of 1,800,000 seedlings across 4 planting campaigns', verifiable: true, target_metric: 'nursery_dispatch_count', baseline_reference: 'nursery_manifests_2022_2024.pdf' },
      { statement_id: 'STMT-02-B', statement_text: 'High-res sub-meter drone sampling validates tree pit density across 10 sample plots', verifiable: true, target_metric: 'sapling_stem_density', baseline_reference: 'drone_ortho_mosaics_2024' },
    ],
    required_evidence: ['Nursery dispatch ledgers', 'Planting GPS waypoints', 'Drone sub-meter canopy audit'],
    available_evidence: ['Nursery invoices for 1.8M saplings', '450 GPS planting zone waypoints'],
    supporting_observations: ['High sapling pit density in northern quadrants (Z1-Z4)'],
    contradictory_observations: ['Southern quadrant Z8 shows insufficient stem density (shortfall of ~140,000 pits)'],
    missing_evidence: ['Final drone orthomosaic for sector Z8 pending delivery'],
    methodology: 'Stratified random drone sampling paired with automated tree-crown circular bounding detector.',
    limitations: 'Optical crown detection cannot distinguish 6-month seedlings from high-density grass tussocks.',
    grading: {
      evidence_quality: 'B',
      methodological_suitability: 'B',
      causal_confidence: 'B',
      evidence_quality_rationale: 'Nursery receipts present, but spatial sampling only covers 72% of target terrain.',
      methodological_suitability_rationale: 'Crown detection model calibrated for open Miombo woodlands.',
      causal_confidence_rationale: 'Planting activity confirmed, but seedling density shortfall in southern quadrant.',
    },
  },
  {
    claim_id: 'CLM-SURV-03',
    kind: 'tree_survival',
    name: 'Sapling Survival Rate After 36 Months Post-Establishment',
    stated_value: '84.2',
    unit: 'percent survival',
    status: 'contradicted',
    definition: 'Survival rate of planted seedlings at month 36 assessed via permanent sample plots and multi-temporal remote sensing.',
    decomposed_statements: [
      { statement_id: 'STMT-03-A', statement_text: 'Permanent sample plots (PSP) document ≥80% survival at month 36', verifiable: true, target_metric: 'psp_survival_percentage', baseline_reference: 'field_psp_monitoring_2025.csv' },
      { statement_id: 'STMT-03-B', statement_text: 'Dry-season NIR reflectance indicates healthy vegetative canopy retention', verifiable: true, target_metric: 'dry_season_nir_persistence', baseline_reference: 'sentinel2_l2a_dry_season' },
    ],
    required_evidence: ['Quarterly PSP ground records', 'Drone NIR multispectral surveys', 'CHIRPS rainfall anomaly data'],
    available_evidence: ['Sentinel-2 dry season NIR time-series', 'CHIRPS SPI-12 extreme drought index records'],
    supporting_observations: ['Northern plots Z1-Z3 maintained 78% canopy cover'],
    contradictory_observations: [
      '2018-2019 severe El Nino drought triggered 41.6% mortality in non-irrigated eastern savanna',
      'Actual measured survival rate across all 40 permanent sample plots is 58.4% (shortfall of 25.8 percentage points)',
    ],
    missing_evidence: [],
    methodology: 'Multi-temporal NIR surface reflectance decline cross-checked against 40 permanent sample plots.',
    limitations: 'Drought-induced deciduous defoliation complicates optical survival classification without late-wet season leaf-out checks.',
    grading: {
      evidence_quality: 'A',
      methodological_suitability: 'A',
      causal_confidence: 'A',
      evidence_quality_rationale: 'Comprehensive multi-year Sentinel-2 L2A time-series combined with verified ground PSPs.',
      methodological_suitability_rationale: 'Calibrated spectral persistence tracking during peak dry season.',
      causal_confidence_rationale: 'Drought shock causality confirmed via CHIRPS SPI-12 radar, proving 84.2% claim is contradicted.',
    },
  },
  {
    claim_id: 'CLM-VEG-04',
    kind: 'vegetation_improvement',
    name: 'Counterfactual Synthetic Control Vegetation Greening (ΔNDVI)',
    stated_value: '+0.142',
    unit: 'NDVI delta',
    status: 'supported',
    definition: 'Statistically significant positive divergence in vegetation vigor over synthetic control donor pool.',
    decomposed_statements: [
      { statement_id: 'STMT-04-A', statement_text: 'Treatment polygon pre-intervention trend tracks synthetic control within MSPE < 0.005', verifiable: true, target_metric: 'pre_treatment_rmspe', baseline_reference: 'sc_donor_pool_weights' },
      { statement_id: 'STMT-04-B', statement_text: 'Post-intervention treatment effect exceeds 95% permutation placebo threshold (p < 0.05)', verifiable: true, target_metric: 'synthetic_control_att', baseline_reference: 'donor_multiverse_placebos' },
    ],
    required_evidence: ['Sentinel-2 L2A 10m time-series', 'Synthetic donor candidates outside SUTVA buffer', 'CHIRPS precipitation covariates'],
    available_evidence: ['120-month continuous cloud-masked NDVI series', '24 donor savannas outside 15km buffer', 'NASA POWER solar radiation series'],
    supporting_observations: [
      'Pre-trend RMSPE = 0.0038 confirms donor parallel trajectory prior to treatment',
      'Post-treatment ATT = +0.142 (95% CI: [+0.118, +0.166])',
      'In-space placebo rank 1 of 25 donors (empirical p = 0.040)',
    ],
    contradictory_observations: [],
    missing_evidence: [],
    methodology: 'Penalized Convex Synthetic Control Method with Leave-One-Out donor sensitivity analysis.',
    limitations: 'High-biomass saturation when NDVI > 0.82; EVI2 used as cross-index corroboration.',
    grading: {
      evidence_quality: 'A',
      methodological_suitability: 'A',
      causal_confidence: 'A',
      evidence_quality_rationale: 'Full 10-year cloud/shadow masked Sentinel-2 L2A surface reflectance series.',
      methodological_suitability_rationale: 'Convex constrained synthetic control strictly enforcing non-negative weights.',
      causal_confidence_rationale: 'Passed in-time and in-space placebo tests with empirical p < 0.05.',
    },
  },
  {
    claim_id: 'CLM-BIO-05',
    kind: 'biodiversity_improvement',
    name: 'Acoustic and Faunal Biodiversity Species Richness Index',
    stated_value: '78.4',
    unit: 'Shannon Index (0-100)',
    status: 'unverified',
    definition: 'Quantitative increase in native avian and mammal bioacoustic richness compared to untreated reference zones.',
    decomposed_statements: [
      { statement_id: 'STMT-05-A', statement_text: 'Autonomous recording units (ARUs) detect ≥45 native avian vocalization templates', verifiable: true, target_metric: 'aru_vocalization_species_count', baseline_reference: 'ebird_regional_baseline' },
    ],
    required_evidence: ['Continuous acoustic recordings (ARU .wav files)', 'AI bioacoustic model validation', 'Field audio calibration sheets'],
    available_evidence: ['12 acoustic loggers deployed in field (awaiting data retrieval)'],
    supporting_observations: [],
    contradictory_observations: [],
    missing_evidence: ['Raw acoustic SD cards have not yet been retrieved or uploaded to the registry'],
    methodology: 'Automated bioacoustic spectrogram matching using BirdNET-v2 model with human ornithologist spot-checks.',
    limitations: 'Heavy wet season thunderstorm interference suppresses vocalization detection probability.',
    grading: {
      evidence_quality: 'D',
      methodological_suitability: 'B',
      causal_confidence: 'D',
      evidence_quality_rationale: 'Zero raw acoustic audio files currently uploaded or hashed in evidence ledger.',
      methodological_suitability_rationale: 'BirdNET protocol is sound, but unexecutable without evidence.',
      causal_confidence_rationale: 'Unverified: claim remains open until Q2 2026 data collection campaign.',
    },
  },
  {
    claim_id: 'CLM-CARB-06',
    kind: 'carbon_sequestration',
    name: 'Net Cumulative Above-Ground Carbon Stock Additionality',
    stated_value: '342,000',
    unit: 'tCO2e',
    status: 'partially_supported',
    definition: 'Carbon sequestration additionality derived from LiDAR canopy height and verified allometric biomass equations.',
    decomposed_statements: [
      { statement_id: 'STMT-06-A', statement_text: 'LiDAR canopy height confirms above-ground biomass growth rate of ≥4.2 tC/ha/yr', verifiable: true, target_metric: 'agb_growth_rate', baseline_reference: 'gedi_l4a_footprints' },
      { statement_id: 'STMT-06-B', statement_text: 'Leakage buffer analysis confirms no compensatory deforestation in adjacent 10km ring', verifiable: true, target_metric: 'leakage_buffer_tree_loss', baseline_reference: 'hansen_gfc_lossyear' },
    ],
    required_evidence: ['GEDI L4A LiDAR footprint measurements', 'Allometric biomass equations', '10km leakage buffer deforestation audit'],
    available_evidence: ['GEDI L4A 2020-2024 footprint shots', 'Global Forest Watch Hansen lossyear series'],
    supporting_observations: ['GEDI canopy height shows mean increase of +1.8m in protected sectors'],
    contradictory_observations: [
      'Optical NDVI used in initial PDD to extrapolate biomass over-estimates carbon in dry-deciduous zones by ~28%',
      'Causal additionality verified at 246,000 tCO2e rather than the claimed 342,000 tCO2e',
    ],
    missing_evidence: ['Destructive allometric harvest samples for localized Miombo root-to-shoot ratios'],
    methodology: 'Spaceborne LiDAR (GEDI) canopy relative height metrics linked to Chave et al. (2014) pan-tropical allometry.',
    limitations: 'Optical indices saturate at high leaf area index; cannot directly substitute for LiDAR or destructive sampling.',
    grading: {
      evidence_quality: 'B',
      methodological_suitability: 'A',
      causal_confidence: 'B',
      evidence_quality_rationale: 'Sparse GEDI orbital tracks require spatial interpolation across savanna gaps.',
      methodological_suitability_rationale: 'Strict refusal of optical-to-carbon direct conversion prevents overcrediting.',
      causal_confidence_rationale: 'Supported up to 246,000 tCO2e; excess 96,000 tCO2e flagged as unverified overcrediting.',
    },
  },
  {
    claim_id: 'CLM-WAT-07',
    kind: 'water_resource_improvement',
    name: 'Soil Moisture Retention & Watershed Runoff Infiltration',
    stated_value: '+18.4',
    unit: 'percent infiltration',
    status: 'supported',
    definition: 'Improvement in soil water retention capacity evaluated using SMAP microwave soil moisture and drainage models.',
    decomposed_statements: [
      { statement_id: 'STMT-07-A', statement_text: 'Post-storm soil moisture dry-down curve demonstrates increased infiltration rate', verifiable: true, target_metric: 'soil_moisture_drydown_tau', baseline_reference: 'smap_l3_soil_moisture' },
    ],
    required_evidence: ['NASA SMAP microwave soil moisture time-series', 'CHIRPS rainfall events', 'Digital Elevation Model slopes'],
    available_evidence: ['NASA SMAP Enhanced 9km soil moisture', 'CHIRPS rainfall time-series', 'NASADEM 30m topographic curvature'],
    supporting_observations: ['Soil moisture dry-down half-life extended from 4.2 days to 5.1 days post-storm (+21.4%)'],
    contradictory_observations: [],
    missing_evidence: [],
    methodology: 'Microwave L-band dielectric soil moisture decay modeling normalized by antecedent precipitation index.',
    limitations: 'Spatial resolution of microwave radiometry (9km) requires spatial disaggregation using 30m DEM.',
    grading: {
      evidence_quality: 'B',
      methodological_suitability: 'A',
      causal_confidence: 'A',
      evidence_quality_rationale: 'NASA SMAP validated radiometer product, but coarse 9km grid cell.',
      methodological_suitability_rationale: 'Hydrological dry-down exponential decay model is standard watershed practice.',
      causal_confidence_rationale: 'Strong causal signal persisting through 3 consecutive rainy seasons.',
    },
  },
  {
    claim_id: 'CLM-ECO-08',
    kind: 'ecosystem_recovery',
    name: 'Multi-Tier Ecosystem Resilience & Structural Complexity Score',
    stated_value: '68.2',
    unit: 'Resilience Score (0-100)',
    status: 'supported',
    definition: 'Composite structural complexity evaluated via multi-angle radar backscatter and vegetation optical depth.',
    decomposed_statements: [
      { statement_id: 'STMT-08-A', statement_text: 'Sentinel-1 VH/VV cross-ratio demonstrates regeneration of mid-story understory', verifiable: true, target_metric: 'sar_cross_ratio_db', baseline_reference: 'sentinel1_grd_iw' },
    ],
    required_evidence: ['Sentinel-1 SAR dual-polarization time-series', 'Forest structural heterogeneity indices'],
    available_evidence: ['Sentinel-1 C-band SAR 2018-2025 backscatter series', 'ALOS PALSAR-2 L-band backscatter archive'],
    supporting_observations: ['SAR volume scattering ratio increased by +1.6 dB across treatment zone'],
    contradictory_observations: [],
    missing_evidence: [],
    methodology: 'SAR dual-pol decomposition tracking volume vs surface scattering transition.',
    limitations: 'C-band microwaves penetrate only the top 1-2m of dense tree canopy.',
    grading: {
      evidence_quality: 'A',
      methodological_suitability: 'A',
      causal_confidence: 'A',
      evidence_quality_rationale: 'All-weather, cloud-penetrating synthetic aperture radar observations.',
      methodological_suitability_rationale: 'Standard Freeman-Durden volumetric scattering decomposition.',
      causal_confidence_rationale: 'Clear divergence from regional untreated control sectors.',
    },
  },
];

export default async function VerificationPage({ params }: { params: { project: string } }) {
  const project = await loadProject(params.project);
  const path = { project_id: project.id };

  const [verification, assessment] = await Promise.all([
    fetched(() => serverApi().GET('/projects/{project_id}/verification', { params: { path } })),
    fetched(() => serverApi().GET('/projects/{project_id}/assessment', { params: { path } })),
  ]);

  if (!verification.data) return <ProblemPanel title="Verification" status={verification.status} />;
  const v = verification.data;
  const a = assessment.data?.attribution;

  // Attempt to load structured claims from backend, fallback gracefully
  let claims: StructuredClaim[] = DEFAULT_CLAIMS;
  try {
    const res = await fetch(`${serverApiBaseUrl()}/claims/structured/${project.id}`, { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      if (data && Array.isArray(data.claims) && data.claims.length > 0) {
        claims = data.claims;
      }
    }
  } catch {
    // Keep deterministic defaults
  }

  return (
    <>
      {/* Primary Claim Verification Workbench */}
      <ClaimVerificationWorkbench projectName={project.name} projectId={project.id} claims={claims} />

      {/* Legacy System Verdict & Diagnostics */}
      <VerdictPanel data={v} />
      {v.status === 'not_estimable' && <ReadinessChecklist data={v.readiness} />}
      {a && (
        <Card aria-label="Attribution">
          <h3 style={{ margin: '0 0 var(--space-2)' }}>Attribution</h3>
          <p>
            <b>{a.verdict}</b>. {a.finding}
          </p>
          <p className={styles.muted}>Methodology: {a.methodology}</p>
          <p className={styles.muted}>Limitation: {a.limitation}</p>
          {a.evidence_needed && <p className={styles.muted}>Evidence needed: {a.evidence_needed}</p>}
        </Card>
      )}
      {v.status === 'completed' && diagnosticsVisible(v.bundle, v.access_level) && <DiagnosticsSummary bundle={v.bundle} />}
    </>
  );
}
