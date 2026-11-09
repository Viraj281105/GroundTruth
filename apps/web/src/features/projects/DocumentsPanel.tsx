'use client';

import React, { useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button, Chip, Dialog } from '../../components/ds';
import { saveBlob } from '../case/report/downloads';
import { deleteDocument, fetchDocumentBlob, fetchExtraction, uploadDocument } from './documents.client';
import { allowedHint, formatBytes, validateUpload, type DocumentView, type ExtractionView } from './documents.model';
import { DocumentsTable } from './DocumentsTable';
import { CandidateList, candidateKey } from './CandidateList';
import { ClaimForm } from './ClaimForm';
import { createClaim } from './claims.client';
import { formFromCandidate, type ClaimCandidate, type ClaimListView, type ProjectClaimView } from './claims.model';
import styles from './documents.module.css';
import claimStyles from './claims.module.css';

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
  /** The project's claims and claim types. Null when they could not be loaded. */
  claimsData?: ClaimListView | null;
  /** Link to the Verification page, where claims are matched against the evidence. */
  verificationHref?: string;
}

export function DocumentsPanel({ projectId, documents, maxBytes, allowedExtensions, canEdit, blockedReason, claimsData = null, verificationHref = '../verification' }: DocumentsPanelProps) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<Msg>(null);
  const [confirm, setConfirm] = useState<DocumentView | null>(null);
  const [view, setView] = useState<{ doc: DocumentView; result: { ok: true; data: ExtractionView } | { ok: false; message: string } | null } | null>(null);

  const [reviewing, setReviewing] = useState<ClaimCandidate | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [created, setCreated] = useState<ProjectClaimView[]>([]);
  const [justAdded, setJustAdded] = useState<string[]>([]);
  const claimsNow = claimsData ? [...claimsData.claims, ...created] : null;

  function closeView() {
    setView(null);
    setReviewing(null);
    setAddError(null);
  }

  async function onAddClaim(docId: string, c: ClaimCandidate, fields: { statement_text: string; kind: string; value: number | null; unit: string | null; period: string | null }) {
    setAdding(true);
    setAddError(null);
    const r = await createClaim(projectId, { document_id: docId, start: c.start, end: c.end, ...fields });
    setAdding(false);
    if (!r.ok) return setAddError(r.message);
    setCreated((x) => [...x, r.data]);
    setJustAdded((x) => [...x, `${docId}:${candidateKey(c)}`]);
    setReviewing(null);
    router.refresh();
  }

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

      <Dialog open={view !== null} onClose={closeView} title={view ? `Extracted statements: ${view.doc.filename}` : 'Extracted statements'}>
        <Chip tone="caution">Candidates, not verified</Chip>
        {view?.result === null && <p className={styles.muted}>Loading…</p>}
        {view?.result && !view.result.ok && <p role="alert" className={styles.error}>{view.result.message}</p>}
        {view?.result?.ok && (
          <>
            <p className={styles.muted}>{view.result.data.note}</p>
            {reviewing && claimsData ? (
              <ClaimForm
                key={candidateKey(reviewing)}
                idPrefix="promote"
                initial={formFromCandidate(reviewing)}
                kinds={claimsData.kinds}
                submitLabel="Add as claim"
                busy={adding}
                error={addError}
                onCancel={() => {
                  setReviewing(null);
                  setAddError(null);
                }}
                onSubmit={(fields) => onAddClaim(view.doc.id, reviewing, fields)}
                intro={
                  <div className={claimStyles.original}>
                    <p>
                      The document said: <em>&ldquo;{reviewing.quote ?? ''}&rdquo;</em>
                    </p>
                    <p>Check the number and wording. If you change them, the claim is tested as you corrected it, and the original wording is kept beside it. Adding a claim does not verify it.</p>
                  </div>
                }
              />
            ) : view.result.data.candidates.length === 0 ? (
              <p>No possible claims were found in the text.</p>
            ) : (
              <CandidateList
                documentId={view.doc.id}
                candidates={view.result.data.candidates}
                claims={claimsNow}
                kinds={claimsData?.kinds ?? []}
                canEdit={canEdit}
                blockedReason={blockedReason}
                justAdded={justAdded.filter((k) => k.startsWith(`${view.doc.id}:`)).map((k) => k.slice(view.doc.id.length + 1))}
                verificationHref={verificationHref}
                onReview={(c) => {
                  setAddError(null);
                  setReviewing(c);
                }}
              />
            )}
          </>
        )}
      </Dialog>
    </section>
  );
}
