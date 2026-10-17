import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import { placeboDistributionFrom } from '../src/lib/fixtures/simulated-data';
import {
  derivePlaceboDiagnostics,
  inTimeGroup,
  leaveOneOutGroup,
  placeboGroup,
  readPValue,
} from '../src/lib/placebo-diagnostics';
import { formatPermutationSignificance } from '../src/lib/formatters';
import { NOT_MEASURED } from '../src/lib/evidence';
import { Evidence } from '../src/lib/types';

const items = KARIBA_COMPLETED.verification.bundle.items;

function patch(id: string, update: Partial<Evidence>, qualifiers?: Record<string, unknown>): Evidence[] {
  return items.map((e) =>
    e.id === id ? { ...e, ...update, qualifiers: { ...e.qualifiers, ...(qualifiers ?? {}) } } : e,
  );
}

describe('placebo diagnostics', () => {
  it('reads the p-value with its floor and significance level', () => {
    const r = readPValue(items);
    expect(r.floor).toBeCloseTo(1 / 51);
    expect(r.significanceLevel).toBeCloseTo(0.05);
    expect(r.canReject).toBe(true);
    expect(r.atFloor).toBe(true);
  });

  it('explains a p-value at the floor instead of implying it is near zero', () => {
    const group = placeboGroup(items);
    expect(group.status).toBe('BELOW SIGNIFICANCE LEVEL');
    expect(group.summary).toMatch(/smallest p-value this many placebos can produce/);
    expect(group.summary).toMatch(/not a probability of misreporting/);
    const pRow = group.rows[0];
    expect(pRow.display).toBe('p = 0.0196');
    expect(pRow.detail).toBe('Floor 1/(J+1) = 0.0196 · α = 0.05');
  });

  it('says when too few placebos exist to ever reject', () => {
    const few = patch('placebo.p_value', { value: 1 / 16 }, { p_value_floor: 1 / 16, significance_level: 0.05 });
    const group = placeboGroup(few);
    expect(group.status).toBe('TOO FEW PLACEBOS TO REJECT');
    expect(group.tone).toBe('neutral');
  });

  it('keeps a non-significant result neutral, not alarming', () => {
    const group = placeboGroup(patch('placebo.p_value', { value: 0.4 }));
    expect(group.status).toBe('WITHIN PLACEBO RANGE');
    expect(group.tone).toBe('neutral');
  });

  it('reports the in-time placebo with its fake date, unit and pass rule', () => {
    const group = inTimeGroup(items);
    expect(group.status).toBe('NO MATERIAL SPURIOUS EFFECT');
    expect(group.rows[0].display).toMatch(/ ndvi$/);
    expect(group.rows[0].detail).toBe('Fake treatment at period 2006');
    expect(group.rows[1].detail).toMatch(/^Rule: absolute fake effect below half/);
  });

  it('reads a failed in-time placebo as caution', () => {
    const group = inTimeGroup(patch('placebo.in_time_passes', { value: false }));
    expect(group.status).toBe('SPURIOUS EFFECT FOUND');
    expect(group.tone).toBe('caution');
  });

  it('reads leave-one-out from evidence with the refit count', () => {
    const group = leaveOneOutGroup(items);
    expect(group.status).toBe('SIGN STABLE');
    expect(group.rows[0].detail).toBe('12 refits');
    expect(group.rows[1].display).toMatch(/ ndvi$/);
    expect(group.rows[1].detail).toMatch(/^Point estimate: .* ndvi$/);
  });

  it('renders "Not measured" when the in-time placebo was not run', () => {
    const without = items.filter((e) => !e.id.startsWith('placebo.in_time'));
    const group = inTimeGroup(without);
    expect(group.status).toBe(NOT_MEASURED);
    expect(group.summary).toMatch(/not run/);
  });

  it('never renders a bare number', () => {
    for (const group of derivePlaceboDiagnostics(items)) {
      for (const r of group.rows) expect(r.display).not.toMatch(/^-?[\d.,]+$/);
    }
  });

  it('qualifies the summary-card p-value with floor and α', () => {
    expect(formatPermutationSignificance(items)).toBe('p = 0.0196 (floor 0.0196, α = 0.05)');
  });

  it('carries α and floor into the histogram data', () => {
    const data = placeboDistributionFrom(KARIBA_COMPLETED);
    expect(data.significanceLevel).toBeCloseTo(0.05);
    expect(data.pValueFloor).toBeCloseTo(1 / 51);
  });
});
