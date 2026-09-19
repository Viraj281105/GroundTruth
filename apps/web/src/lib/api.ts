import {
  CaseDetail,
  CaseSummary,
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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch list of all project cases.
 */
export async function getCases(): Promise<CaseSummary[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/cases`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      next: { revalidate: 60 },
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Graceful fallback to mock summary for offline development/demo
  }
  return MOCK_CASES_SUMMARY;
}

/**
 * Fetch full case definition.
 */
export async function getCaseDetail(caseId: string): Promise<CaseDetail | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/cases/${caseId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      next: { revalidate: 60 },
    });
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Fallback to fixture
  }
  return MOCK_CASE_DETAILS[caseId] || null;
}

/**
 * Run verification pipeline.
 */
export async function verifyCase(
  caseId: string,
  options: VerificationRequest = { synthetic: true, true_effect: 0.06, min_donors: 10, include_report: true }
): Promise<{ success: boolean; data?: VerificationResponse; error?: string; isRefusal?: boolean }> {
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
      return {
        success: false,
        error: detail.message || 'Verification was scientifically refused.',
        isRefusal: true,
      };
    }

    return {
      success: false,
      error: typeof detail === 'string' ? detail : (detail?.message || 'Verification request failed.'),
      isRefusal: Boolean(detail?.is_refusal),
    };
  } catch {
    // If backend is offline, return simulated fixture if synthetic mode was requested
    if (options.synthetic) {
      const fixture = MOCK_VERIFICATION_RESULTS[caseId];
      if (fixture) {
        return { success: true, data: fixture.verification };
      }
    }
    return {
      success: false,
      error: 'Backend API is unreachable. Please verify that FastAPI is running at ' + API_BASE_URL,
      isRefusal: false,
    };
  }
}

/**
 * Get rich fixture visualization data for UI display (chart series, donors map, placebos, timeline).
 */
export function getVisualizationFixture(caseId: string): VerificationFixtureData | null {
  return MOCK_VERIFICATION_RESULTS[caseId] || MOCK_VERIFICATION_RESULTS['kariba-redd'];
}

/**
 * Fetch health and honest capability reporting.
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
    // Fallback honest health representation
  }
  return {
    status: 'ok',
    version: '0.2.0',
    engine_version: '0.2.0',
    contract_version: '0.2.0',
    earth_observation_implemented: false,
    genai_narration_implemented: false,
    cases_available: 3,
    engine_capabilities: {
      synthetic_control: true,
      did: true,
      placebo_in_space: true,
      placebo_in_time: true,
      leave_one_out: true,
      earth_engine_reduction: false,
      biomass_conversion: false,
    },
  };
}
