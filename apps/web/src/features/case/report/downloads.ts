import { getPublicApiUrl } from '../../../lib/api';
import { notifySessionExpired } from '../../../lib/session-events';

export type ReportFormat = 'pdf' | 'csv';

export type DownloadFailureKind = 'unauthenticated' | 'forbidden' | 'not_found' | 'server' | 'network' | 'invalid_file';

export type DownloadResult =
  | { ok: true; blob: Blob; filename: string; bytes: number; contentType: string; dataMode: string | null }
  | { ok: false; kind: DownloadFailureKind; message: string };

type Fetch = typeof globalThis.fetch;

const MIME: Record<ReportFormat, string> = { pdf: 'application/pdf', csv: 'text/csv' };

export function exportUrl(caseId: string, format: ReportFormat): string {
  return `${getPublicApiUrl()}/cases/${encodeURIComponent(caseId)}/export/${format}`;
}

/** Filename from a Content-Disposition header, falling back to a predictable name. */
export function filenameFrom(disposition: string | null, caseId: string, format: ReportFormat): string {
  const m = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const raw = m?.[1]?.trim();
  const safe = raw ? raw.replace(/[\\/]/g, '_') : '';
  return safe || `${caseId}-${format === 'pdf' ? 'report' : 'evidence'}.${format}`;
}

/**
 * A 200 is not a file. PDF bytes must start with `%PDF-` and contain an EOF
 * marker; a CSV must be text with a header row and at least one data row.
 * Returns a problem description, or null when the content is what it claims.
 */
export function validateExport(format: ReportFormat, bytes: Uint8Array): string | null {
  if (bytes.byteLength === 0) return 'The server returned an empty file.';
  if (format === 'pdf') {
    const head = String.fromCharCode(...bytes.slice(0, 5));
    if (head !== '%PDF-') return 'The server returned something that is not a PDF.';
    const tail = new TextDecoder('latin1').decode(bytes.slice(Math.max(0, bytes.byteLength - 1024)));
    if (!tail.includes('%%EOF')) return 'The PDF is incomplete (no end-of-file marker).';
    return null;
  }
  const text = new TextDecoder('utf-8').decode(bytes);
  if (text.trimStart().startsWith('<')) return 'The server returned a web page instead of a CSV.';
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length < 2) return 'The CSV has no data rows.';
  return null;
}

/** Fetch one export with the session cookie and verify the file before handing it back. */
export async function fetchReportFile(
  caseId: string,
  format: ReportFormat,
  fetchImpl: Fetch = (...a) => globalThis.fetch(...a),
): Promise<DownloadResult> {
  let res: Response;
  try {
    res = await fetchImpl(exportUrl(caseId, format), { method: 'GET', credentials: 'include', headers: { Accept: MIME[format] } });
  } catch {
    return { ok: false, kind: 'network', message: 'The analysis service could not be reached. Nothing was downloaded.' };
  }
  if (res.status === 401) {
    notifySessionExpired();
    return { ok: false, kind: 'unauthenticated', message: 'You are not signed in, or your session expired. Sign in and try again.' };
  }
  if (res.status === 403) return { ok: false, kind: 'forbidden', message: 'Your account is not allowed to export this report.' };
  if (res.status === 404) return { ok: false, kind: 'not_found', message: 'This case has no export available.' };
  if (!res.ok) {
    return { ok: false, kind: 'server', message: `The export failed on the server (HTTP ${res.status}). Nothing was downloaded.` };
  }
  const buf = new Uint8Array(await res.arrayBuffer());
  const problem = validateExport(format, buf);
  if (problem) return { ok: false, kind: 'invalid_file', message: `${problem} Nothing was saved.` };
  return {
    ok: true,
    blob: new Blob([buf], { type: MIME[format] }),
    filename: filenameFrom(res.headers.get('Content-Disposition'), caseId, format),
    bytes: buf.byteLength,
    contentType: res.headers.get('Content-Type') ?? MIME[format],
    dataMode: res.headers.get('X-GroundTruth-Data-Mode'),
  };
}

/** Hand a verified blob to the browser as a download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

