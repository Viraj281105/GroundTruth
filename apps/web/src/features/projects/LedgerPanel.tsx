import React from 'react';
import { Chip } from '../../components/ds/Chip';
import { fetched } from './server';
import { serverApi } from '../../lib/server-api';
import { formatUtc, ledgerStatusText, shortHash } from './ledger.model';
import { VerifyReportForm } from './VerifyReportForm';
import styles from './projects.module.css';

/**
 * The project's audit ledger, verified by the API on every load. Every figure shown is a value the API
 * returned; when the call fails the panel says so instead of showing a placeholder.
 */
export async function LedgerPanel({ projectId }: { projectId: string }) {
  const r = await fetched(() => serverApi().GET('/projects/{project_id}/ledger', { params: { path: { project_id: projectId } } }));
  if (!r.data) {
    return (
      <div className={styles.section}>
        <h2>Audit ledger</h2>
        <p role="alert" className={styles.error}>
          The audit ledger could not be loaded{r.status ? ` (HTTP ${r.status})` : ''}. No integrity status is shown because none was verified.
        </p>
      </div>
    );
  }
  const l = r.data;
  const text = ledgerStatusText(l.status);
  return (
    <div className={styles.section}>
      <h2>Audit ledger</h2>
      <p>
        <Chip tone={text.tone} dot>{text.label}</Chip> <span className={styles.muted}>{l.message}</span>
      </p>
      <p className={styles.muted}>{text.explain}</p>
      <dl className={styles.muted} style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: 'var(--space-1) var(--space-3)', margin: 0 }}>
        <dt>Records</dt>
        <dd>{l.record_count}{l.legacy_record_count > 0 ? ` (+${l.legacy_record_count} legacy)` : ''}</dd>
        <dt>Ledger root</dt>
        <dd><code title={l.ledger_root ?? undefined}>{shortHash(l.ledger_root, 16)}</code></dd>
        <dt>Last verified</dt>
        <dd>{formatUtc(l.verified_at)}</dd>
        <dt>Stored in</dt>
        <dd>{l.durable ? 'the database (survives restarts)' : 'memory only (lost on restart)'}</dd>
      </dl>
      {l.failures.length > 0 && (
        <ul className={styles.error} aria-label="Integrity failures">
          {l.failures.map((f, i) => (
            <li key={`${f.record_id ?? 'x'}-${i}`}>{f.sequence != null ? `Record ${f.sequence}: ` : ''}{f.reason}</li>
          ))}
        </ul>
      )}
      {l.records.length > 0 && (
        <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Ledger records, scrollable">
          <table className={styles.table}>
            <thead>
              <tr><th>#</th><th>Kind</th><th>When</th><th>Record id</th><th>Report SHA-256</th></tr>
            </thead>
            <tbody>
              {l.records.map((rec) => (
                <tr key={rec.record_id}>
                  <td>{rec.sequence ?? '—'}</td>
                  <td>{rec.record_kind === 'report.sealed' ? 'Report sealed' : rec.record_kind}</td>
                  <td>{formatUtc(rec.timestamp)}</td>
                  <td><code title={rec.record_id}>{shortHash(rec.record_id.replace('AUDIT-', ''), 8)}</code></td>
                  <td><code title={rec.report_sha256 ?? undefined}>{shortHash(rec.report_sha256, 10)}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className={styles.muted}>{l.limitations}</p>
      {l.records.some((x) => x.record_kind === 'report.sealed') && <VerifyReportForm projectId={projectId} records={l.records.filter((x) => x.record_kind === 'report.sealed').map((x) => x.record_id)} />}
    </div>
  );
}
