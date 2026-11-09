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

export function titleCase(slug: string): string {
  const s = slug.replace(/[_-]+/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}
