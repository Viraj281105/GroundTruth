import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED, KARIBA_REFUSED_ALIGNMENT } from '../src/lib/fixtures/generated';
import {
  MOCK_VERIFICATION_RESULTS,
  chartSeriesFrom,
  placeboDistributionFrom,
} from '../src/lib/fixtures/simulated-data';

/**
 * The demo fixture is engine output, not hand-typed data. These tests pin the
 * properties the UI relies on so a regeneration that drops an evidence family
 * or loses the simulated marker fails here rather than in a demo.
 */
describe('engine-generated fixtures', () => {
  const ids = KARIBA_COMPLETED.verification.bundle.items.map((e) => e.id);

  it('are unmistakably simulated (R7)', () => {
    for (const meta of [KARIBA_COMPLETED._generated, KARIBA_REFUSED_ALIGNMENT._generated]) {
      expect(meta.marker.startsWith('SIMULATED DATA')).toBe(true);
    }
    expect(KARIBA_COMPLETED.verification.data_mode).toBe('simulated');
    expect(KARIBA_COMPLETED.verification.caveats.some((c) => c.includes('SIMULATED DATA'))).toBe(
      true,
    );
  });

  it('carry every evidence family the UI renders', () => {
    for (const id of [
      'fit.relative_pre_rmspe',
      'fit.inside_donor_hull',
      'fit.hull_level_excess',
      'fit.hull_periods_outside_envelope',
      'fit.n_pre_periods',
      'fit.n_post_periods',
      'fit.treatment_boundary_period',
      'placebo.p_value',
      'placebo.in_time_fake_effect',
      'placebo.in_time_passes',
      'robustness.spec_curve.median',
      'robustness.spec_curve.sign_agreement',
      'crosscheck.did_standard_error',
    ]) {
      expect(ids).toContain(id);
    }
    expect(ids.some((id) => id.startsWith('robustness.spec_curve.estimate.'))).toBe(true);
  });

  it('label every interval with its kind', () => {
    const byId = Object.fromEntries(
      KARIBA_COMPLETED.verification.bundle.items.map((e) => [e.id, e]),
    );
    expect(byId['robustness.spec_curve.median'].confidence?.kind).toBe('sensitivity-envelope');
    expect(byId['crosscheck.did_standard_error'].confidence?.kind).toBe('bootstrap');
    expect(byId['placebo.p_value'].qualifiers).toHaveProperty('p_value_floor');
    expect(byId['placebo.p_value'].qualifiers).toHaveProperty('significance_level');
  });

  it('serves the generated bundle as the Kariba demo verification', () => {
    expect(MOCK_VERIFICATION_RESULTS['kariba-redd'].verification).toBe(
      KARIBA_COMPLETED.verification,
    );
  });

  it('draws the counterfactual path the engine fitted, with no invented interval', () => {
    const series = chartSeriesFrom(KARIBA_COMPLETED);
    const boundary = KARIBA_COMPLETED.verification.bundle.items.find(
      (e) => e.id === 'fit.treatment_boundary_period',
    )?.value;
    expect(series.find((p) => p.isPost)?.year).toBe(boundary);
    expect(series.every((p) => p.ciLower === undefined && p.ciUpper === undefined)).toBe(true);
  });

  it('bins every placebo unit and takes p-value and rank from the bundle', () => {
    const placebo = placeboDistributionFrom(KARIBA_COMPLETED);
    const pValue = KARIBA_COMPLETED.verification.bundle.items.find(
      (e) => e.id === 'placebo.p_value',
    );
    const binned = placebo.bins.reduce((n, b) => n + b.count, 0);
    expect(binned).toBe(KARIBA_COMPLETED.not_served_by_api.placebo_distribution.placebo_statistics.length);
    expect(placebo.pValue).toBe(pValue?.value);
    expect(placebo.rank).toBe(pValue?.qualifiers.rank);
  });

  it('include coverage-rule donor exclusions with the engine reason', () => {
    const coverage = KARIBA_COMPLETED.not_served_by_api.donor_pool.filter((d) =>
      d.exclusion_reason?.startsWith('insufficient clear pre-treatment observations'),
    );
    expect(coverage.length).toBeGreaterThan(0);
    expect(coverage.every((d) => !d.admitted)).toBe(true);
  });

  it('include an alignment refusal with per-unit missing periods', () => {
    const { error_body, not_served_by_api } = KARIBA_REFUSED_ALIGNMENT;
    expect(error_body.detail.code).toBe('insufficient_data');
    expect(error_body.detail.stage).toBe('alignment');
    expect(error_body.detail.is_refusal).toBe(true);
    expect(not_served_by_api.error_detail.units.length).toBe(
      not_served_by_api.error_detail.n_units_misaligned,
    );
    expect(not_served_by_api.error_detail.units.every((u) => u.missing_periods.length > 0)).toBe(
      true,
    );
  });
});
