import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getRefusalFixture, verifyCase } from '../src/lib/api';
import { KARIBA_COMPLETED, KARIBA_REFUSED_ALIGNMENT } from '../src/lib/fixtures/generated';
import { MOCK_VERIFICATION_RESULTS } from '../src/lib/fixtures/simulated-data';
import { formatPeriods, isAlignmentDetail, refusalStageLabel } from '../src/lib/refusal';
import { exclusionRule, groupExclusions, poolGroup, weightsGroup } from '../src/lib/donor-pool';

const items = KARIBA_COMPLETED.verification.bundle.items;

describe('alignment refusal', () => {
  const originalFetch = global.fetch;
  const originalDemo = process.env.NEXT_PUBLIC_DEMO_MODE;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_DEMO_MODE;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalDemo === undefined) delete process.env.NEXT_PUBLIC_DEMO_MODE;
    else process.env.NEXT_PUBLIC_DEMO_MODE = originalDemo;
  });

  it('keeps the engine code, stage and remediation from a 422 refusal body', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => KARIBA_REFUSED_ALIGNMENT.error_body,
    }) as unknown as typeof fetch;
    const result = await verifyCase('kariba-redd');
    expect(result.isRefusal).toBe(true);
    expect(result.refusal?.code).toBe('insufficient_data');
    expect(result.refusal?.stage).toBe('alignment');
    expect(result.refusal?.remediation).toMatch(/^Obtain observations for the missing periods/);
    // The API does not send AnalysisError.detail yet, so nothing is invented.
    expect(result.refusal?.detail).toBeUndefined();
  });

  it('reads AnalysisError.detail once the API includes it', async () => {
    const body = {
      detail: { ...KARIBA_REFUSED_ALIGNMENT.error_body.detail, detail: KARIBA_REFUSED_ALIGNMENT.not_served_by_api.error_detail },
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => body }) as unknown as typeof fetch;
    const result = await verifyCase('kariba-redd');
    expect(isAlignmentDetail(result.refusal?.detail)).toBe(true);
  });

  it('serves the refusal preview only in demo mode, with per-unit detail', () => {
    expect(getRefusalFixture('kariba-redd')).toBeNull();
    process.env.NEXT_PUBLIC_DEMO_MODE = 'true';
    const r = getRefusalFixture('kariba-redd');
    expect(r?.stage).toBe('alignment');
    expect(isAlignmentDetail(r?.detail)).toBe(true);
    expect(getRefusalFixture('mikoko-pamoja')).toBeNull();
  });

  it('formats missing periods compactly', () => {
    expect(formatPeriods([2005, 2004])).toBe('2004–2005');
    expect(formatPeriods([2019])).toBe('2019');
    expect(formatPeriods([2001, 2002, 2003, 2010])).toBe('2001–2003, 2010');
    expect(formatPeriods([])).toBe('—');
  });

  it('names the refusal stage in plain words', () => {
    expect(refusalStageLabel('alignment')).toBe('period alignment');
    expect(refusalStageLabel('somewhere-new')).toBe('somewhere-new');
  });
});

describe('donor pool', () => {
  const candidates = KARIBA_COMPLETED.not_served_by_api.donor_pool;

  it('maps every engine exclusion reason to its rule', () => {
    expect(exclusionRule('inside project leakage belt (potential spillover contamination)')).toBe('leakage_belt');
    expect(exclusionRule('outside common support: elevation_m differs by 3.20 SD (caliper 3.00)')).toBe('common_support');
    expect(exclusionRule('insufficient clear pre-treatment observations (2 < 4)')).toBe('pre_treatment_coverage');
    expect(exclusionRule('ranked 51 by covariate distance, beyond the max_donors cap of 50')).toBe('donor_cap');
    expect(exclusionRule('something unseen')).toBe('other');
  });

  it('groups exclusions so their counts add up to matching.n_candidates_excluded', () => {
    const groups = groupExclusions(candidates);
    const total = groups.reduce((n, g) => n + g.candidates.length, 0);
    expect(total).toBe(items.find((e) => e.id === 'matching.n_candidates_excluded')?.value);
    const coverage = groups.find((g) => g.rule === 'pre_treatment_coverage');
    expect(coverage?.candidates.map((c) => c.unit_id).sort()).toEqual(['donor-003', 'donor-017', 'donor-041']);
    expect(groups.some((g) => g.rule === 'other')).toBe(false);
  });

  it('reads pool counts and balance from evidence', () => {
    const g = poolGroup(items);
    expect(g.status).toBe('BALANCED');
    expect(g.rows.map((r) => r.display)).toEqual(['80 regions', '50 regions', '30 regions', '0.199 SMD']);
    expect(g.rows[3].detail).toBe('Guideline: at most 0.25 SMD across 5 covariates');
  });

  it('reads contributing donor weights from fit.donor_weight.*, not a hand-drawn layout', () => {
    const g = weightsGroup(items);
    expect(g.rows).toHaveLength(5);
    expect(g.rows[0].label).toBe('donor-076');
    expect(g.rows[0].display).toBe('28.7% of the synthetic control');
    expect(g.status).toBe('WEIGHTS NOT UNIQUE');
    expect(g.caveats?.[0]).toMatch(/one of several equally good weightings/);
  });

  it('serves the engine candidate list in the demo fixture', () => {
    expect(MOCK_VERIFICATION_RESULTS['kariba-redd'].donorPool).toBe(candidates);
  });
});
