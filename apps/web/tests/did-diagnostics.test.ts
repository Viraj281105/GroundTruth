import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import { deriveDidDiagnostics, didEstimateGroup, didInferenceGroup } from '../src/lib/did-diagnostics';
import { formatDidParallelTrends } from '../src/lib/formatters';
import { NOT_MEASURED } from '../src/lib/evidence';
import { Evidence } from '../src/lib/types';

const items = KARIBA_COMPLETED.verification.bundle.items;

function patch(id: string, qualifiers: Record<string, unknown>): Evidence[] {
  return items.map((e) => (e.id === id ? { ...e, qualifiers: { ...e.qualifiers, ...qualifiers } } : e));
}

describe('DiD cross-check', () => {
  it('reads the engine’s parallel-trends failure as caution, not as plausible', () => {
    // The generated run fails the screen; the old card said "PLAUSIBLE".
    const group = didEstimateGroup(items);
    expect(group.status).toBe('PARALLEL TRENDS FAIL');
    expect(group.tone).toBe('caution');
    expect(group.summary).toMatch(/rely on the synthetic control/);
  });

  it('shows the estimate with the bootstrap interval and its kind', () => {
    const estimateRow = didEstimateGroup(items).rows[0];
    expect(estimateRow.display).toMatch(/ ndvi$/);
    expect(estimateRow.detail).toMatch(/^\[0\.0455, 0\.0575 ndvi\] \(95% bootstrap\)$/);
  });

  it('shows the CR1 standard error with clustering and bootstrap settings', () => {
    const [seRow, bootRow] = didInferenceGroup(items).rows;
    expect(seRow.display).toMatch(/ ndvi$/);
    expect(seRow.detail).toBe('Clustered by unit · 50 clusters');
    expect(bootRow.display).toContain('95% bootstrap');
    expect(bootRow.detail).toMatch(/^Bootstrap SE 0\.00311 ndvi · rademacher weights · 999 draws$/);
  });

  it('always carries the control-side and independent-units caveats', () => {
    const group = didInferenceGroup(items);
    expect(group.status).toBe('UNITS ASSUMED INDEPENDENT');
    expect(group.caveats).toHaveLength(2);
    expect(group.caveats?.[0]).toMatch(/^Control-side uncertainty only/);
    expect(group.caveats?.[1]).toMatch(/independent draw/);
  });

  it('drops the independent-units caveat when real clusters were used', () => {
    const clustered = patch('crosscheck.did_standard_error', {
      independent_units_assumed: false,
      cluster_level: 'district',
    });
    const group = didInferenceGroup(clustered);
    expect(group.status).toBe('CLUSTERED');
    expect(group.caveats).toHaveLength(1);
    expect(group.rows[0].detail).toBe('Clustered by district · 50 clusters');
  });

  it('reads a plausible screen as positive', () => {
    const group = didEstimateGroup(patch('crosscheck.did_estimate', { parallel_trends_plausible: true }));
    expect(group.status).toBe('PARALLEL TRENDS PLAUSIBLE');
    expect(group.tone).toBe('positive');
  });

  it('renders "Not measured" when the cross-check did not run', () => {
    const without = items.filter((e) => !e.id.startsWith('crosscheck.'));
    for (const g of deriveDidDiagnostics(without)) expect(g.status).toBe(NOT_MEASURED);
    expect(didInferenceGroup(without).caveats).toEqual([]);
  });

  it('never renders a bare number', () => {
    for (const g of deriveDidDiagnostics(items)) {
      for (const r of g.rows) expect(r.display).not.toMatch(/^-?[\d.,]+$/);
    }
  });

  it('summary card names the divergence and its unit', () => {
    expect(formatDidParallelTrends(items)).toBe('Implausible (pre-trend divergence 0.0024 ndvi)');
  });
});
