/** Scientific integrity notices for data mode, biomass calibration, and uncertainty reporting. */
export const SCIENTIFIC_INTEGRITY_NOTICES = {
  dataModeNotice:
    'All bundled demonstrations run on deterministic SYNTHETIC fixtures. Real satellite ingestion is not enabled unless live Earth Observation credentials and pipelines are active.',
  calibrationNotice:
    'NOT CALIBRATED: NDVI is a spectral reflectance ratio, not a carbon stock. Carbon conversion is refused unless a sourced, site-calibrated biomass model is supplied.',
  uncertaintyNotice:
    'Sensitivity envelopes report the range across specifications or leave-one-out refits (not a 95% confidence interval). Calibrated biomass error propagation reports a one-sigma (~68%) interval under assumed model error.',
} as const;

/** English copy for the status page. Honest status: implemented or not, nothing in between. */
export const STATUS_COPY = {
  title: 'System status',
  intro: 'What the running engine reports about itself. Nothing here is inferred or rounded up.',
  unreachableTitle: 'The backend could not be reached',
  unreachableBody: 'No status is shown rather than a guess. Check that the API is running, then reload.',
  versions: 'Versions',
  package: 'Package',
  engine: 'Engine',
  contract: 'Contract',
  cases: 'Registered cases',
  capabilities: 'Capabilities',
  implemented: 'Implemented',
  notImplemented: 'Not implemented',
  runsTitle: 'Recent runs',
  runsNotConfiguredTitle: 'Run history is not set up',
  runsNotConfiguredBody: 'This deployment has no run store, so there is no history to chart.',
  runsUnreachableTitle: 'Run history could not be loaded',
  runsUnreachableBody: 'The runs endpoint did not answer. Nothing is charted rather than guessing.',
  runsNoneTitle: 'No runs recorded yet',
  runsNoneBody: 'Once an analysis is run it will appear here.',
  runsSimulated: 'Includes simulated runs',
  runsPerDay: 'Runs per day (UTC, latest 14 days with runs)',
  runsPerDayLabel: (days: number, total: number) => `Bar chart of ${total} stored runs across ${days} days`,
  runsByState: 'Runs by outcome',
  runsRecent: 'Latest runs',
  simulatedTitle: 'Simulated data',
  simulatedBody: 'Analyses run today use simulated data and are labelled as such wherever they appear. Requests for observed data are refused with a clear message rather than served from simulated numbers.',
  guardrailsTitle: 'Standing guardrails',
  guardrails: [
    'A vegetation index is not carbon: converting it to tonnes needs site-specific allometry and a propagated error budget.',
    'An observed change is not a causal effect: each estimate depends on its donor pool and assumptions.',
    'A divergence warrants accredited review. It is not a finding about intent or conduct.',
  ],
  capabilityLabels: {
    synthetic_control: 'Synthetic control estimate',
    placebo_inference: 'Placebo inference',
    in_space_placebo: 'In-space placebo test',
    in_time_placebo: 'In-time placebo test',
    leave_one_out: 'Leave-one-donor-out check',
    specification_curve: 'Specification curve',
    biomass_carbon_conversion: 'Biomass to carbon conversion',
    cross_sensor_calibration: 'Cross-sensor calibration',
    earth_observation: 'Earth-observation data retrieval',
    genai_narration: 'AI-written report narration',
  } as Record<string, string>,
  capabilityDescriptions: {
    synthetic_control: 'Constrained convex combination of untreated donor units tracking pre-intervention series.',
    placebo_inference: 'Finite-sample permutation inference across untreated donor units with floor 1 / (N + 1).',
    in_space_placebo: 'Reassigns the intervention to each eligible untreated donor unit in turn.',
    in_time_placebo: 'Backdates the intervention within the pre-intervention window.',
    leave_one_out: 'Re-estimates the synthetic control while omitting one active donor at a time.',
    specification_curve: 'Evaluates sensitivity across alternative donor pools and covariate specifications.',
    biomass_carbon_conversion:
      'Requires a sourced, site-calibrated biomass model (NOT CALIBRATED by default because NDVI is a spectral reflectance ratio, not carbon).',
    cross_sensor_calibration: 'Harmonizes spectral measurements across satellite sensors before comparison.',
    earth_observation: 'Retrieves satellite series when live Earth Observation credentials and pipelines are active.',
    genai_narration: 'Summarizes verified evidence bundle numbers without computing or altering estimates.',
  } as Record<string, string>,
  scientificIntegrityNotices: SCIENTIFIC_INTEGRITY_NOTICES,
} as const;
