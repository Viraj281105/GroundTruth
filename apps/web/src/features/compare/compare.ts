import type { CaseDetail } from '../../lib/types';
import { COMPARE_COPY as C } from './copy';

export interface CompareIds {
  a: string;
  b: string;
}

/** Read `a` and `b` from query params; absent values are empty strings. */
export function parseCompareParams(params: { get(name: string): string | null }): CompareIds {
  return { a: (params.get('a') ?? '').trim(), b: (params.get('b') ?? '').trim() };
}

/** Shareable URL for a pair. Empty ids are omitted. */
export function buildCompareUrl({ a, b }: CompareIds): string {
  const q = new URLSearchParams();
  if (a) q.set('a', a);
  if (b) q.set('b', b);
  const s = q.toString();
  return s ? `/compare?${s}` : '/compare';
}

export const swapIds = ({ a, b }: CompareIds): CompareIds => ({ a: b, b: a });

export interface CompareRow {
  key: string;
  label: string;
  /** null means the API did not return the value; the UI says "not available". */
  value: string | null;
}

const num = (n: number | null | undefined, unit = '') =>
  n === null || n === undefined ? null : `${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}${unit}`;

/**
 * Rows for one case. The case record carries no estimate, so effect, uncertainty, fit,
 * placebo p-value and verdict stay null here: they are never filled from anywhere but a run.
 */
export function compareRows(detail: CaseDetail | null): CompareRow[] {
  return [
    { key: 'effect', label: C.rows.effect, value: null },
    { key: 'uncertainty', label: C.rows.uncertainty, value: null },
    { key: 'donors', label: C.rows.donors, value: num(detail?.donor_pool_size) },
    { key: 'fit', label: C.rows.fit, value: null },
    { key: 'placebo', label: C.rows.placebo, value: null },
    { key: 'verdict', label: C.rows.verdict, value: null },
    { key: 'area', label: C.rows.area, value: num(detail?.area_ha, ' ha') },
  ];
}
