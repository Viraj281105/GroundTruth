export interface CitationInput {
  caseName: string;
  standard: string;
  registryId: string | null;
  runId: string;
  specHash: string;
  dataMode: string;
  generator: string | null;
}

/**
 * A plain-text citation for a screening report. It names the run and the
 * specification so the result can be reproduced, and states what kind of
 * result it is. It contains no estimate and no judgement about the project.
 */
export function formatCitation(i: CitationInput): string {
  const registry = i.registryId ? `, ${i.registryId}` : '';
  const kind = i.dataMode === 'simulated' ? 'Simulated data, not an observed result.' : 'Observed data.';
  const gen = i.generator ? ` Narrative generator: ${i.generator}.` : '';
  return `GroundTruth screening report: ${i.caseName} (${i.standard}${registry}). Run ${i.runId}, specification ${i.specHash}. ${kind}${gen} Independent screening estimate; not an audit or verification of the project.`;
}

/** Print rules: hide the site chrome and the case tabs, keep the report. */
export const PRINT_CSS = `@media print {
  header, footer, nav, [data-print="hide"] { display: none !important; }
  body { background: #fff !important; color: #000 !important; }
  .gt-container { max-width: none !important; padding: 0 !important; }
}`;
