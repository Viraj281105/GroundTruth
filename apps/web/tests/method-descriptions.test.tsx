import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import { DESCRIBED_METHODS, describeMethod } from '../src/lib/method-descriptions';
import { ProvenanceDrawer } from '../src/components/ui/ProvenanceDrawer';
import type { Evidence } from '../src/lib/types';

const items = KARIBA_COMPLETED.verification.bundle.items as Evidence[];
const byId = (id: string): Evidence => {
  const item = items.find((e) => e.id === id);
  if (!item) throw new Error(`fixture has no ${id}`);
  return item;
};
const render = (evidence: Evidence): string =>
  renderToStaticMarkup(<ProvenanceDrawer evidence={evidence} isOpen onClose={() => {}} />);

/** The simplex constraint belongs to the synthetic-control weight fit only. */
const SIMPLEX = 'Σᵢ wᵢ = 1';

describe('method descriptions', () => {
  it('describe every method the engine emits in the generated fixture', () => {
    const methods = new Set(items.map((e) => e.provenance.method));
    for (const method of methods) {
      expect(describeMethod(method), method).not.toBeNull();
    }
  });

  it('map each method to its own description', () => {
    expect(describeMethod('synthetic-control/simplex-constrained-least-squares')?.title).toMatch(
      /synthetic control/i,
    );
    expect(describeMethod('in-space-placebo-permutation')?.formula?.join(' ')).toContain('J + 1');
    expect(describeMethod('in-time-placebo/pre-period-refit')?.formula?.join(' ')).toContain(
      '0.5',
    );
    expect(describeMethod('convex-hull-necessary-conditions/level-and-envelope')?.caveat).toMatch(
      /necessary, not sufficient/,
    );
    expect(describeMethod('difference-in-differences')?.caveat).toMatch(/parallel trends/);
    expect(describeMethod('cluster-robust-cr1/wild-cluster-bootstrap')?.caveat).toMatch(
      /Control-side uncertainty only/,
    );
    expect(describeMethod('specification-curve/one-at-a-time')?.caveat).toMatch(
      /not a confidence interval/,
    );
    expect(describeMethod('standardised-covariate-distance')?.title).toMatch(/matching/i);
    expect(describeMethod('window-alignment/period-labels')?.title).toMatch(/alignment/i);
    expect(describeMethod('leave-one-donor-out-refit')?.title).toMatch(/leave-one/i);
  });

  it('give the simplex weight program to synthetic control only', () => {
    for (const method of DESCRIBED_METHODS) {
      const formula = describeMethod(method)?.formula?.join('\n') ?? '';
      const isScm = method === 'synthetic-control/simplex-constrained-least-squares';
      expect(formula.includes(SIMPLEX), method).toBe(isScm);
    }
  });

  it('never claim a V-matrix the engine does not fit', () => {
    const scm = describeMethod('synthetic-control/simplex-constrained-least-squares');
    expect(scm?.formula?.join(' ')).not.toMatch(/\|\|_V|‖_V|X_0/);
    expect(scm?.summary.join(' ')).toMatch(/no predictor-weighting \(V\) matrix/);
  });

  it('return null for unknown methods, including object-prototype keys', () => {
    for (const method of ['file-load', 'made-up-estimator', '', 'constructor', 'toString']) {
      expect(describeMethod(method), method).toBeNull();
    }
  });
});

describe('ProvenanceDrawer', () => {
  it('shows the placebo method, not the synthetic-control program, for a p-value', () => {
    const html = render(byId('placebo.p_value'));
    expect(html).toContain('In-space placebo permutation test');
    expect(html).not.toContain(SIMPLEX);
    expect(html).toContain('n_placebos');
    expect(html).toContain('The project is never a donor in a placebo fit');
  });

  it('shows the simplex program for the effect estimate', () => {
    expect(render(byId('effect.point_estimate'))).toContain(SIMPLEX);
  });

  it('shows the method string and parameters only for an unknown method', () => {
    const base = byId('effect.point_estimate');
    const unknown: Evidence = {
      ...base,
      provenance: {
        ...base.provenance,
        method: 'file-load',
        parameters: { path: 'observations.parquet' },
        notes: null,
      },
    };
    const html = render(unknown);
    expect(html).toContain('No description is available for <code>file-load</code>');
    expect(html).toContain('observations.parquet');
    expect(html).not.toContain(SIMPLEX);
    expect(html).not.toContain('Formula');
  });

  it('says so when an unknown method has no parameters', () => {
    const base = byId('effect.point_estimate');
    const html = render({
      ...base,
      provenance: { ...base.provenance, method: 'made-up', parameters: {} },
    });
    expect(html).toContain('No parameters were recorded for it.');
    expect(html).not.toContain('Execution Parameters');
  });

  it('shows no attestation, hash or digest that the evidence does not carry', () => {
    for (const item of items) {
      const html = render(item);
      expect(html, item.id).not.toMatch(/SHA-256|sha256|digest|BIT-PERFECT|Immutable/i);
    }
  });

  it('shows the qualifiers the engine attached', () => {
    const html = render(byId('placebo.p_value'));
    expect(html).toContain('Not a probability of misreporting');
    // Floats are shown to six significant figures, not as binary noise.
    expect(html).toContain('>0.05<');
    expect(html).not.toContain('0.050000000000000044');
  });
});
