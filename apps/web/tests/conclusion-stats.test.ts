import { describe, it, expect } from 'vitest';
import {
  formatPermutationSignificance,
  formatJackknifeStability,
  formatDidParallelTrends,
  formatUncertaintyEnvelope,
} from '../src/lib/formatters';
import { Evidence, Provenance } from '../src/lib/types';

/**
 * Follow-up to issue #58: the "Scientific Conclusion" footer on the case
 * detail page used to show hardcoded numbers (p = 0.038, "24 refits",
 * "Div: 0.0018", a fake sha256 hash, a fake confidence interval) regardless
 * of what a real backend result contained. These functions derive that
 * display from real evidence items only, and must never fabricate a value
 * when the underlying evidence item — or one of its parameters/qualifiers —
 * is absent.
 */

function provenance(overrides: Partial<Provenance> = {}): Provenance {
  return {
    source: 'test',
    method: 'test-method',
    stage: 'test-stage',
    source_uri: null,
    retrieved_at: null,
    code_version: null,
    parameters: {},
    inputs: [],
    notes: null,
    ...overrides,
  };
}

function evidence(overrides: Partial<Evidence> & Pick<Evidence, 'id' | 'value'>): Evidence {
  return {
    label: 'test evidence',
    unit: '',
    confidence: null,
    provenance: provenance(),
    qualifiers: {},
    ...overrides,
  };
}

describe('formatPermutationSignificance', () => {
  it('formats a real placebo.p_value item with its p-value convention', () => {
    const items = [evidence({ id: 'placebo.p_value', value: 0.042 })];
    expect(formatPermutationSignificance(items)).toBe('p = 0.042');
  });

  it('reports "Not measured" rather than a fabricated p-value when the item is absent', () => {
    expect(formatPermutationSignificance([])).toBe('Not measured');
  });
});

describe('formatJackknifeStability', () => {
  it('reports real stability and the real refit count from provenance.parameters', () => {
    const items = [
      evidence({
        id: 'robustness.sign_stable',
        value: true,
        provenance: provenance({ parameters: { n_refits: 24 } }),
      }),
    ];
    expect(formatJackknifeStability(items)).toBe('Stable across 24 refits');
  });

  it('reports instability honestly when the sign is not stable', () => {
    const items = [
      evidence({
        id: 'robustness.sign_stable',
        value: false,
        provenance: provenance({ parameters: { n_refits: 5 } }),
      }),
    ];
    expect(formatJackknifeStability(items)).toBe('Not stable across 5 refits');
  });

  it('never fabricates a refit count when n_refits is missing', () => {
    const items = [evidence({ id: 'robustness.sign_stable', value: true, provenance: provenance() })];
    expect(formatJackknifeStability(items)).toBe('Stable across an unrecorded number of refits');
  });

  it('reports "Not measured" when the evidence item itself is absent', () => {
    expect(formatJackknifeStability([])).toBe('Not measured');
  });
});

describe('formatDidParallelTrends', () => {
  it('formats a real plausible result with its real divergence value', () => {
    const items = [
      evidence({
        id: 'crosscheck.did_estimate',
        value: 0.039,
        qualifiers: { parallel_trends_plausible: true },
      }),
      evidence({ id: 'crosscheck.did_pre_trend_divergence', value: 0.0018 }),
    ];
    expect(formatDidParallelTrends(items)).toBe('Plausible (Div: 0.0018)');
  });

  it('formats an implausible result without inventing a divergence figure', () => {
    const items = [
      evidence({
        id: 'crosscheck.did_estimate',
        value: 0.039,
        qualifiers: { parallel_trends_plausible: false },
      }),
    ];
    expect(formatDidParallelTrends(items)).toBe('Implausible');
  });

  it('reports "Not measured" when the DiD cross-check was not run at all', () => {
    expect(formatDidParallelTrends([])).toBe('Not measured');
  });
});

describe('formatUncertaintyEnvelope', () => {
  it('formats a real confidence interval compactly', () => {
    expect(
      formatUncertaintyEnvelope({ lower: -0.012, upper: 0.084, level: 0.95, kind: 'sensitivity-envelope' })
    ).toBe('[-0.012, 0.084]');
  });

  it('returns an empty string (not a fabricated interval) when there is no confidence interval', () => {
    expect(formatUncertaintyEnvelope(null)).toBe('');
    expect(formatUncertaintyEnvelope(undefined)).toBe('');
  });
});
