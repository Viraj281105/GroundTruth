import { describe, it, expect } from 'vitest';
import {
  formatEvidenceValue,
  formatConfidenceInterval,
  formatHectares,
  formatDivergenceRatio,
  formatPValue,
  formatSMD,
} from '../src/lib/formatters';
import { verdictTone, isSimulated, VerdictLabel } from '../src/lib/types';
import { MOCK_VERIFICATION_RESULTS } from '../src/lib/fixtures/simulated-data';

describe('Scientific UI Rules Verification', () => {
  describe('Rule: No Bare Numbers', () => {
    it('always formats values with units attached', () => {
      expect(formatEvidenceValue(0.042, 'ndvi')).toBe('0.042 ndvi');
      expect(formatEvidenceValue(785000, 'ha')).toBe('785,000 ha');
      expect(formatEvidenceValue(27000000, 'tCO2e')).toBe('27,000,000 tCO2e');
    });

    it('formats confidence intervals with their kind explicitly stated', () => {
      const interval = formatConfidenceInterval(
        { lower: -0.012, upper: 0.084, level: 0.95, kind: 'sensitivity-envelope' },
        'ndvi'
      );
      expect(interval).toContain('[-0.0120, 0.0840 ndvi]');
      expect(interval).toContain('95% sensitivity-envelope');
    });
  });

  describe('Rule: INCONCLUSIVE Must Be a Legitimate Neutral State', () => {
    it('styles inconclusive as neutral rather than caution or positive', () => {
      expect(verdictTone('inconclusive')).toBe('neutral');
    });

    it('styles divergent_from_claim as caution (amber), never alarm-red or negative', () => {
      expect(verdictTone('divergent_from_claim')).toBe('caution');
    });

    it('styles consistent_with_claim as positive', () => {
      expect(verdictTone('consistent_with_claim')).toBe('positive');
    });
  });

  describe('Rule: Simulated Data Banner Unmissable & Persistent', () => {
    it('correctly detects simulated data mode', () => {
      const kariba = MOCK_VERIFICATION_RESULTS['kariba-redd'].verification;
      expect(isSimulated(kariba)).toBe(true);
      expect(kariba.data_mode).toBe('simulated');
    });

    it('all mock verification results carry explicit simulated data warnings', () => {
      const kariba = MOCK_VERIFICATION_RESULTS['kariba-redd'].verification;
      expect(kariba.warnings.some((w) => w.includes('SIMULATED DATA'))).toBe(true);
      expect(kariba.caveats.some((c) => c.includes('SIMULATED DATA'))).toBe(true);
    });
  });

  describe('Rule: Never Visually Imply Fraud or Wrongdoing', () => {
    it('verdict copy uses neutral screening language rather than criminal or fraud claims', () => {
      const kariba = MOCK_VERIFICATION_RESULTS['kariba-redd'].verification;
      const allText = [
        kariba.verdict_rationale,
        ...kariba.caveats,
        ...kariba.warnings,
      ].join(' ').toLowerCase();

      // Enforce: Never accuse fraud or crime in automated output
      expect(allText).not.toContain('fraud detected');
      expect(allText).not.toContain('guilty');
      expect(allText).not.toContain('misconduct confirmed');
      // Instead, must explain that divergence is a reason to review the baseline
      expect(allText).toContain('review');
    });
  });

  describe('Statistical Formatters', () => {
    it('formats p-values with floor', () => {
      expect(formatPValue(0.042)).toBe('p = 0.042');
      expect(formatPValue(0.0001)).toBe('p < 0.001');
    });

    it('formats SMD balance status against 0.25 threshold', () => {
      const balanced = formatSMD(0.182);
      expect(balanced.formatted).toBe('0.182 SMD');
      expect(balanced.isBalanced).toBe(true);

      const unbalanced = formatSMD(0.32);
      expect(unbalanced.isBalanced).toBe(false);
    });
  });
});
