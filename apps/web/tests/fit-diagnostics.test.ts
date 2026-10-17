import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import { coverageGroup, deriveFitDiagnostics, fitGroup, hullGroup } from '../src/lib/fit-diagnostics';
import { NOT_MEASURED } from '../src/lib/evidence';
import { Evidence } from '../src/lib/types';

const items = KARIBA_COMPLETED.verification.bundle.items;

function withValue(id: string, value: Evidence['value'], qualifiers?: Record<string, unknown>): Evidence[] {
  return items.map((e) =>
    e.id === id ? { ...e, value, qualifiers: { ...e.qualifiers, ...(qualifiers ?? {}) } } : e,
  );
}

describe('fit diagnostics', () => {
  it('reads every row from an evidence item in the generated bundle', () => {
    for (const group of deriveFitDiagnostics(items)) {
      for (const row of group.rows) {
        expect(row.item?.id).toBe(row.evidenceId);
        expect(row.display).not.toBe(NOT_MEASURED);
      }
    }
  });

  it('never renders a bare number', () => {
    for (const group of deriveFitDiagnostics(items)) {
      for (const row of group.rows) {
        expect(row.display).not.toMatch(/^-?[\d.,]+$/);
      }
    }
  });

  it('states the fit gate threshold alongside the relative RMSPE', () => {
    const group = fitGroup(items);
    expect(group.status).toBe('WITHIN FIT GATE');
    expect(group.tone).toBe('positive');
    expect(group.rows[0].display).toMatch(/× pre-period SD$/);
    expect(group.rows[0].detail).toMatch(/^Gate: at most 0\.3 × SD$/);
  });

  it('reads a failed fit gate as caution, never error', () => {
    const group = fitGroup(withValue('fit.relative_pre_rmspe', 0.45));
    expect(group.status).toBe('OUTSIDE FIT GATE');
    expect(group.tone).toBe('caution');
  });

  it('explains a project outside the donor hull without implying wrongdoing', () => {
    const group = hullGroup(withValue('fit.inside_donor_hull', false));
    expect(group.status).toBe('OUTSIDE DONOR HULL');
    expect(group.tone).toBe('caution');
    expect(group.summary).toMatch(/donor pool is inadequate/);
    expect(group.summary.toLowerCase()).not.toMatch(/fraud|mislead|false claim|manipulat/);
  });

  it('shows the share of pre-periods outside the envelope as a percentage', () => {
    const row = hullGroup(items).rows.find((r) => r.evidenceId === 'fit.hull_periods_outside_envelope');
    expect(row?.display).toBe('0% of pre-periods');
  });

  it('reports period coverage with ranges and the treatment boundary', () => {
    const group = coverageGroup(items);
    expect(group.tone).toBe('neutral');
    const [pre, post, boundary] = group.rows;
    expect(pre.display).toBe('10 periods');
    expect(pre.detail).toBe('2001–2010');
    expect(post.display).toBe('12 periods');
    expect(post.detail).toBe('2011–2022');
    expect(boundary.display).toBe('Period 2011');
    expect(boundary.detail).toBe('No periods dropped');
  });

  it('names dropped periods when the provider returned extra ones', () => {
    const group = coverageGroup(withValue('fit.treatment_boundary_period', 2011, { dropped_periods: [1999, 2000] }));
    expect(group.summary).toMatch(/1999, 2000/);
    expect(group.rows[2].detail).toBe('Dropped: 1999, 2000');
  });

  it('renders "Not measured" for an older bundle without the new evidence', () => {
    const legacy = items.filter((e) => !e.id.startsWith('fit.'));
    for (const group of deriveFitDiagnostics(legacy)) {
      expect(group.status).toBe(NOT_MEASURED);
      expect(group.tone).toBe('neutral');
      expect(group.rows.every((r) => r.display === NOT_MEASURED && r.item === undefined)).toBe(true);
    }
  });
});
