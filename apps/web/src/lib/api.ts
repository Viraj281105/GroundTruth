import {
  CaseDetail,
  CaseSummary,
  DonorCandidateSummary,
  HealthResponse,
  VerificationRequest,
  VerificationResponse,
} from './types';
import {
  MOCK_CASES_SUMMARY,
  MOCK_CASE_DETAILS,
  MOCK_VERIFICATION_RESULTS,
  VerificationFixtureData,
} from './fixtures/simulated-data';
import { AlignmentRefusalDetail, KARIBA_REFUSED_ALIGNMENT } from './fixtures/generated';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Explicit, off-by-default demo gate. Fixture data may only ever be returned
 * to a caller when this is true, and every caller that receives it must be
 * told so via `isDemo` — never substituted silently for a real result.
 */
export function isDemoMode(): boolean {
  return process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
}

/**
 * Thrown when the backend cannot be reached and demo mode is off. A dead
 * backend must never be indistinguishable from a successful run.
 */
export class ApiUnreachableError extends Error {
  constructor(public readonly apiBaseUrl: string, cause?: unknown) {
    super(`Backend API is unreachable at ${apiBaseUrl}.`);
    this.name = 'ApiUnreachableError';
    if (cause !== undefined) {
      (this as { cause?: unknown }).cause = cause;
    }
  }
}

export interface DemoResult<T> {
  data: T;
  /** True when `data` is fixture data served under NEXT_PUBLIC_DEMO_MODE. */
  isDemo: boolean;
}

/**
 * Fetch list of all project cases.
 *
 * Throws `ApiUnreachableError` when the backend cannot be reached and demo
 * mode is off.
 */
export async function getCases(): Promise<DemoResult<CaseSummary[]>> {
  try {
    const res = await fetch(`${API_BASE_URL}/cases`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      next: { revalidate: 60 },
    });
    if (res.ok) {
      return { data: await res.json(), isDemo: false };
    }
    throw new Error(`API responded with ${res.status}`);
  } catch (err) {
    if (isDemoMode()) {
      return { data: MOCK_CASES_SUMMARY, isDemo: true };
    }
    throw new ApiUnreachableError(API_BASE_URL, err);
  }
}

/**
 * Fetch full case definition.
 *
 * Throws `ApiUnreachableError` when the backend cannot be reached and demo
 * mode is off.
 */
export async function getCaseDetail(caseId: string): Promise<DemoResult<CaseDetail | null>> {
  try {
    const res = await fetch(`${API_BASE_URL}/cases/${caseId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      next: { revalidate: 60 },
    });
    if (res.ok) {
      return { data: await res.json(), isDemo: false };
    }
    throw new Error(`API responded with ${res.status}`);
  } catch (err) {
    if (isDemoMode()) {
      return { data: MOCK_CASE_DETAILS[caseId] || null, isDemo: true };
    }
    throw new ApiUnreachableError(API_BASE_URL, err);
  }
}

/**
 * A scientific refusal as the engine stated it. Every field except `message`
 * is optional because older API builds and the 501 path send less.
 */
export interface RefusalInfo {
  message: string;
  code?: string;
  stage?: string;
  remediation?: string | null;
  runId?: string;
  /**
   * `AnalysisError.detail`. The API's refusal body does not include it yet;
   * it is read when present so per-unit defects appear as soon as it does.
   */
  detail?: AlignmentRefusalDetail | Record<string, unknown>;
}

function refusalFrom(detail: Record<string, unknown>, fallback: string): RefusalInfo {
  const str = (k: string) => (typeof detail[k] === 'string' ? (detail[k] as string) : undefined);
  const inner = detail.detail;
  return {
    message: str('message') ?? fallback,
    code: str('code'),
    stage: str('stage'),
    remediation: str('remediation') ?? null,
    runId: str('run_id'),
    detail: inner && typeof inner === 'object' ? (inner as Record<string, unknown>) : undefined,
  };
}

/**
 * Run verification pipeline.
 */
export async function verifyCase(
  caseId: string,
  options: VerificationRequest = { synthetic: true, true_effect: 0.06, min_donors: 10, include_report: true }
): Promise<{
  success: boolean;
  data?: VerificationResponse;
  error?: string;
  isRefusal?: boolean;
  refusal?: RefusalInfo;
  isDemo?: boolean;
}> {
  try {
    const res = await fetch(`${API_BASE_URL}/cases/${caseId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
    });

    if (res.ok) {
      const data = await res.json();
      return { success: true, data };
    }

    const errJson = await res.json().catch(() => null);
    const detail = errJson?.detail;

    // 501 Not Implemented: observed-data access is refused, never silently served
    if (res.status === 501) {
      return {
        success: false,
        error: typeof detail === 'string' ? detail : 'Observed-data access is not yet implemented. Earth Engine reducer chain is planned for MVP.',
        isRefusal: true,
      };
    }

    if (res.status === 422 && typeof detail === 'object' && detail?.is_refusal) {
      const refusal = refusalFrom(detail, 'Verification was scientifically refused.');
      return {
        success: false,
        error: refusal.message,
        isRefusal: true,
        refusal,
      };
    }

    return {
      success: false,
      error: typeof detail === 'string' ? detail : (detail?.message || 'Verification request failed.'),
      isRefusal: Boolean(detail?.is_refusal),
    };
  } catch {
    // Backend unreachable. Only ever substitute a fixture when demo mode is
    // explicitly on, and always flag it as such — never as a successful run.
    if (isDemoMode() && options.synthetic) {
      const fixture = MOCK_VERIFICATION_RESULTS[caseId];
      if (fixture) {
        return { success: true, data: fixture.verification, isDemo: true };
      }
    }
    return {
      success: false,
      error: `Backend API is unreachable at ${API_BASE_URL}. No verification was executed.`,
      isRefusal: false,
    };
  }
}

/**
 * The engine-generated alignment refusal, for showing the refusal state in a
 * demo. `null` unless demo mode is explicitly on; never returned in place of
 * a real response.
 */
export function getRefusalFixture(caseId: string): RefusalInfo | null {
  if (!isDemoMode() || KARIBA_REFUSED_ALIGNMENT._generated.case_id !== caseId) {
    return null;
  }
  return {
    ...refusalFrom(KARIBA_REFUSED_ALIGNMENT.error_body.detail as unknown as Record<string, unknown>, ''),
    detail: KARIBA_REFUSED_ALIGNMENT.not_served_by_api.error_detail,
  };
}

/**
 * Get rich fixture visualization data for UI display (chart series, donors map, placebos, timeline).
 *
 * Returns `null` unless demo mode is explicitly enabled. Never substitutes
 * another case's fixture: a missing fixture for a known case id is `null`,
 * not a fallback to Kariba.
 */
export function getVisualizationFixture(caseId: string): VerificationFixtureData | null {
  if (!isDemoMode()) {
    return null;
  }
  return MOCK_VERIFICATION_RESULTS[caseId] || null;
}

/**
 * Fetch health and honest capability reporting.
 *
 * An unreachable health endpoint renders as unknown status, never as a
 * fabricated capability claim.
 */
export async function getHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // fall through to the honest "unreachable" representation below
  }
  return {
    status: 'unreachable',
    version: 'unknown',
    engine_version: 'unknown',
    contract_version: 'unknown',
    earth_observation_implemented: false,
    genai_narration_implemented: false,
    cases_available: 0,
    engine_capabilities: {},
  };
}

/**
 * ADR-011 donor-candidate-generation summary for a case.
 *
 * There is currently no HTTP endpoint serving this. `EarthEngineUnitConstruction`
 * (`packages/groundtruth/src/groundtruth/platform/units/generator.py`) raises
 * `DataUnavailableError` on every call — no candidate count has ever been
 * measured for any case. This returns the honest "nothing has been measured"
 * shape rather than inventing a value or a mock: every measurement field is
 * `null`, and `resultState` is `'not_started'`. When a real endpoint exists,
 * this function should be replaced with a `fetch` following the same
 * unreachable/refused/failed pattern as `getCaseDetail` and `verifyCase`
 * above — not extended with a demo-mode fixture fallback, since inventing
 * ADR-011 candidate counts would be fabricated scientific data regardless of
 * the demo flag.
 */
export function getDonorCandidateSummary(caseDetail: CaseDetail): DonorCandidateSummary {
  return {
    caseId: caseDetail.case_id,
    caseName: caseDetail.name,
    treatedEligibleAreaKm2: null,
    rungUsed: null,
    rungs: [],
    candidateCount: null,
    admittedDonorCount: null,
    exclusionsByCategory: null,
    resultState: 'not_started',
  };
}
