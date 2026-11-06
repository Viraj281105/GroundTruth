import { describe, expect, it } from 'vitest';
import { compact, extent, histogram, linePath, linearScale, niceTicks } from '../src/components/charts/scale';

describe('chart scales', () => {
  it('extent ignores non-finite values and returns null when empty', () => {
    expect(extent([3, NaN, 1, Infinity, 2])).toEqual({ min: 1, max: 3 });
    expect(extent([])).toBeNull();
    expect(extent([NaN])).toBeNull();
  });

  it('linearScale maps the domain onto the range, and a flat domain to the midpoint', () => {
    const s = linearScale({ min: 0, max: 10 }, [0, 100]);
    expect(s(0)).toBe(0);
    expect(s(5)).toBe(50);
    expect(s(10)).toBe(100);
    expect(linearScale({ min: 4, max: 4 }, [0, 100])(4)).toBe(50);
  });

  it('niceTicks gives round numbers inside the domain', () => {
    expect(niceTicks({ min: 0, max: 100 }, 5)).toEqual([0, 25, 50, 75, 100]);
    const t = niceTicks({ min: 0.43, max: 0.72 }, 5);
    expect(t[0]).toBeGreaterThanOrEqual(0.43);
    expect(t[t.length - 1]).toBeLessThanOrEqual(0.72 + 1e-9);
    expect(niceTicks({ min: 2, max: 2 })).toEqual([2]);
  });

  it('histogram puts every finite value in exactly one bin', () => {
    const values = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, NaN];
    const bins = histogram(values, 5);
    expect(bins).toHaveLength(5);
    expect(bins.reduce((n, b) => n + b.count, 0)).toBe(11);
    expect(bins[4].count).toBeGreaterThan(0); // the max lands in the last bin
    expect(histogram([], 5)).toEqual([]);
  });

  it('linePath breaks the line at missing points', () => {
    const d = linePath([{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: NaN, y: 2 }, { x: 3, y: 3 }]);
    expect(d).toBe('M0.00 0.00L1.00 1.00M3.00 3.00');
    expect(linePath([])).toBe('');
  });

  it('compact formats axis labels', () => {
    expect(compact(1200)).toBe('1.2k');
    expect(compact(2_500_000)).toBe('2.5M');
    expect(compact(0.0312)).toBe('0.031');
    expect(compact(NaN)).toBe('–');
  });
});
