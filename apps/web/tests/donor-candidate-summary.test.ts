import { describe, it, expect } from 'vitest';
import { formatMeasurement } from '../src/lib/formatters';
import { getDonorCandidateSummary } from '../src/lib/api';
import { DONOR_EXCLUSION_CATEGORIES } from '../src/lib/types';
import { MOCK_CASE_DETAILS } from '../src/lib/fixtures/simulated-data';

/**
 * ADR-011 donor-candidate generation: the frontend representation of
 * unmeasured scientific state. No backend endpoint exists yet (see
 * getDonorCandidateSummary's doc comment), so every measurement must render
 * as an explicit "Not measured" — never a bare 0, and never fabricated data.
 */
describe('formatMeasurement', () => {
  it('renders null and undefined as an explicit "Not measured" state', () => {
    expect(formatMeasurement(null)).toBe('Not measured');
    expect(formatMeasurement(undefined)).toBe('Not measured');
    expect(formatMeasurement(null, 'km²')).toBe('Not measured');
  });

  it('never conflates a genuine 0 measurement with a missing one', () => {
    // 0 admitted donors, or 0 exclusions in a category, is a real finding.
    expect(formatMeasurement(0)).toBe('0');
    expect(formatMeasurement(0, 'donors')).toBe('0 donors');
    expect(formatMeasurement(0)).not.toBe('Not measured');
  });

  it('formats a genuine positive measurement with its unit', () => {
    expect(formatMeasurement(80, 'candidates')).toBe('80 candidates');
    expect(formatMeasurement(785000, 'ha')).toBe('785,000 ha');
  });
});

describe('getDonorCandidateSummary', () => {
  const caseDetail = MOCK_CASE_DETAILS['kariba-redd'];

  it('reports every measurement as unmeasured (null), not zero or fabricated', () => {
    const summary = getDonorCandidateSummary(caseDetail);
    expect(summary.treatedEligibleAreaKm2).toBeNull();
    expect(summary.candidateCount).toBeNull();
    expect(summary.admittedDonorCount).toBeNull();
    expect(summary.exclusionsByCategory).toBeNull();
    expect(summary.rungUsed).toBeNull();
    expect(summary.rungs).toEqual([]);
  });

  it('reports the run as not_started, since no candidate generation has ever run', () => {
    const summary = getDonorCandidateSummary(caseDetail);
    expect(summary.resultState).toBe('not_started');
  });

  it('carries the real case identity, not a fabricated or substituted one', () => {
    const summary = getDonorCandidateSummary(caseDetail);
    expect(summary.caseId).toBe('kariba-redd');
    expect(summary.caseName).toBe(caseDetail.name);
  });

  it('never substitutes another case\'s summary for a missing one', () => {
    const mikoko = getDonorCandidateSummary(MOCK_CASE_DETAILS['mikoko-pamoja']);
    expect(mikoko.caseId).toBe('mikoko-pamoja');
    expect(mikoko.caseId).not.toBe('kariba-redd');
  });
});

describe('DONOR_EXCLUSION_CATEGORIES', () => {
  it('is the fixed ADR-011 category list, known even with no measurements', () => {
    expect(DONOR_EXCLUSION_CATEGORIES).toEqual([
      'empty_after_mask',
      'ecoregion_share',
      'area_floor',
      'area_band',
      'leakage_belt',
      'carbon_project',
    ]);
  });
});
