import { Evidence } from './types';
import { formatEvidenceValue } from './formatters';

/**
 * Evidence lookups for views.
 *
 * Views read values from the bundle by evidence id, never from literals. A
 * missing item is `undefined` and must render as "Not measured" — an older
 * engine, a disabled robustness flag or a refused stage all legitimately
 * leave items out.
 */

export const NOT_MEASURED = 'Not measured';

export function findEvidence(items: Evidence[] | undefined, id: string): Evidence | undefined {
  return items?.find((e) => e.id === id);
}

export function numberValue(item: Evidence | undefined): number | undefined {
  return typeof item?.value === 'number' && Number.isFinite(item.value) ? item.value : undefined;
}

export function booleanValue(item: Evidence | undefined): boolean | undefined {
  return typeof item?.value === 'boolean' ? item.value : undefined;
}

export function numberQualifier(item: Evidence | undefined, key: string): number | undefined {
  const v = item?.qualifiers?.[key];
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

export function listQualifier(item: Evidence | undefined, key: string): unknown[] | undefined {
  const v = item?.qualifiers?.[key];
  return Array.isArray(v) ? v : undefined;
}

/** Format a number to a fixed number of significant figures, keeping integers whole. */
export function sig(value: number, digits = 3): string {
  if (Number.isInteger(value)) return value.toLocaleString('en-US');
  if (value === 0) return '0';
  return Number(value.toPrecision(digits)).toString();
}

/** Value with its own evidence unit, or "Not measured". */
export function withUnit(item: Evidence | undefined): string {
  if (item === undefined) return NOT_MEASURED;
  return formatEvidenceValue(item.value, item.unit || null);
}

/**
 * Tone for a diagnostic check. A failed check is `caution` (amber), never an
 * error: it limits what the result can say, it is not a malfunction.
 */
export type CheckTone = 'positive' | 'caution' | 'neutral';

export function checkTone(passes: boolean | undefined): CheckTone {
  if (passes === undefined) return 'neutral';
  return passes ? 'positive' : 'caution';
}
