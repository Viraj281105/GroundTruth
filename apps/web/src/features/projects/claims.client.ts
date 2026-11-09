import { getApiBaseUrl } from '../../lib/api';
import { apiDetail, claimErrorMessage, type ClaimCreateBody, type ClaimListView, type ClaimPatchBody, type ProjectClaimView } from './claims.model';

type Fetch = typeof globalThis.fetch;
const defaultFetch: Fetch = (...a) => globalThis.fetch(...a);

export type Outcome<T> = { ok: true; data: T } | { ok: false; status: number; message: string; code: string | null };

const base = (projectId: string) => `${getApiBaseUrl()}/projects/${encodeURIComponent(projectId)}/claims`;
const json = { 'content-type': 'application/json' };

async function body(res: Response): Promise<unknown> {
  return res.json().catch(() => null);
}

async function send<T>(url: string, init: RequestInit, fetchImpl: Fetch, parse: boolean): Promise<Outcome<T>> {
  try {
    const res = await fetchImpl(url, { ...init, credentials: 'include' });
    if (!res.ok) {
      const b = await body(res);
      return { ok: false, status: res.status, message: claimErrorMessage(res.status, b), code: apiDetail(b).code };
    }
    return { ok: true, data: (parse ? await body(res) : null) as T };
  } catch {
    return { ok: false, status: 0, message: claimErrorMessage(0, null), code: null };
  }
}

export const listClaims = (projectId: string, fetchImpl: Fetch = defaultFetch) => send<ClaimListView>(base(projectId), {}, fetchImpl, true);

/** Promote an extracted statement (document_id + start + end) or add a typed claim (statement_text + kind). */
export const createClaim = (projectId: string, payload: ClaimCreateBody, fetchImpl: Fetch = defaultFetch) =>
  send<ProjectClaimView>(base(projectId), { method: 'POST', headers: json, body: JSON.stringify(payload) }, fetchImpl, true);

export const patchClaim = (projectId: string, claimId: string, payload: ClaimPatchBody, fetchImpl: Fetch = defaultFetch) =>
  send<ProjectClaimView>(`${base(projectId)}/${encodeURIComponent(claimId)}`, { method: 'PATCH', headers: json, body: JSON.stringify(payload) }, fetchImpl, true);

/** Withdraws (soft-removes) a claim. */
export const withdrawClaim = (projectId: string, claimId: string, fetchImpl: Fetch = defaultFetch) =>
  send<null>(`${base(projectId)}/${encodeURIComponent(claimId)}`, { method: 'DELETE' }, fetchImpl, false);
