import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  getCases,
  getCaseDetail,
  verifyCase,
  getVisualizationFixture,
  getHealth,
  isDemoMode,
  ApiUnreachableError,
  API_BASE_URL,
} from '../src/lib/api';
import { MOCK_CASES_SUMMARY, MOCK_CASE_DETAILS } from '../src/lib/fixtures/simulated-data';

/**
 * Issue #58: a dead backend must never be indistinguishable from a
 * successful run, and fixture data must only ever appear behind an explicit,
 * off-by-default NEXT_PUBLIC_DEMO_MODE flag.
 */
describe('api.ts fixture fallback guards (issue #58)', () => {
  const originalFetch = global.fetch;
  const originalDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE;

  function setDemoMode(on: boolean) {
    if (on) {
      process.env.NEXT_PUBLIC_DEMO_MODE = 'true';
    } else {
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
    }
  }

  function stubUnreachableFetch() {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('fetch failed')) as unknown as typeof fetch;
  }

  beforeEach(() => {
    setDemoMode(false);
  });

  afterEach(() => {
    global.fetch = originalFetch;
    if (originalDemoMode === undefined) {
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
    } else {
      process.env.NEXT_PUBLIC_DEMO_MODE = originalDemoMode;
    }
  });

  describe('isDemoMode', () => {
    it('is off unless NEXT_PUBLIC_DEMO_MODE is exactly "true"', () => {
      setDemoMode(false);
      expect(isDemoMode()).toBe(false);
      process.env.NEXT_PUBLIC_DEMO_MODE = 'yes';
      expect(isDemoMode()).toBe(false);
      setDemoMode(true);
      expect(isDemoMode()).toBe(true);
    });
  });

  describe('getCases', () => {
    it('throws ApiUnreachableError when the backend is unreachable and demo mode is off', async () => {
      stubUnreachableFetch();
      await expect(getCases()).rejects.toBeInstanceOf(ApiUnreachableError);
    });

    it('names the unreachable API base URL in the thrown error', async () => {
      stubUnreachableFetch();
      await expect(getCases()).rejects.toThrow(API_BASE_URL);
    });

    it('serves MOCK_CASES_SUMMARY flagged as isDemo when demo mode is explicitly on', async () => {
      setDemoMode(true);
      stubUnreachableFetch();
      const result = await getCases();
      expect(result.isDemo).toBe(true);
      expect(result.data).toEqual(MOCK_CASES_SUMMARY);
    });
  });

  describe('getCaseDetail', () => {
    it('throws ApiUnreachableError when the backend is unreachable and demo mode is off', async () => {
      stubUnreachableFetch();
      await expect(getCaseDetail('kariba-redd')).rejects.toBeInstanceOf(ApiUnreachableError);
    });

    it('serves the matching fixture flagged as isDemo when demo mode is on', async () => {
      setDemoMode(true);
      stubUnreachableFetch();
      const result = await getCaseDetail('kariba-redd');
      expect(result.isDemo).toBe(true);
      expect(result.data).toEqual(MOCK_CASE_DETAILS['kariba-redd']);
    });
  });

  describe('verifyCase', () => {
    it('never reports success when the backend is unreachable and demo mode is off', async () => {
      stubUnreachableFetch();
      const result = await verifyCase('kariba-redd', {
        synthetic: true,
        true_effect: 0.06,
        min_donors: 10,
        include_report: true,
      });
      expect(result.success).toBe(false);
      expect(result.isDemo).toBeFalsy();
      expect(result.error).toContain(API_BASE_URL);
    });

    it('only substitutes a fixture, flagged isDemo, when demo mode is explicitly on', async () => {
      setDemoMode(true);
      stubUnreachableFetch();
      const result = await verifyCase('kariba-redd', {
        synthetic: true,
        true_effect: 0.06,
        min_donors: 10,
        include_report: true,
      });
      expect(result.success).toBe(true);
      expect(result.isDemo).toBe(true);
      expect(result.data?.case_id).toBe('kariba-redd');
    });
  });

  describe('getVisualizationFixture', () => {
    it('returns null for every case when demo mode is off', () => {
      setDemoMode(false);
      expect(getVisualizationFixture('kariba-redd')).toBeNull();
      expect(getVisualizationFixture('mikoko-pamoja')).toBeNull();
      expect(getVisualizationFixture('unknown-case')).toBeNull();
    });

    it('never substitutes another case\'s fixture: a missing fixture is null, not Kariba', () => {
      setDemoMode(true);
      // Only 'kariba-redd' has a fixture in MOCK_VERIFICATION_RESULTS.
      const result = getVisualizationFixture('mikoko-pamoja');
      expect(result).toBeNull();
      expect(result?.verification.case_id).not.toBe('kariba-redd');
    });

    it('returns the matching fixture for a case that does have one, under demo mode', () => {
      setDemoMode(true);
      const result = getVisualizationFixture('kariba-redd');
      expect(result?.verification.case_id).toBe('kariba-redd');
    });
  });

  describe('getHealth', () => {
    it('renders an honest "unreachable" status rather than a fabricated capability claim', async () => {
      stubUnreachableFetch();
      const health = await getHealth();
      expect(health.status).toBe('unreachable');
      expect(health.version).toBe('unknown');
      expect(health.engine_capabilities).toEqual({});
    });
  });
});
