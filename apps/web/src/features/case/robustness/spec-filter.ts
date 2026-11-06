import type { SpecEstimate } from '../../../lib/spec-curve';

/** Filtering for the multiverse view: pure so it can be tested without a DOM. */

export interface SpecFilter {
  /** Analytic-choice dimension to show, or null for all. */
  dimension: string | null;
  /** Only specifications whose sign differs from the median. */
  flipsOnly: boolean;
}

export const NO_FILTER: SpecFilter = { dimension: null, flipsOnly: false };

export function filterSpecs(specs: SpecEstimate[], filter: SpecFilter): SpecEstimate[] {
  return specs.filter((s) => {
    // The centre belongs to every choice: it is the reference the others vary from.
    if (filter.dimension !== null && s.dimension !== filter.dimension && !s.isCentre) return false;
    if (filter.flipsOnly && !s.flipsSign) return false;
    return true;
  });
}

/** Distinct dimensions present, in first-seen order, excluding the centre. */
export function dimensionsOf(specs: SpecEstimate[]): string[] {
  const seen: string[] = [];
  for (const s of specs) {
    if (s.dimension === 'centre' || s.isCentre) continue;
    if (!seen.includes(s.dimension)) seen.push(s.dimension);
  }
  return seen;
}

export function countByDimension(specs: SpecEstimate[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of specs) {
    if (s.isCentre) continue;
    out[s.dimension] = (out[s.dimension] ?? 0) + 1;
  }
  return out;
}
