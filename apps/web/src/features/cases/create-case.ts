import { getApiBaseUrl } from '../../lib/api';
import { notifySessionExpired } from '../../lib/session-events';

export type CreateCaseResult =
  | { ok: true; caseId: string }
  | { ok: false; reason: 'unauthenticated' | 'forbidden' | 'rejected' | 'network'; message: string };

type Fetch = typeof globalThis.fetch;

/** FastAPI sends `detail` as a string, or as a list of {msg} objects for validation errors. */
function detailText(detail: unknown): string | null {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && typeof (d as { msg?: unknown }).msg === 'string' ? (d as { msg: string }).msg : null))
      .filter((m): m is string => Boolean(m));
    return msgs.length ? msgs.join('; ') : null;
  }
  if (detail && typeof detail === 'object' && typeof (detail as { message?: unknown }).message === 'string') {
    return (detail as { message: string }).message;
  }
  return null;
}

/**
 * POST /cases with the session cookie. Without `credentials: 'include'` the
 * browser drops the HttpOnly session cookie on a cross-origin call and the API
 * answers 401 even for a signed-in user.
 */
export async function createCase(payload: Record<string, unknown>, fetchImpl: Fetch = (...a) => globalThis.fetch(...a)): Promise<CreateCaseResult> {
  let res: Response;
  try {
    res = await fetchImpl(`${getApiBaseUrl()}/cases`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch {
    return { ok: false, reason: 'network', message: 'Network error: Unable to reach analysis service.' };
  }
  if (res.ok) {
    const data = await res.json().catch(() => null);
    const caseId = data && typeof data.case_id === 'string' ? data.case_id : null;
    if (caseId) return { ok: true, caseId };
    return { ok: false, reason: 'rejected', message: 'The server accepted the project but returned no case id.' };
  }
  const body = await res.json().catch(() => null);
  if (res.status === 401) {
    notifySessionExpired();
    return { ok: false, reason: 'unauthenticated', message: 'You are not signed in, or your session has expired. Sign in and try again.' };
  }
  if (res.status === 403) {
    return { ok: false, reason: 'forbidden', message: detailText(body?.detail) ?? 'Your account is not allowed to create projects.' };
  }
  return { ok: false, reason: 'rejected', message: detailText(body?.detail) ?? `Could not create project (HTTP ${res.status}).` };
}

