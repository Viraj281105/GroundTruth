import { AlignmentRefusalDetail } from './fixtures/generated';

/**
 * Reading a refusal's `detail`. Only the alignment refusal has a structured
 * detail today (`MisalignedSeriesError.as_detail`); anything else is shown as
 * the engine's message alone.
 */

export function isAlignmentDetail(detail: unknown): detail is AlignmentRefusalDetail {
  if (!detail || typeof detail !== 'object') return false;
  const d = detail as Record<string, unknown>;
  return Array.isArray(d.units) && typeof d.window === 'object' && d.window !== null;
}

/** Human-readable stage name for a refusal heading. */
export function refusalStageLabel(stage: string | undefined): string | undefined {
  switch (stage) {
    case 'alignment':
      return 'period alignment';
    case 'matching':
      return 'donor matching';
    case 'causal':
      return 'estimation';
    case 'ingestion':
      return 'data ingestion';
    case 'validation':
      return 'request validation';
    default:
      return stage;
  }
}

/** Compact list of periods, e.g. "2004–2005, 2019". */
export function formatPeriods(periods: number[]): string {
  if (periods.length === 0) return '—';
  const sorted = [...periods].sort((a, b) => a - b);
  const runs: string[] = [];
  let start = sorted[0];
  let prev = sorted[0];
  for (const p of sorted.slice(1)) {
    if (p === prev + 1) {
      prev = p;
      continue;
    }
    runs.push(start === prev ? `${start}` : `${start}–${prev}`);
    start = p;
    prev = p;
  }
  runs.push(start === prev ? `${start}` : `${start}–${prev}`);
  return runs.join(', ');
}
