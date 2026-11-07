import { ApiUnreachableError, getCaseDetail, API_BASE_URL } from '../../../lib/api';
import type { CaseDetail } from '../../../lib/types';

export type CaseLoad =
  | { status: 'ok'; detail: CaseDetail; isDemo: boolean }
  | { status: 'not_found' }
  | { status: 'unreachable'; apiBaseUrl: string };

/**
 * `getCaseDetail` wraps every failure, including a plain 404, in
 * ApiUnreachableError with the original error as `cause`. A 404 means the case
 * does not exist; anything else means the service could not be used.
 */
export function classifyLoadError(err: unknown): 'not_found' | 'unreachable' {
  const cause = err instanceof Error ? (err as { cause?: unknown }).cause : undefined;
  if (cause instanceof Error && /responded with 404/.test(cause.message)) return 'not_found';
  return 'unreachable';
}

export async function loadCase(caseId: string): Promise<CaseLoad> {
  try {
    const { data, isDemo } = await getCaseDetail(caseId);
    if (!data) return { status: 'not_found' };
    return { status: 'ok', detail: data, isDemo };
  } catch (err) {
    if (classifyLoadError(err) === 'not_found') return { status: 'not_found' };
    return { status: 'unreachable', apiBaseUrl: err instanceof ApiUnreachableError ? err.apiBaseUrl : API_BASE_URL };
  }
}
