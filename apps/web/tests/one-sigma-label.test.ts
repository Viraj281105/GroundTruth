import { describe, expect, it } from 'vitest';
import { formatConfidenceInterval } from '../src/lib/formatters';
import { describeEffect } from '../src/features/case/overview/model';

const oneSigma = { lower: 5, upper: 9, level: 0.6827, kind: 'assumed-1sigma-interval' };

describe('assumed one-sigma interval labelling', () => {
  it('is never presented as a 95% confidence interval', () => {
    const text = formatConfidenceInterval(oneSigma, 'tCO2e');
    expect(text).toContain('one-sigma');
    expect(text).toContain('not a 95% confidence interval');
    expect(text).not.toMatch(/\(95%/);
  });

  it('is described in plain language without a 95% claim', () => {
    const text = describeEffect('7 tCO2e', oneSigma, '[5, 9]');
    expect(text).toContain('one-sigma');
    expect(text).toContain('not a 95% confidence interval');
  });
});

