import { createApiClient, type ApiClient, type Schemas } from '../../lib/api-client';

export type ClaimsResponse = Schemas['ClaimsResponse'];
export const MAX_TEXT_CHARS = 200_000;

export type AnalyzeResult =
  | { kind: 'ok'; data: ClaimsResponse }
  | { kind: 'rejected'; status: number; message: string }
  | { kind: 'unreachable' };

/** POST /claims/analyze. A network failure is `unreachable`; it never yields invented results. */
export async function analyzeClaims(text: string, caseId: string | null, client: ApiClient = createApiClient()): Promise<AnalyzeResult> {
  try {
    const { data, error, response } = await client.POST('/claims/analyze', { body: { text, case_id: caseId } });
    if (data) return { kind: 'ok', data };
    return { kind: 'rejected', status: response.status, message: describeError(error) };
  } catch {
    return { kind: 'unreachable' };
  }
}

function describeError(error: unknown): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) return String((detail[0] as { msg?: unknown }).msg ?? 'Invalid request');
  return 'The request was not accepted.';
}
