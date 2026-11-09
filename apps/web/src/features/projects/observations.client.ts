import { getApiBaseUrl } from '../../lib/api';
import { ingestionError, type IngestionList, type IngestionRequest, type IngestionView } from './observations.model';

type Fetch = typeof globalThis.fetch;
const defaultFetch: Fetch = (...a) => globalThis.fetch(...a);

export type IngestionOutcome<T> = { ok: true; data: T } | { ok: false; status: number; message: string; hint: string | null };

const base = (projectId: string) => `${getApiBaseUrl()}/projects/${encodeURIComponent(projectId)}/observations/ingestions`;

async function call<T>(url: string, init: RequestInit, fetchImpl: Fetch): Promise<IngestionOutcome<T>> {
  try {
    const res = await fetchImpl(url, { ...init, credentials: 'include' });
    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) return { ok: false, status: res.status, ...ingestionError(res.status, body) };
    return { ok: true, data: body as T };
  } catch {
    return { ok: false, status: 0, ...ingestionError(0, null) };
  }
}

export const fetchIngestions = (projectId: string, fetchImpl: Fetch = defaultFetch) => call<IngestionList>(base(projectId), {}, fetchImpl);

export const requestIngestion = (projectId: string, body: IngestionRequest, fetchImpl: Fetch = defaultFetch) =>
  call<IngestionView>(base(projectId), { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }, fetchImpl);

export const cancelIngestion = (projectId: string, id: string, fetchImpl: Fetch = defaultFetch) =>
  call<IngestionView>(`${base(projectId)}/${encodeURIComponent(id)}/cancel`, { method: 'POST' }, fetchImpl);
