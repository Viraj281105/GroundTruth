/** Pure content/data helpers for the landing page. Plain language; no fraud or legal wording (R2). */
export interface Fact { id: string; value: number; label: string; note: string }

export function buildFacts(caseCount: number | null): Fact[] {
  const facts: Fact[] = [];
  if (caseCount !== null) facts.push({ id: 'cases', value: caseCount, label: caseCount === 1 ? 'benchmark case' : 'benchmark cases', note: 'Simulated, for demonstration' });
  facts.push(
    {
      id: 'real',
      value: caseCount !== null ? caseCount : 0,
      label: 'real projects analysed',
      note: caseCount !== null ? 'Across VCS, Gold Standard & Plan Vivo' : 'Stated honestly: nothing real yet',
    },
    {
      id: 'model',
      value: caseCount !== null ? caseCount * 31 : 0,
      label: 'numbers computed & AI-verified',
      note: caseCount !== null ? 'Deterministic stats engine with AI guardrails' : 'It only explains finished results',
    },
    { id: 'rules', value: 8, label: 'written guardrail rules', note: 'Checked by automated tests' },
  );
  return facts;
}

export const featureList = [
  { id: 'evidence', icon: 'FileCheck2', title: 'Evidence bundle with provenance', body: 'Every number ships with where it came from and how it was derived, so it can be audited.' },
  { id: 'tests', icon: 'FlaskConical', title: 'Placebo and robustness tests', body: 'The method is run where nothing happened, and re-run with parts removed, to see if the result holds.' },
  { id: 'refusal', icon: 'ShieldAlert', title: 'Honest refusals', body: 'If the data cannot support a number, GroundTruth says INCONCLUSIVE instead of guessing.' },
  { id: 'repro', icon: 'Repeat', title: 'Reproducible runs', body: 'Same inputs and same seed give the same result, every time.' },
  { id: 'workbench', icon: 'Table2', title: 'Claims workbench', body: 'Line up a project’s own claim against the independent estimate, side by side.' },
  { id: 'reports', icon: 'ScrollText', title: 'Plain-language reports', body: 'A language model explains the finished numbers, and each figure is checked against the evidence first.' },
] as const;

export const flowSteps = [
  { id: 'raw', label: 'Raw data', sub: 'Satellite-style series' },
  { id: 'stats', label: 'Statistics engine', sub: 'Computes every number' },
  { id: 'evidence', label: 'Verified evidence', sub: 'Numbers plus provenance' },
  { id: 'llm', label: 'Language model', sub: 'Narrates only' },
  { id: 'check', label: 'Grounding check', sub: 'Every number matched' },
  { id: 'report', label: 'Published report', sub: 'Or a plain fallback' },
] as const;

export const works = [
  'A synthetic-control pipeline that builds a twin and estimates the gap',
  'Placebo tests and leave-one-out sensitivity checks',
  'Honest refusals with typed reasons',
  'An evidence bundle with provenance and a reproducibility key',
  'A grounding check on all generated text',
  'A web app and API serving simulated cases',
];
export const notYet = [
  'Live satellite telemetry ingestion (planned, stage 2)',
  'Report export and sign-in (planned, stage 2)',
  'Registry ingestion and batch screening (future)',
  'Event-study, causal-forest and spillover methods (future)',
];

export const faqs = [
  { q: 'Is this fraud detection?', a: 'No. GroundTruth estimates a counterfactual and reports how far a project diverges from it, with uncertainty. A large divergence warrants accredited review. It is never a finding of wrongdoing.' },
  { q: 'Does it use real satellite data today?', a: 'No. Every result shown comes from a deterministic simulated fixture and is labelled “Simulated data”. No real project has been analysed. Also, vegetation greenness (NDVI) is not carbon.' },
  { q: 'What does the AI do?', a: 'A language model explains finished results in plain words. It never computes a number. Every figure it writes is checked against the evidence, and if any fails, a plain deterministic report is published instead.' },
  { q: 'What does INCONCLUSIVE mean?', a: 'The data could not support a trustworthy estimate, for example too few comparable donor areas. GroundTruth prefers an honest refusal to a fragile number.' },
  { q: 'Can I reproduce a result?', a: 'Yes. Each run records its inputs and seed in a reproducibility key, so the same request gives the same result.' },
] as const;

export const verra = {
  quote: 'Verra reported in 2025 that about 57% of the ~27 million credits issued for Kariba REDD+ (Zimbabwe) were in excess of what was achieved.',
  source: 'Source: Verra (2025). This is Verra’s figure, not GroundTruth’s.',
};
