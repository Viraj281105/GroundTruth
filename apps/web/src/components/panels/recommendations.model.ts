import type { RecommendationView } from './types';

/**
 * Orders recommendations for a persona (org type): those naming the persona first, then the rest,
 * each group by priority (1 = most urgent). It only reorders: nothing is dropped or rewritten, and
 * the input array is not mutated.
 */
export function recommendationsFor(recs: readonly RecommendationView[], persona?: string | null): RecommendationView[] {
  const hit = (r: RecommendationView) => (persona && r.personas?.includes(persona) ? 0 : 1);
  return recs
    .map((r, i) => ({ r, i }))
    .sort((a, b) => hit(a.r) - hit(b.r) || a.r.priority - b.r.priority || a.i - b.i)
    .map((x) => x.r);
}
