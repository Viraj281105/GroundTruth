import { getApiBaseUrl } from '../../lib/api';
import { documentErrorMessage, type DocumentView, type ExtractionView } from './documents.model';

type Fetch = typeof globalThis.fetch;
const defaultFetch: Fetch = (...a) => globalThis.fetch(...a);

export type Outcome<T> = { ok: true; data: T } | { ok: false; status: number; message: string };

const base = (projectId: string) => `${getApiBaseUrl()}/projects/${encodeURIComponent(projectId)}/documents`;

async function body(res: Response): Promise<unknown> {
  return res.json().catch(() => null);
}

/** POST multipart field `file`. The browser sets Origin and the multipart boundary; the session cookie goes with it. */
export async function uploadDocument(projectId: string, file: File, fetchImpl: Fetch = defaultFetch): Promise<Outcome<DocumentView>> {
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetchImpl(base(projectId), { method: 'POST', body: form, credentials: 'include' });
    const b = await body(res);
    if (!res.ok) return { ok: false, status: res.status, message: documentErrorMessage(res.status, b) };
    return { ok: true, data: b as DocumentView };
  } catch {
    return { ok: false, status: 0, message: documentErrorMessage(0, null) };
  }
}

export async function deleteDocument(projectId: string, docId: string, fetchImpl: Fetch = defaultFetch): Promise<Outcome<null>> {
  try {
    const res = await fetchImpl(`${base(projectId)}/${encodeURIComponent(docId)}`, { method: 'DELETE', credentials: 'include' });
    if (res.status === 204 || res.ok) return { ok: true, data: null };
    return { ok: false, status: res.status, message: documentErrorMessage(res.status, await body(res)) };
  } catch {
    return { ok: false, status: 0, message: documentErrorMessage(0, null) };
  }
}

export async function fetchExtraction(projectId: string, docId: string, fetchImpl: Fetch = defaultFetch): Promise<Outcome<ExtractionView>> {
  try {
    const res = await fetchImpl(`${base(projectId)}/${encodeURIComponent(docId)}/extraction`, { credentials: 'include' });
    const b = await body(res);
    if (!res.ok) return { ok: false, status: res.status, message: documentErrorMessage(res.status, b) };
    return { ok: true, data: b as ExtractionView };
  } catch {
    return { ok: false, status: 0, message: documentErrorMessage(0, null) };
  }
}

/** Fetch with the session cookie, then the caller hands the blob to the browser (saveBlob). */
export async function fetchDocumentBlob(projectId: string, docId: string, fetchImpl: Fetch = defaultFetch): Promise<Outcome<Blob>> {
  try {
    const res = await fetchImpl(`${base(projectId)}/${encodeURIComponent(docId)}/download`, { credentials: 'include' });
    if (!res.ok) return { ok: false, status: res.status, message: documentErrorMessage(res.status, await body(res)) };
    return { ok: true, data: await res.blob() };
  } catch {
    return { ok: false, status: 0, message: documentErrorMessage(0, null) };
  }
}
