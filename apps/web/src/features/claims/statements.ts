import type { ClaimsResponse } from './client';

type Statement = ClaimsResponse['statements'][number];
export type StatementTone = 'accent' | 'neutral' | 'danger';

/** How a statement status is toned. An overclaim is flagged; "unsupported" is neutral (absence of evidence, not a finding). */
export function statementTone(status: string): StatementTone {
  if (status === 'overclaim') return 'danger';
  if (status === 'unsupported_by_available_evidence') return 'neutral';
  return 'accent';
}

/** Plain-language label. "Extracted" means read from the text, never verified. */
export function statementLabel(status: string): string {
  switch (status) {
    case 'extracted':
      return 'Extracted from text, not verified';
    case 'unsupported_by_available_evidence':
      return 'Not supported by available evidence';
    case 'overclaim':
      return 'Possible overclaim';
    default:
      return status ? status.replace(/_/g, ' ') : 'Unclassified';
  }
}

/** "12,000 hectares (2020-2023)", or just what the API gave; empty parts are skipped, nothing is invented. */
export function formatStatementValue(s: Pick<Statement, 'value' | 'unit' | 'period'>): string {
  const parts: string[] = [];
  if (typeof s.value === 'number' && Number.isFinite(s.value)) parts.push(s.value.toLocaleString('en-US', { maximumFractionDigits: 2 }));
  if (s.unit) parts.push(s.unit);
  const base = parts.join(' ');
  if (s.period) return base ? `${base} (${s.period})` : s.period;
  return base;
}

export const statementsOf = (data: Pick<ClaimsResponse, 'statements'>): Statement[] => (Array.isArray(data.statements) ? data.statements : []);
export const unrecognisedOf = (data: Pick<ClaimsResponse, 'unrecognised_sentences'>) =>
  Array.isArray(data.unrecognised_sentences) ? data.unrecognised_sentences : [];

/** Spans to highlight in the document: every statement when present, otherwise the older claim spans. */
export function highlightSpans(data: Pick<ClaimsResponse, 'claims' | 'statements'>) {
  const st = statementsOf(data);
  return st.length > 0 ? st.map((s) => s.span) : data.claims.map((c) => c.span);
}

/** Index of the statement that covers a claim's span, so a claim row can scroll to its highlight. */
export function statementIndexForClaim(data: Pick<ClaimsResponse, 'claims' | 'statements'>, claimIndex: number): number {
  const st = statementsOf(data);
  if (st.length === 0) return claimIndex;
  const c = data.claims[claimIndex];
  if (!c) return -1;
  return st.findIndex((s) => s.span.start <= c.span.start && s.span.end >= c.span.end);
}
