import React from 'react';
import Link from 'next/link';
import { EmptyState } from '../../../../../components/ds';
import { Chip } from '../../../../../components/ds/Chip';
import { SetDataMode } from '../../../../../components/shell/data-mode';
import { ProblemPanel } from '../../../../../features/projects/ProblemPanel';
import { formatBytes, formatUtc, ledgerStatusText, shortHash } from '../../../../../features/projects/ledger.model';
import { fetched } from '../../../../../features/projects/server';
import styles from '../../../../../features/projects/projects.module.css';
import { serverApi } from '../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Reports' };

/**
 * Reports this organization can actually download, one row per project it owns or was granted, with the
 * ledger state the API verified just now. Nothing on this page is stored in the front end: an organization
 * with no projects sees an empty state, and a project nothing was generated for is shown as "nothing sealed yet".
 */
export default async function OrgReportsPage({ params }: { params: { org: string } }) {
  const r = await fetched(() => serverApi().GET('/orgs/{slug}/reports', { params: { path: { slug: params.org } } }));
  if (!r.data) return <ProblemPanel title="Reports" status={r.status} />;
  const reports = r.data.reports;
  const anySimulated = reports.some((p) => p.data_mode === 'simulated');
  return (
    <>
      {anySimulated && <SetDataMode mode="simulated" />}
      <h1 style={{ fontSize: 'var(--text-3xl)', margin: 0 }}>Reports</h1>
      <p className={styles.muted} style={{ maxWidth: '60ch' }}>
        What you can download for each project, and whether the record of what was generated checks out. The technical dossier is a
        ZIP meant for auditors; it is not a summary for a funding committee.
      </p>
      {reports.length === 0 ? (
        <EmptyState title="No reports yet" body="Create a project, or ask the owner of a project to share one with you. Reports appear here once a project exists." />
      ) : (
        <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Reports by project, scrollable">
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Project</th>
                <th>Data</th>
                <th>Last report generated</th>
                <th>Integrity</th>
                <th>Open</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((p) => {
                const text = ledgerStatusText(p.ledger.status);
                return (
                  <tr key={p.project_id}>
                    <td>
                      <Link href={`/app/${params.org}/projects/${p.project_slug}/overview`}>{p.project_name}</Link>
                      <div className={styles.muted}>Your access: {p.access_level}</div>
                    </td>
                    <td>{p.data_mode === 'simulated' ? <Chip tone="sim" dot>Simulated</Chip> : <Chip>Real project</Chip>}</td>
                    <td>
                      {p.last_sealed ? (
                        <>
                          Technical dossier, {formatUtc(p.last_sealed.timestamp)}
                          <div className={styles.muted}>
                            {formatBytes(p.last_sealed.size_bytes)} · SHA-256 <code title={p.last_sealed.report_sha256 ?? undefined}>{shortHash(p.last_sealed.report_sha256, 8)}</code>
                          </div>
                        </>
                      ) : (
                        <span className={styles.muted}>None generated yet</span>
                      )}
                    </td>
                    <td>
                      <Chip tone={text.tone} dot>{text.label}</Chip>
                      <div className={styles.muted}>
                        {p.ledger.record_count} record{p.ledger.record_count === 1 ? '' : 's'}
                        {p.ledger.ledger_root ? <> · root <code title={p.ledger.ledger_root}>{shortHash(p.ledger.ledger_root, 8)}</code></> : null}
                      </div>
                    </td>
                    <td>
                      <Link href={`/app/${params.org}/projects/${p.project_slug}/reports`}>
                        {p.dossier_available ? 'Download & verify' : 'View reports'}
                      </Link>
                      {!p.dossier_available && <div className={styles.muted}>{p.dossier_note}</div>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
