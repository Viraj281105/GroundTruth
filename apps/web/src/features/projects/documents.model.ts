import type { Schemas } from '../../lib/api-client';

export type DocumentView = Schemas['DocumentView'];
export type DocumentStatus = DocumentView['status'];
export type DocumentListView = Schemas['DocumentListView'];
export type ExtractionView = Schemas['ExtractionView'];

export type Tone = 'neutral' | 'accent' | 'caution' | 'danger';

export interface StatusCopy {
  label: string;
  tone: Tone;
  /** Plain statement of how far processing went, never more. */
  plain: string;
}

/**
 * What each processing status means, in words for a non-specialist. "Uploaded" is stored, NOT processed;
 * extracted statements are text matches, never verified.
 */
export function statusCopy(status: DocumentStatus | string): StatusCopy {
  switch (status) {
    case 'uploaded':
      return { label: 'Stored, not processed', tone: 'neutral', plain: 'The file is stored and checksummed. Nothing has been read from it yet.' };
    case 'text_extracted':
      return {
        label: 'Text read, not verified',
        tone: 'accent',
        plain: 'The text was read and possible claims were found. They are text matches only: none has been checked against evidence.',
      };
    case 'extraction_unsupported':
      return { label: 'Stored, cannot be read', tone: 'caution', plain: 'The file is stored, but GroundTruth cannot read text from this kind of file yet.' };
    case 'extraction_failed':
      return { label: 'Stored, reading failed', tone: 'danger', plain: 'The file is stored, but reading its text failed.' };
    default:
      return { label: 'Unknown status', tone: 'caution', plain: 'The status of this document is not recognised.' };
  }
}

export function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return 'unknown size';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** First 12 hex characters of a checksum, or null when none is stored. */
export const shortSha = (sha: string | null | undefined): string | null => (sha ? sha.slice(0, 12) : null);

/** ".PDF" -> ".pdf"; "" when the name has no extension. */
export function extensionOf(filename: string): string {
  const i = filename.lastIndexOf('.');
  return i > 0 && i < filename.length - 1 ? filename.slice(i).toLowerCase() : '';
}

const normExt = (e: string) => (e.startsWith('.') ? e : `.${e}`).toLowerCase();

/** Client-side check against the limits the API reported. Returns a plain message, or null when the file may be sent. */
export function validateUpload(file: { name: string; size: number } | null | undefined, allowedExtensions: readonly string[], maxBytes: number): string | null {
  if (!file || !file.name) return 'Choose a file first.';
  const allowed = allowedExtensions.map(normExt);
  const ext = extensionOf(file.name);
  if (!ext || !allowed.includes(ext)) return `This file type is not accepted. Use one of: ${allowed.join(', ')}.`;
  if (file.size === 0) return 'The file is empty.';
  if (file.size > maxBytes) return `The file is ${formatBytes(file.size)}, which is over the ${formatBytes(maxBytes)} limit.`;
  return null;
}

interface ApiDetail {
  code?: unknown;
  message?: unknown;
  hint?: unknown;
}

/** The API's `{detail:{code,message,hint}}` shown as sent (message plus hint); status-based wording is the fallback. */
export function documentErrorMessage(status: number, body: unknown): string {
  const d = (body as { detail?: unknown } | null | undefined)?.detail;
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    const { message, hint } = d as ApiDetail;
    if (typeof message === 'string' && message) return typeof hint === 'string' && hint ? `${message} ${hint}` : message;
  }
  if (typeof d === 'string' && d) return d;
  switch (status) {
    case 0:
      return 'The GroundTruth API could not be reached. Nothing was changed.';
    case 401:
      return 'Your session has expired. Sign in again.';
    case 403:
      return 'Your access level does not allow this action.';
    case 404:
      return 'The document was not found, or you have no access to it.';
    case 413:
      return 'The file is larger than the upload limit.';
    case 415:
      return 'This file type is not accepted.';
    case 422:
      return 'The file was rejected.';
    case 409:
      return 'This is not available for this document.';
    default:
      return `The server could not complete the request (HTTP ${status}).`;
  }
}

export const allowedHint = (exts: readonly string[], maxBytes: number): string => `Accepted: ${exts.map(normExt).join(', ')}. Largest file: ${formatBytes(maxBytes)}.`;
