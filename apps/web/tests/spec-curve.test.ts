import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import {
  deriveSpecCurve,
  dimensionLabel,
  formatSignAgreement,
  formatSpecCurveMedian,
  specLabel,
} from '../src/lib/spec-curve';
import { Evidence } from '../src/lib/types';

const items = KARIBA_COMPLETED.verification.bundle.items;

describe('specification curve', () => {
  const curve = deriveSpecCurve(items);

  it('reads every per-spec estimate, sorted ascending', () => {
    expect(curve).not.toBeNull();
    const ids = items.filter((e) => e.id.startsWith('robustness.spec_curve.estimate.'));
    expect(curve!.estimates).toHaveLength(ids.length);
    const values = curve!.estimates.map((e) => e.value);
    expect([...values].sort((a, b) => a - b)).toEqual(values);
  });

  it('marks exactly one centre and does not make it the headline', () => {
    const centres = curve!.estimates.filter((e) => e.isCentre);
    expect(centres).toHaveLength(1);
    const median = items.find((e) => e.id === 'robustness.spec_curve.median');
    // The headline is the engine's median across all specifications.
    expect(curve!.median).toBe(median?.value);
    expect(formatSpecCurveMedian(curve!)).not.toContain('centre');
  });

  it('labels the range as a sensitivity envelope, never as a confidence level', () => {
    const text = formatSpecCurveMedian(curve!);
    expect(text).toContain('sensitivity envelope, not a confidence interval');
    expect(text).toContain('across 7 specifications');
    expect(text).not.toMatch(/\d+%/);
    expect(text).toMatch(/ ndvi/);
  });

  it('reports sign agreement and the dimensions not varied', () => {
    expect(formatSignAgreement(curve!)).toBe('100% of specifications');
    expect(curve!.status).toBe('SIGN AGREES ACROSS SPECIFICATIONS');
    expect(curve!.dimensionsNotVaried.map(dimensionLabel)).toEqual([
      'Indicator',
      'Caliper',
      'Covariate weighting',
    ]);
  });

  it('reads a sign flip as caution and names the specifications', () => {
    const flipped: Evidence[] = items.map((e) =>
      e.id === 'robustness.spec_curve.sign_agreement'
        ? { ...e, value: 6 / 7, qualifiers: { sign_flips: ['donor-cap-20'] } }
        : e,
    );
    const c = deriveSpecCurve(flipped)!;
    expect(c.status).toBe('SIGN DEPENDS ON SPECIFICATION');
    expect(c.tone).toBe('caution');
    expect(c.summary).toContain('20 nearest donors');
    expect(c.summary.toLowerCase()).not.toMatch(/fraud|mislead|manipulat/);
  });

  it('gives readable names to engine specification ids', () => {
    expect(specLabel('ridge-0-01')).toBe('Ridge penalty 0.01');
    expect(specLabel('pre-period-8')).toBe('8 pre-treatment periods');
    expect(specLabel('treatment-1-earlier')).toBe('Treatment 1 period earlier');
    expect(specLabel('donor-cap-35')).toBe('35 nearest donors');
    expect(specLabel('something-new')).toBe('something-new');
  });

  it('is null when the run did not compute a curve', () => {
    expect(deriveSpecCurve(items.filter((e) => !e.id.startsWith('robustness.spec_curve')))).toBeNull();
  });
});
