import type { CaseSummary } from '../../lib/types';

export type SortKey = 'name' | 'standard' | 'period';

export interface CaseQuery {
  search: string;
  standard: string; // 'all' or a standard
  status: string; // 'all' or a status
  sort: SortKey;
}

export const DEFAULT_QUERY: CaseQuery = { search: '', standard: 'all', status: 'all', sort: 'name' };

/** Distinct values of a field, sorted, for building filter options from data. */
export function distinct(cases: CaseSummary[], key: 'standard' | 'status'): string[] {
  return [...new Set(cases.map((c) => c[key]))].sort((a, b) => a.localeCompare(b));
}

function matchesSearch(c: CaseSummary, q: string): boolean {
  if (!q) return true;
  return [c.name, c.case_id, c.country, c.ecosystem, c.standard, c.registry_id ?? '']
    .join(' ')
    .toLowerCase()
    .includes(q);
}

export function filterCases(cases: CaseSummary[], query: CaseQuery): CaseSummary[] {
  const q = query.search.trim().toLowerCase();
  const out = cases.filter(
    (c) =>
      (query.standard === 'all' || c.standard === query.standard) &&
      (query.status === 'all' || c.status === query.status) &&
      matchesSearch(c, q),
  );
  const cmp: Record<SortKey, (a: CaseSummary, b: CaseSummary) => number> = {
    name: (a, b) => a.name.localeCompare(b.name),
    standard: (a, b) => a.standard.localeCompare(b.standard) || a.name.localeCompare(b.name),
    period: (a, b) => a.pre_period.localeCompare(b.pre_period) || a.name.localeCompare(b.name),
  };
  return [...out].sort(cmp[query.sort]);
}

export type StatusTone = 'neutral' | 'accent' | 'caution';

/** Human label and chip tone for a case status; unknown statuses are shown verbatim, never guessed. */
export function statusInfo(status: string): { label: string; tone: StatusTone } {
  switch (status) {
    case 'scaffolded':
      return { label: 'Scaffolded', tone: 'neutral' };
    case 'analysed':
      return { label: 'Analysed', tone: 'accent' };
    case 'refused':
      return { label: 'Refused', tone: 'caution' };
    default:
      return { label: status, tone: 'neutral' };
  }
}
