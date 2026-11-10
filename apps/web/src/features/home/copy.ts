/** English UI copy for the home page. No fraud, legal or certainty wording (R2). */
export const homeCopy = {
  headline: 'Verify what changed, not just what was claimed.',
  promise:
    'GroundTruth is an independent check on carbon-credit and forest-restoration claims. It compares a project with a synthetic twin built from similar untouched land and shows how far the two paths diverge. The chart and cases shown on this page are simulated.',
  primary: 'Open your workspace',
  secondary: 'How it works',
  illustrative: 'Illustrative simulation',
  heroAlt:
    'Animated line chart: a project path and its synthetic twin move together, then separate after the intervention year.',
  legendObserved: 'Project path',
  legendTwin: 'Synthetic twin',
  legendIntervention: 'Intervention',
  howTitle: 'How it works',
  steps: [
    { term: 'donor-pool', title: 'Build a twin from similar untouched land', body: 'Pick comparable areas the project never touched and blend them into a synthetic twin.' },
    { term: 'counterfactual', title: 'Compare the project to its twin', body: 'Before the project the two paths should match. Afterwards, the gap is the estimated difference.' },
    { term: 'placebo', title: 'Stress-test the result', body: 'Run the same method on places where nothing happened. A real signal should stand out from that noise.' },
  ],
  stripKicker: 'Featured case · simulated',
  stripEffect: 'Estimated effect',
  stripDonors: 'Donors admitted',
  stripP: 'Placebo p-value',
  stripOpen: 'Open this case',
  stripNote: 'Observed series from a simulated fixture, not from a real project.',
  featuredTitle: 'Featured cases',
  allCases: 'All cases',
  featuredError: 'Cases could not be loaded, so none are featured.',
  status:
    'Honest status: the benchmark cases on this site run on a simulated fixture and are labelled as such; no real project has been analysed causally. Sign-in, organisation workspaces, boundary upload, dossier export and claim-text screening exist today. A project you create can request real Sentinel-2 observations for its boundary: those values are measured but not field-validated, and no attribution to the project is available for them yet.',
} as const;
