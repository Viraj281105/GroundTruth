import { describe, expect, it } from 'vitest';
import type { Evidence } from '../../../lib/types';
import { bboxRect, didVsScm, donorBars, fitDonut, gapSeries, leaveOneOutBars, pDonut, placeboBins, storyNumbers } from './viz-model';

function ev(id: string, value: unknown, qualifiers: Record<string, unknown> = {}): Evidence {
  return { id, value, unit: 'ndvi', qualifiers, provenance: {} } as unknown as Evidence;
}

describe('viz-model', () => {
  it('lists donor weights as percentages in reported order, capped at n', () => {
    const items = [ev('fit.donor_weight.1', 0.2, { donor_unit_id: 'b' }), ev('fit.donor_weight.0', 0.5, { donor_unit_id: 'a' }), ev('fit.donor_weight.2', 0.1)];
    const bars = donorBars(items, 2);
    expect(bars.map((b) => b.label)).toEqual(['a', 'b']);
    expect(bars[0].value).toBeCloseTo(50);
    expect(donorBars([])).toEqual([]);
  });

  it('builds the gap series only with enough finite points', () => {
    const pt = (year: number, gap: number) => ({ year, observed: 0, synthetic: 0, gap, isPost: false });
    expect(gapSeries([pt(2000, 1)])).toEqual([]);
    expect(gapSeries([pt(2000, 1), pt(2001, Number.NaN), pt(2002, 3)])[0].points).toEqual([
      { x: 2000, y: 1 },
      { x: 2002, y: 3 },
    ]);
  });

  it('maps placebo bins', () => {
    expect(placeboBins({ bins: [{ min: 0, max: 1, count: 4 }], projectStatistic: 0, pValue: 0, rank: 1, totalUnits: 1 })).toEqual([{ from: 0, to: 1, count: 4 }]);
  });

  it('needs both value and gate for the fit donut', () => {
    expect(fitDonut([ev('fit.relative_pre_rmspe', 0.4)])).toBeNull();
    expect(fitDonut([ev('fit.relative_pre_rmspe', 0.4, { gate_threshold: 0.5 })])).toEqual({ value: 0.4, gate: 0.5, passes: true });
    expect(fitDonut([ev('fit.relative_pre_rmspe', 0.9, { gate_threshold: 0.5 })])?.passes).toBe(false);
  });

  it('reports p without inventing a significance level', () => {
    expect(pDonut([ev('placebo.p_value', 0.07)])).toEqual({ p: 0.07, level: undefined, significant: undefined });
    expect(pDonut([ev('placebo.p_value', 0.07, { significance_level: 0.1 })])?.significant).toBe(true);
    expect(pDonut([])).toBeNull();
  });

  it('compares estimators using only reported values', () => {
    expect(didVsScm([])).toEqual([]);
    expect(didVsScm([ev('crosscheck.did_estimate', -0.1)])).toHaveLength(1);
    expect(didVsScm([ev('effect.point_estimate', 0.2), ev('crosscheck.did_estimate', -0.1)])).toHaveLength(2);
  });

  it('shows leave-one-out only when the shift and estimate exist', () => {
    expect(leaveOneOutBars([ev('robustness.max_absolute_shift', 0.01)])).toEqual([]);
    expect(leaveOneOutBars([ev('robustness.max_absolute_shift', 0.01), ev('effect.point_estimate', -0.2)])).toHaveLength(2);
  });

  it('omits story numbers that were not reported', () => {
    expect(storyNumbers([])).toEqual([]);
    expect(storyNumbers([ev('effect.point_estimate', 0.2), ev('placebo.p_value', 0.1)]).map((n) => n.label)).toEqual(['Estimated effect', 'Placebo p-value']);
  });

  it('places a bbox inside a padded frame', () => {
    const r = bboxRect([10, 20, 12, 22]);
    expect(r.x).toBeGreaterThan(0);
    expect(r.x + r.w).toBeLessThan(1);
    expect(r.y + r.h).toBeLessThan(1);
  });
});
