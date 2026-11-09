'use client';

import React, { useState } from 'react';
import { Button } from '../../components/ds';
import { getApiBaseUrl } from '../../lib/api';
import { fetchReportFile, saveBlob, type ReportFormat } from '../case/report/downloads';
import { dossierVisible, legacyReportsAvailable, type AccessLevel } from './model';
import styles from './projects.module.css';

type Status = { kind: 'idle' } | { kind: 'busy'; what: string } | { kind: 'done'; text: string } | { kind: 'error'; text: string };

/**
 * Downloads for a project. Monitoring reports use the legacy case export routes, so they exist only when
 * the project has a case_id. The dossier is owner/audit only. The API audits every download.
 */
export function ReportsView({ projectId, level, caseId }: { projectId: string; level: AccessLevel; caseId: string | null }) {
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const legacy = legacyReportsAvailable(caseId);
  const dossier = dossierVisible(level);

  async function legacyDownload(format: ReportFormat) {
    if (!caseId || status.kind === 'busy') return;
    setStatus({ kind: 'busy', what: format });
    const r = await fetchReportFile(caseId, format);
    if (!r.ok) return setStatus({ kind: 'error', text: r.message });
    saveBlob(r.blob, r.filename);
    setStatus({ kind: 'done', text: `Saved ${r.filename}.` });
  }

  async function dossierDownload() {
    if (status.kind === 'busy') return;
    setStatus({ kind: 'busy', what: 'dossier' });
    try {
      const res = await fetch(`${getApiBaseUrl()}/projects/${encodeURIComponent(projectId)}/export/dossier`, { credentials: 'include' });
      if (!res.ok) return setStatus({ kind: 'error', text: res.status === 403 ? 'Your access level does not allow the dossier.' : `The dossier could not be created (HTTP ${res.status}).` });
      saveBlob(await res.blob(), `${projectId}-dossier.zip`);
      setStatus({ kind: 'done', text: 'Saved the technical dossier.' });
    } catch {
      setStatus({ kind: 'error', text: 'The GroundTruth API could not be reached.' });
    }
  }

  const busy = status.kind === 'busy' ? status.what : null;
  const hint = !legacy ? <p className={styles.muted}>The monitoring report becomes available after a completed run.</p> : null;
  if (!legacy && !dossier) {
    return (
      <>
        <p className={styles.muted}>No reports are available for this project at your access level.</p>
        {hint}
      </>
    );
  }
  return (
    <div className={styles.section}>
      {legacy && (
        <div className={styles.section}>
          <h2>Monitoring report</h2>
          <div className={styles.actions}>
            <Button variant="primary" onClick={() => legacyDownload('pdf')} loading={busy === 'pdf'} disabled={busy !== null}>
              Download PDF
            </Button>
            <Button variant="secondary" onClick={() => legacyDownload('csv')} loading={busy === 'csv'} disabled={busy !== null}>
              Download CSV
            </Button>
          </div>
        </div>
      )}
      {hint}
      {dossier && (
        <div className={styles.section}>
          <h2>Technical dossier</h2>
          <p className={styles.muted}>A ZIP with limitations, readiness, evidence inventory, assessment, observations, climate, provenance and a checksum manifest, for audit.</p>
          <div className={styles.actions}>
            <Button variant="secondary" onClick={dossierDownload} loading={busy === 'dossier'} disabled={busy !== null}>
              Download dossier (ZIP)
            </Button>
          </div>
        </div>
      )}
      <p className={styles.muted}>Each download is recorded in the audit log.</p>
      {status.kind === 'error' && <p role="alert" className={styles.error}>{status.text}</p>}
      {status.kind === 'done' && <p role="status" className={styles.muted}>{status.text}</p>}
    </div>
  );
}
