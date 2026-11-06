import { describe, expect, it } from 'vitest';
import { claimPairs } from '../src/features/claims/pairs';

const claim = (value: number) => ({ kind: 'area_hectares', unit: 'ha', value, span: { start: 0, end: 1 } });

describe('claimPairs', () => {
  it('keeps only comparisons with an estimate', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data: any = { claims: [claim(10), claim(20)], comparisons: [{ estimated: null, note: '' }, { estimated: 15, note: '' }] };
    expect(claimPairs(data)).toEqual([{ index: 1, kind: 'area_hectares', unit: 'ha', claimed: 20, estimated: 15 }]);
  });
  it('is empty when nothing is comparable', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(claimPairs({ claims: [], comparisons: [] } as any)).toEqual([]);
  });
});
