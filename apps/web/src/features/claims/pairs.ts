import type { ClaimsResponse } from './client';

export interface ClaimPair {
  index: number;
  kind: string;
  unit: string;
  claimed: number;
  estimated: number;
}

/** Only comparisons that carry an estimate. Claims without one are left out, never zero-filled. */
export function claimPairs(data: Pick<ClaimsResponse, 'claims' | 'comparisons'>): ClaimPair[] {
  const out: ClaimPair[] = [];
  data.claims.forEach((c, i) => {
    const cmp = data.comparisons[i];
    if (cmp && typeof cmp.estimated === 'number' && Number.isFinite(cmp.estimated) && Number.isFinite(c.value)) {
      out.push({ index: i, kind: c.kind, unit: c.unit, claimed: c.value, estimated: cmp.estimated });
    }
  });
  return out;
}
