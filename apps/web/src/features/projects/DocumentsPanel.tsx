'use client';

import React, { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button, Chip, Dialog } from '../../components/ds';
import { saveBlob } from '../case/report/downloads';
import { deleteDocument, fetchDocumentBlob, fetchExtraction, uploadDocument } from './documents.client';
import { allowedHint, formatBytes, validateUpload, type DocumentView, type ExtractionView } from './documents.model';
import { DocumentsTable } from './DocumentsTable';
import styles from './documents.module.css';

type Msg = { kind: 'ok' | 'error'; text: string } | null;

export interface DocumentsPanelProps {
  projectId: string;
  documents: DocumentView[];
  maxBytes: number;
  allowedExtensions: string[];
  /** Owner-level access AND an org role that may edit. */
  canEdit: boolean;
  /** Plain-language reason shown instead of the controls when canEdit is false. */
  blockedReason: string | null;
}

export function DocumentsPanel({ projectId, documents, maxBytes, allowedExtensions, canEdit, blockedReason }: DocumentsPanelProps) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const [confirm, setConfirm] = useState<DocumentView | null>(null);
  const [view, setView] = useState<{ doc: DocumentView; result: { ok: true; data: ExtractionView } | { ok: false; message: string } | null } | null>(null);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    if (uploading) return;
    const file = input.current?.files?.[0] ?? null;
    const problem = validateUpload(file, allowedExtensions, maxBytes);
    if (problem || !file) return setMsg({ kind: 'error', text: problem ?? 'Choose a file first.' });
    setUploading(true);
    setMsg(null);
    const r = await uploadDocument(projectId, file);
    setUploading(false);
    if (!r.ok) return setMsg({ kind: 'error', text: r.message });
    if (input.current) input.current.value = '';
    setMsg({ kind: 'ok', text: `Uploaded ${r.data.filename} (${formatBytes(r.data.size_bytes)}). It is stored; see its status below for what has been read.` });
    router.refresh();
  }

  async function onDownload(d: DocumentView) {
    setBusyId(d.id);
    setMsg(null);
    const r = await fetchDocumentBlob(projectId, d.id);
    setBusyId(null);
    if (!r.ok) return setMsg({ kind: 'error', text: r.message });
    saveBlob(r.data, d.filename);
    setMsg({ kind: 'ok', text: `Saved ${d.filename}.` });
  }

  async function onConfirmDelete() {
    const d = confirm;
    if (!d) return;
    setConfirm(null);
    setBusyId(d.id);
    const r = await deleteDocument(projectId, d.id);
    setBusyId(null);
    if (!r.ok) return setMsg({ kind: 'error', text: r.message });
    setMsg({ kind: 'ok', text: `Deleted ${d.filename}.` });
    router.refresh();
  }

  async function onView(d: DocumentView) {
    setView({ doc: d, result: null });
    const r = await fetchExtraction(projectId, d.id);
    setView({ doc: d, result: r.ok ? { ok: true, data: r.data } : { ok: false, message: r.message } });
  }

  return (
    <section className={styles.section} aria-label="Project documents">
      <h2 className={styles.h2}>Project documents</h2>
      <p className={styles.muted}>
        Uploaded documents are stored with a checksum so they cannot be changed unnoticed. A stored document is not evidence of any claim until it has been checked.
      </p>

      {canEdit ? (
        <form className={styles.uploadForm} onSubmit={onUpload} aria-label="Upload a document">
          <label>
            <span className={styles.muted}>Choose a document. {allowedHint(allowedExtensions, maxBytes)}</span>
            <br />
            <input ref={input} type="file" name="file" accept={allowedExtensions.map((x) => (x.startsWith('.') ? x : `.${x}`)).join(',')} disabled={uploading} />
          </label>
          <Button type="submit" loading={uploading}>
            Upload document
          </Button>
        </form>
      ) : (
        <p className={styles.muted} data-upload-blocked>
          {blockedReason ?? 'You cannot upload documents to this project.'}
        </p>
      )}

      {msg?.kind === 'error' && (
        <p role="alert" className={styles.error}>
          {msg.text}
        </p>
      )}
      {msg?.kind === 'ok' && (
        <p role="status" className={styles.ok}>
          {msg.text}
        </p>
      )}

      <DocumentsTable documents={documents} canDelete={canEdit} busyId={busyId} onDownload={onDownload} onDelete={setConfirm} onView={onView} />

      <Dialog open={confirm !== null} onClose={() => setConfirm(null)} title="Delete this document?">
        <p>
          {confirm?.filename} will be removed from this project. This cannot be undone. The deletion is recorded in the audit log.
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button variant="danger" onClick={onConfirmDelete}>
            Delete document
          </Button>
          <Button variant="secondary" onClick={() => setConfirm(null)}>
            Keep it
          </Button>
        </div>
      </Dialog>

      <Dialog open={view !== null} onClose={() => setView(null)} title={view ? `Extracted statements: ${view.doc.filename}` : 'Extracted statements'}>
        <Chip tone="caution">Candidates, not verified</Chip>
        {view?.result === null && <p className={styles.muted}>Loading…</p>}
        {view?.result && !view.result.ok && <p role="alert" className={styles.error}>{view.result.message}</p>}
        {view?.result?.ok && (
          <>
            <p className={styles.muted}>{view.result.data.note}</p>
            {view.result.data.candidates.length === 0 ? (
              <p>No possible claims were found in the text.</p>
            ) : (
              <ul className={styles.candidates}>
                {view.result.data.candidates.map((c, i) => (
                  <li key={`${c.start ?? i}-${i}`}>
                    <strong>{c.kind}</strong>
                    {c.value !== null && c.value !== undefined ? `: ${c.value}${c.unit ? ` ${c.unit}` : ''}` : ''}
                    {c.quote && <p className={styles.quote}>&ldquo;{c.quote}&rdquo;</p>}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Dialog>
    </section>
  );
}
