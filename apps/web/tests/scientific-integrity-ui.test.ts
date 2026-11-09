import { describe, expect, it } from 'vitest';

import { COPY as EVIDENCE_COPY, EVIDENCE_METHODOLOGICAL_NOTES } from '../src/features/case/evidence/copy';
import { METHOD_COPY, METHODOLOGICAL_NOTES } from '../src/features/method/copy';
import { SCIENTIFIC_INTEGRITY_NOTICES, STATUS_COPY } from '../src/features/status/copy';
import { formatConfidenceInterval } from '../src/lib/formatters';

function collectStrings(value: unknown): string[] {
  if (typeof value === 'string') {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.flatMap(collectStrings);
  }
  if (value !== null && typeof value === 'object') {
    return Object.values(value).flatMap(collectStrings);
  }
  return [];
}

describe('Scientific integrity UI copy and formatting', () => {
  it('exposes SCIENTIFIC_INTEGRITY_NOTICES and biomass calibration requirement in status/copy.ts', () => {
    expect(SCIENTIFIC_INTEGRITY_NOTICES.dataModeNotice).toBe(
      'All bundled demonstrations run on deterministic SYNTHETIC fixtures. Real satellite ingestion is not enabled unless live Earth Observation credentials and pipelines are active.',
    );
    expect(SCIENTIFIC_INTEGRITY_NOTICES.calibrationNotice).toBe(
      'NOT CALIBRATED: NDVI is a spectral reflectance ratio, not a carbon stock. Carbon conversion is refused unless a sourced, site-calibrated biomass model is supplied.',
    );
    expect(SCIENTIFIC_INTEGRITY_NOTICES.uncertaintyNotice).toBe(
      'Sensitivity envelopes report the range across specifications or leave-one-out refits (not a 95% confidence interval). Calibrated biomass error propagation reports a one-sigma (~68%) interval under assumed model error.',
    );
    expect(STATUS_COPY.capabilityDescriptions.biomass_carbon_conversion).toContain('NOT CALIBRATED');
    expect(STATUS_COPY.capabilityDescriptions.biomass_carbon_conversion).toContain('site-calibrated biomass model');
  });

  it('documents SUTVA, weight identification, permutation p-value floor, and SMD in method/copy.ts and case/evidence/copy.ts', () => {
    const methodText = collectStrings(METHOD_COPY).join(' ');
    const evidenceText = collectStrings(EVIDENCE_COPY).join(' ');

    for (const copyText of [methodText, evidenceText]) {
      expect(copyText).toContain('SUTVA');
      expect(copyText).toContain('host districts');
      expect(copyText).toContain('leakage belts');
      expect(copyText).toContain('weights_identified');
      expect(copyText).toContain('T_0');
      expect(copyText).toContain('1 / (N + 1)');
      expect(copyText).toContain('Standardized Mean Difference (SMD)');
      expect(copyText).toContain('static baseline covariate balance');
    }

    expect(METHODOLOGICAL_NOTES.sutvaDonorEligibility).toContain('SUTVA');
    expect(EVIDENCE_METHODOLOGICAL_NOTES.weightIdentification).toContain('weights_identified');
  });

  it('distinguishes sensitivity-envelope from assumed-1sigma-interval in formatConfidenceInterval', () => {
    const envelopeText = formatConfidenceInterval(
      { lower: -0.08, upper: -0.02, level: 0.95, kind: 'sensitivity-envelope' },
      'NDVI',
    );
    const oneSigmaText = formatConfidenceInterval(
      { lower: 100, upper: 140, level: 0.68, kind: 'assumed-1sigma-interval' },
      'tCO2e',
    );

    expect(envelopeText).toContain('sensitivity-envelope: range, not a confidence interval');
    expect(envelopeText).not.toContain('95% Sensitivity Envelope');
    expect(oneSigmaText).toContain('one-sigma interval under an assumed model error, ~68%; not a 95% confidence interval');
    expect(envelopeText).not.toBe(oneSigmaText);
  });

  it('contains no deprecated hardcoded numbers or "95% Sensitivity Envelope" labels in UI copy modules', () => {
    const allCopyStrings = [
      ...collectStrings(STATUS_COPY),
      ...collectStrings(SCIENTIFIC_INTEGRITY_NOTICES),
      ...collectStrings(METHOD_COPY),
      ...collectStrings(EVIDENCE_COPY),
    ].join('\n');

    expect(allCopyStrings).not.toContain('57.04%');
    expect(allCopyStrings).not.toContain('70.86%');
    expect(allCopyStrings).not.toContain('0.0609');
    expect(allCopyStrings).not.toContain('95% Sensitivity Envelope');
  });
});
