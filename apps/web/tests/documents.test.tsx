import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { deleteDocument, fetchExtraction, uploadDocument } from '../src/features/projects/documents.client';
import { documentErrorMessage, extensionOf, formatBytes, statusCopy, validateUpload, type DocumentView } from '../src/features/projects/documents.model';
import { DocumentsTable } from '../src/features/projects/DocumentsTable';
import { EvidenceGuidance } from '../src/features/projects/EvidenceGuidance';
import { canEditProject, editBlockedReason } from '../src/features/projects/model';

const doc = (over: Partial<DocumentView> = {}): DocumentView => ({
  id: 'd1',
  filename: 'design.txt',
  content_type: 'text/plain',
  size_bytes: 2048,
  sha256: 'abcdef0123456789abcdef',
  uploaded_at: '2026-11-01T10:00:00Z',
  status: 'uploaded',
  status_detail: null,
  extracted_claims_count: null,
  project_id: 'p1',
  uploaded_by: 'u1',
  extracted_text_chars: null,
  processing_note: 'Stored and checksummed.',
  ...over,
});

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('validateUpload', () => {
  const allowed = ['.pdf', '.txt', '.md', '.csv'];
  it('accepts an allowed type within the limit (case-insensitive)', () => {
    expect(validateUpload({ name: 'Plan.PDF', size: 100 }, allowed, 1000)).toBeNull();
    expect(validateUpload({ name: 'a.md', size: 1000 }, ['md'], 1000)).toBeNull();
  });
  it('rejects a missing file, a wrong extension, an empty file and an oversize file with plain messages', () => {
    expect(validateUpload(null, allowed, 1000)).toBe('Choose a file first.');
    expect(validateUpload({ name: 'x.exe', size: 5 }, allowed, 1000)).toContain('not accepted');
    expect(validateUpload({ name: 'noext', size: 5 }, allowed, 1000)).toContain('not accepted');
    expect(validateUpload({ name: 'a.txt', size: 0 }, allowed, 1000)).toBe('The file is empty.');
    expect(validateUpload({ name: 'a.txt', size: 2 * 1024 * 1024 }, allowed, 1024 * 1024)).toContain('over the 1.0 MB limit');
  });
  it('helpers', () => {
    expect(extensionOf('a.b.CSV')).toBe('.csv');
    expect(extensionOf('.hidden')).toBe('');
    expect(formatBytes(1536)).toBe('1.5 KB');
  });
});

describe('statusCopy', () => {
  it('uploaded means stored, not processed', () => {
    expect(statusCopy('uploaded').label).toBe('Stored, not processed');
  });
  it('text_extracted says candidates are not verified', () => {
    const c = statusCopy('text_extracted');
    expect(c.label).toContain('not verified');
    expect(c.plain).toContain('none has been checked');
  });
  it('unsupported and failed are plain', () => {
    expect(statusCopy('extraction_unsupported').plain).toContain('cannot read');
    expect(statusCopy('extraction_failed').label).toContain('failed');
  });
});

describe('documentErrorMessage', () => {
  it('shows the API message plus hint as sent', () => {
    expect(documentErrorMessage(415, { detail: { code: 'unsupported_type', message: 'That file type is not accepted.', hint: 'Use .pdf, .txt, .md or .csv.' } })).toBe(
      'That file type is not accepted. Use .pdf, .txt, .md or .csv.',
    );
  });
  it('falls back to status wording', () => {
    expect(documentErrorMessage(403, null)).toContain('does not allow');
    expect(documentErrorMessage(0, null)).toContain('could not be reached');
  });
});

describe('client calls', () => {
  it('upload posts multipart with credentials and returns the document', async () => {
    const f = vi.fn().mockResolvedValue(res(201, doc()));
    const file = new File(['hello'], 'a.txt', { type: 'text/plain' });
    const r = await uploadDocument('p1', file, f as unknown as typeof fetch);
    expect(r.ok).toBe(true);
    const [url, init] = f.mock.calls[0]!;
    expect(String(url)).toMatch(/\/projects\/p1\/documents$/);
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    expect((init.body as FormData).get('file')).toBeInstanceOf(File);
  });
  it('upload surfaces the API error and a network failure', async () => {
    const bad = vi.fn().mockResolvedValue(res(413, { detail: { code: 'too_large', message: 'File too large.', hint: 'Max 10 MB.' } }));
    expect(await uploadDocument('p1', new File(['x'], 'a.txt'), bad as unknown as typeof fetch)).toEqual({ ok: false, status: 413, message: 'File too large. Max 10 MB.' });
    const down = vi.fn().mockRejectedValue(new TypeError('x'));
    const r = await uploadDocument('p1', new File(['x'], 'a.txt'), down as unknown as typeof fetch);
    expect(r.ok).toBe(false);
  });
  it('delete accepts 204; extraction 409 is an error with the API message', async () => {
    expect((await deleteDocument('p1', 'd1', vi.fn().mockResolvedValue(new Response(null, { status: 204 })) as unknown as typeof fetch)).ok).toBe(true);
    const r = await fetchExtraction('p1', 'd1', vi.fn().mockResolvedValue(res(409, { detail: { code: 'extraction_not_available', message: 'No text was extracted.', hint: null } })) as unknown as typeof fetch);
    expect(r).toEqual({ ok: false, status: 409, message: 'No text was extracted.' });
  });
});

describe('permissions', () => {
  it('only owner-level access with an editing role may change documents', () => {
    expect(canEditProject('owner', 'member')).toBe(true);
    expect(canEditProject('owner', 'viewer')).toBe(false);
    expect(canEditProject('audit', 'owner')).toBe(false);
    expect(editBlockedReason('view', 'owner')).toContain('another organization');
    expect(editBlockedReason('owner', 'viewer')).toContain('read-only');
    expect(editBlockedReason('owner', 'admin')).toBeNull();
  });
});

describe('DocumentsTable', () => {
  it('empty state when nothing is uploaded', () => {
    expect(renderToStaticMarkup(<DocumentsTable documents={[]} canDelete />)).toContain('No documents uploaded yet');
  });
  it('rows show name, size, short checksum, status copy and no delete for non-owners', () => {
    const rows = [doc(), doc({ id: 'd2', filename: 'n.md', status: 'text_extracted', extracted_claims_count: 2 })];
    const m = renderToStaticMarkup(<DocumentsTable documents={rows} canDelete={false} />);
    expect(m).toContain('design.txt');
    expect(m).toContain('2.0 KB');
    expect(m).toContain('abcdef012345');
    expect(m).toContain('>abcdef012345<');
    expect(m).toContain('Stored, not processed');
    expect(m).toContain('View extracted statements');
    expect(m).toContain('2 possible claims found (not verified)');
    expect(m).not.toContain('>Delete<');
    expect(renderToStaticMarkup(<DocumentsTable documents={rows} canDelete />)).toContain('>Delete<');
  });
});

describe('EvidenceGuidance', () => {
  it('shows the ingestion message, missing evidence and next steps from the API', () => {
    const m = renderToStaticMarkup(
      <EvidenceGuidance inventory={{ missing_evidence: ['No satellite observations are stored.'], next_steps: ['Upload a project document.'], observation_ingestion: { available: false, message: 'Satellite ingestion is not available for projects.' } }} />,
    );
    expect(m).toContain('Satellite data cannot be added here');
    expect(m).toContain('Satellite ingestion is not available for projects.');
    expect(m).toContain('No satellite observations are stored.');
    expect(m).toContain('Upload a project document.');
  });
  it('renders nothing when the API gave nothing', () => {
    expect(renderToStaticMarkup(<EvidenceGuidance inventory={{ missing_evidence: [], next_steps: [], observation_ingestion: null }} />)).toBe('');
  });
});
