/** Small pure formatters shared by the panel view-models. */

export const DASH = '-';

/** Renders an arbitrary API value (criteria `observed_value` is `unknown`) without inventing anything. */
export function formatValue(v: unknown): string {
  if (v === null || v === undefined) return DASH;
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : DASH;
  if (typeof v === 'string') return v === '' ? DASH : v;
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  try {
    return JSON.stringify(v);
  } catch {
    return DASH;
  }
}

export const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/**
 * A vegetation index value for reading: four decimals. The stored value has about sixteen
 * digits, which is arithmetic, not measurement precision; the full number stays in the cell's
 * tooltip and in the dossier.
 */
export function formatIndexValue(v: number): string {
  return Number.isFinite(v) ? v.toFixed(4) : DASH;
}

/**
 * The API names each scientific guardrail by its engine identifier ("assert_not_index_to_carbon:
 * Optical indices ..."). A reader needs the sentence; the identifier is kept as a tooltip.
 */
export function splitGuardrail(raw: string): { id: string | null; text: string } {
  const match = /^([a-z][a-z0-9_]*):\s+(.+)$/s.exec(raw);
  return match ? { id: match[1], text: match[2] } : { id: null, text: raw };
}

export function titleCase(slug: string): string {
  const s = slug.replace(/[_-]+/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}
