import { describe, expect, it } from 'vitest';
import { buildCaseViz, observedSeriesMap } from '../src/features/cases/viz';
import { MOCK_VERIFICATION_RESULTS } from '../src/lib/fixtures/simulated-data';

describe('buildCaseViz', () => {
  it('returns null without a fixture', () => {
    expect(buildCaseViz(null)).toBeNull();
  });
  it('reads values only from the fixture', () => {
    const v = buildCaseViz(MOCK_VERIFICATION_RESULTS['kariba-redd'])!;
    expect(v.observed.length).toBeGreaterThan(2);
    expect(v.gap.length).toBe(v.observed.length);
    expect(v.donorsAdmitted).toBe(50);
    expect(v.placeboP).toBeCloseTo(0.0196, 3);
    expect(v.specLow!).toBeLessThan(v.specHigh!);
  });
  it('omits cases without fixtures from the series map', () => {
    const m = observedSeriesMap(['kariba-redd', 'mikoko-pamoja'], (id) => MOCK_VERIFICATION_RESULTS[id] ?? null);
    expect(Object.keys(m)).toEqual(['kariba-redd']);
  });
});
