import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { LifecycleProgress } from '../src/components/panels/LifecycleProgress';
import { lifecycleSteps, progressSummary, type LifecycleInput } from '../src/components/panels/lifecycle.model';
import { inventoryFull } from './panels/fixtures';

vi.mock('next/navigation', () => ({ usePathname: () => '/app/acme/projects/p/overview' }));

const inv = (over: Record<string, unknown> = {}) => ({ ...inventoryFull, ...over }) as NonNullable<LifecycleInput['inventory']>;
const base = (over: Partial<LifecycleInput> = {}): LifecycleInput => ({
  project: { boundary_sha256: 'abc' },
  inventory: inv({
    indicators: [],
    items: null,
    documents_count: 0,
    climate_status: 'unavailable',
    climate_reason: 'No climate record stored.',
    observation_ingestion: { available: false, message: 'No ingestion path exists for this project.' },
  }),
  assessment: { level: 0, level_name: 'Not assessable' },
  claims: { total: 0, supported: 0, partiallySupported: 0, contradicted: 0, unverified: 0, hasClaims: false, isDemo: false },
  ledger: { status: 'empty', record_count: 0, message: '' },
  ...over,
});
const byLabel = (steps: ReturnType<typeof lifecycleSteps>, label: string) => steps.find((s) => s.label === label)!;

describe('lifecycleSteps', () => {
  it('a new project with a boundary: boundary done, nothing else asserted as done', () => {
    const steps = lifecycleSteps(base());
    expect(byLabel(steps, 'Project created').status).toBe('done');
    expect(byLabel(steps, 'Boundary').status).toBe('done');
    expect(byLabel(steps, 'Documents').status).toBe('current');
    expect(steps.filter((s) => s.status === 'done').map((s) => s.label)).toEqual(['Project created', 'Boundary']);
  });

  it('satellite data is "not available" when ingestion is unavailable, using the API message, and never claims ingestion', () => {
    const sat = byLabel(lifecycleSteps(base()), 'Satellite data');
    expect(sat.status).toBe('unavailable');
    expect(sat.description).toBe('No ingestion path exists for this project.');
    expect(sat.description.toLowerCase()).not.toContain('ingested');
  });

  it('documents are done only from the inventory count', () => {
    const steps = lifecycleSteps(base({ inventory: inv({ indicators: [], documents_count: 3, observation_ingestion: null }) }));
    expect(byLabel(steps, 'Documents').status).toBe('done');
    expect(byLabel(steps, 'Documents').description).toContain('3 documents');
  });

  it('no boundary: boundary is not available', () => {
    expect(byLabel(lifecycleSteps(base({ project: { boundary_sha256: null } })), 'Boundary').status).toBe('unavailable');
  });

  it('stored observations make the satellite step done', () => {
    const steps = lifecycleSteps(base({ inventory: inv() }));
    expect(byLabel(steps, 'Satellite data').status).toBe('done');
    expect(byLabel(steps, 'Satellite data').description).toContain('NDVI');
  });

  it('claims, assessment level and ledger come from their own data; a failed ledger is blocked', () => {
    const steps = lifecycleSteps(
      base({
        assessment: { level: 2, level_name: 'Contextual intelligence' },
        claims: { total: 4, supported: 1, partiallySupported: 1, contradicted: 1, unverified: 1, hasClaims: true, isDemo: false },
        ledger: { status: 'failed', record_count: 2, message: '' },
      }),
    );
    expect(byLabel(steps, 'Assessment').status).toBe('done');
    expect(byLabel(steps, 'Assessment').description).toContain('Level 2');
    expect(byLabel(steps, 'Claims').status).toBe('done');
    expect(byLabel(steps, 'Reports & ledger').status).toBe('blocked');
  });

  it('anything that could not be read is unknown, not done', () => {
    const steps = lifecycleSteps(base({ inventory: null, assessment: null, claims: null, ledger: null }));
    for (const l of ['Documents', 'Satellite data', 'Climate record', 'Assessment', 'Claims', 'Reports & ledger']) expect(byLabel(steps, l).status).toBe('unknown');
  });

  it('exactly one step is current and every step maps to a real tab or the project list', () => {
    const steps = lifecycleSteps(base());
    expect(steps.filter((s) => s.status === 'current')).toHaveLength(1);
    const tabs = ['overview', 'observation', 'climate', 'evidence', 'verification', 'reports', 'activity'];
    for (const s of steps) expect(s.segment === null || tabs.includes(s.segment)).toBe(true);
    expect(progressSummary(steps).total).toBe(8);
  });
});

describe('LifecycleProgress', () => {
  it('shows counts from the statuses, links to real pages and no "Step 2 of 9" wording', () => {
    const steps = lifecycleSteps(base());
    const m = renderToStaticMarkup(<LifecycleProgress orgSlug="acme" projectSlug="p" steps={steps} />);
    expect(m).toContain('2 of 8');
    expect(m).toContain('/app/acme/projects/p/evidence');
    expect(m).toContain('Next: Documents');
    expect(m).toContain('data-step-status="unavailable"');
    expect(m).not.toMatch(/of 9|Sentinel-2 & remote sensing time-series ingested/);
  });
});
