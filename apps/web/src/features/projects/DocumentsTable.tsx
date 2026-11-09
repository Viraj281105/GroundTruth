import React from 'react';
import { Button, Chip, EmptyState } from '../../components/ds';
import { formatBytes, shortSha, statusCopy, type DocumentView } from './documents.model';
import styles from './documents.module.css';

export interface DocumentsTableProps {
  documents: readonly DocumentView[];
  canDelete: boolean;
  busyId?: string | null;
  onDownload?: (d: DocumentView) => void;
  onDelete?: (d: DocumentView) => void;
  onView?: (d: DocumentView) => void;
}

const when = (iso: string) => {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? iso : new Date(t).toISOString().slice(0, 16).replace('T', ' ') + ' UTC';
};

/** The project's uploaded documents. Status wording says how far processing went, never more. */
export function DocumentsTable({ documents, canDelete, busyId = null, onDownload, onDelete, onView }: DocumentsTableProps) {
  if (documents.length === 0) {
    return <EmptyState title="No documents uploaded yet" body="Upload a project document (for example a design document or monitoring report) to store it with this project." />;
  }
  return (
    <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Uploaded documents, scrollable">
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Name</th>
            <th>Size</th>
            <th>Uploaded</th>
            <th>Checksum (SHA-256)</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => {
            const s = statusCopy(d.status);
            const sha = shortSha(d.sha256);
            const busy = busyId === d.id;
            return (
              <tr key={d.id} data-doc-status={d.status}>
                <td>{d.filename}</td>
                <td>{formatBytes(d.size_bytes)}</td>
                <td>{when(d.uploaded_at)}</td>
                <td>{sha ? <code title={d.sha256 ?? undefined}>{sha}</code> : <span className={styles.muted}>none stored</span>}</td>
                <td>
                  <Chip tone={s.tone === 'accent' ? 'accent' : s.tone === 'danger' ? 'danger' : s.tone === 'caution' ? 'caution' : 'neutral'}>{s.label}</Chip>
                  <p className={styles.statusNote}>{d.processing_note || s.plain}</p>
                  {d.status_detail && <p className={styles.statusNote}>{d.status_detail}</p>}
                  {d.status === 'text_extracted' && typeof d.extracted_claims_count === 'number' && (
                    <p className={styles.statusNote}>
                      {d.extracted_claims_count} possible claim{d.extracted_claims_count === 1 ? '' : 's'} found (not verified).
                    </p>
                  )}
                </td>
                <td>
                  <div className={styles.rowActions}>
                    <Button size="sm" variant="secondary" onClick={() => onDownload?.(d)} disabled={busy}>
                      Download
                    </Button>
                    {d.status === 'text_extracted' && (
                      <Button size="sm" variant="ghost" onClick={() => onView?.(d)} disabled={busy}>
                        View extracted statements
                      </Button>
                    )}
                    {canDelete && (
                      <Button size="sm" variant="danger" onClick={() => onDelete?.(d)} disabled={busy}>
                        Delete
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
