import React from 'react';
import Link from 'next/link';
import { EmptyState, LinkButton } from '../../../../../components/ds';
import { Chip } from '../../../../../components/ds/Chip';
import { ProblemPanel } from '../../../../../features/projects/ProblemPanel';
import { SetDataMode } from '../../../../../components/shell/data-mode';
import { canCreateProject, dataModeLabel, isLibraryCase, projectDataMode } from '../../../../../features/projects/model';
import { fetched, loadOrg } from '../../../../../features/projects/server';
import styles from '../../../../../features/projects/projects.module.css';
import { serverApi } from '../../../../../lib/server-api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Projects' };

/** The project registry: everything this organization owns or was granted. Assessment levels come from the portfolio endpoint, never computed here. */
export default async function ProjectsPage({ params }: { params: { org: string } }) {
  const org = await loadOrg(params.org);
  const list = await fetched(() => serverApi().GET('/orgs/{slug}/projects', { params: { path: { slug: params.org } } }));
  if (!list.data) return <ProblemPanel title="Projects" status={list.status} />;
  const projects = list.data;
  // The portfolio endpoint is funder/government only; when it is not offered we omit the column.
  const levels = new Map<string, string>();
  if (org && (org.type === 'funder' || org.type === 'government')) {
    const pf = await fetched(() => serverApi().GET('/orgs/{slug}/portfolio', { params: { path: { slug: params.org } } }));
    for (const row of [...(pf.data?.projects ?? []), ...(pf.data?.simulated ?? [])]) {
      if (!row.degraded) levels.set(row.project.id, `Level ${row.assessment_level} · ${row.level_name}`);
    }
  }
  const showLevel = levels.size > 0;
  const anySimulated = projects.some((p) => projectDataMode(p) === 'simulated');
  return (
    <>
      {anySimulated && <SetDataMode mode="simulated" />}
      <div className={styles.actions} style={{ justifyContent: 'space-between', marginBottom: 'var(--space-4)' }}>
        <h1 style={{ fontSize: 'var(--text-3xl)', margin: 0 }}>Projects</h1>
        {org && canCreateProject(org.type, org.role) && <LinkButton href={`/app/${params.org}/projects/new`}>New project</LinkButton>}
      </div>
      {projects.length === 0 ? (
        <EmptyState title="No projects yet" body="Projects this organization owns, or that another organization has shared with it, appear here." />
      ) : (
        <div className={styles.tableWrap} role="region" tabIndex={0} aria-label="Projects, scrollable">
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Project</th>
                <th>Owner</th>
                <th>Access</th>
                {showLevel && <th>Assessment level</th>}
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link href={`/app/${params.org}/projects/${p.slug}/overview`}>{p.name}</Link>
                    <div className={styles.muted}>
                      {p.country} · {p.ecosystem} · {p.intervention}
                    </div>
                  </td>
                  <td>{p.owner_name}</td>
                  <td>{p.access_level}</td>
                  {showLevel && <td>{levels.get(p.id) ?? '—'}</td>}
                  <td>
                    {isLibraryCase(p) ? (
                      <span className={styles.libraryNote}>{dataModeLabel(p)}</span>
                    ) : p.data_mode === 'simulated' ? (
                      <Chip tone="sim" dot>{dataModeLabel(p)}</Chip>
                    ) : (
                      <Chip>{dataModeLabel(p)}</Chip>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
