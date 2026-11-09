import React from 'react';
import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { Chip, EmptyState } from '../../../../../components/ds';
import { SetDataMode } from '../../../../../components/shell/data-mode';
import { toRow, kpis, type AssessmentRow } from '../../../../../features/assessments/model';
import { ProblemPanel } from '../../../../../features/projects/ProblemPanel';
import { fetched } from '../../../../../features/projects/server';
import { serverApi } from '../../../../../lib/server-api';
import styles from './AssessmentsPage.module.css';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Assessments — GroundTruth 2.0' };

/**
 * Every figure here is read from the API for the projects of THIS organization: the assessment level the
 * server derived, and the claim counts from the structured-claims endpoint. Nothing is computed or assumed.
 */
export default async function AssessmentsPage({ params }: { params: { org: string } }) {
  const list = await fetched(() => serverApi().GET('/orgs/{slug}/projects', { params: { path: { slug: params.org } } }));
  if (!list.data) {
    return <ProblemPanel title="Assessments" status={list.status} />;
  }
  const rows: AssessmentRow[] = await Promise.all(
    list.data.map(async (p) => {
      const path = { project_id: p.id };
      const [assessment, claims] = await Promise.all([
        fetched(() => serverApi().GET('/projects/{project_id}/assessment', { params: { path } })),
        fetched(() => serverApi().GET('/claims/structured/{project_id}', { params: { path } })),
      ]);
      return toRow(p, assessment, claims);
    }),
  );
  const k = kpis(rows);
  const base = `/app/${params.org}/projects`;

  return (
    <div className={styles.container}>
      {k.simulatedProjects > 0 && <SetDataMode mode="simulated" />}
      <div className={styles.header}>
        <span className={styles.kicker}>Assessments</span>
        <h1 className={styles.title}>Assessments &amp; claims by project</h1>
        <p className={styles.desc}>
          For each project in this organization: the assessment level the platform has reached and how many claims have been recorded. Open a
          project to see the evidence behind each figure.
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="No projects yet"
          body="Assessments appear here once you create a project."
          action={<Link href={`/app/${params.org}/projects/new`}>Create project</Link>}
        />
      ) : (
        <>
          <div className={styles.kpiRow}>
            <div className={styles.kpiCard}>
              <span className={styles.kpiLabel}>Projects</span>
              <span className={styles.kpiValue}>{k.projects}</span>
              <span className={styles.kpiSub}>In this organization</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={styles.kpiLabel}>Assessments available</span>
              <span className={styles.kpiValue}>{k.assessmentsAvailable}</span>
              <span className={styles.kpiSub}>of {k.projects} projects</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={styles.kpiLabel}>Claims recorded</span>
              <span className={styles.kpiValue}>{k.claimsOnRealProjects}</span>
              <span className={styles.kpiSub}>Real projects only; not verified results</span>
            </div>
            <div className={styles.kpiCard}>
              <span className={styles.kpiLabel}>Simulated projects</span>
              <span className={styles.kpiValue}>{k.simulatedProjects}</span>
              <span className={styles.kpiSub}>Benchmark data, not real</span>
            </div>
          </div>

          <div className={styles.tableCard}>
            <div className={styles.tableHeader}>
              <h3>Project assessments</h3>
              <span className={styles.tableSub}>Open a project to review its claims and evidence</span>
            </div>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Project</th>
                    <th>Ecosystem / Country</th>
                    <th>Treatment start</th>
                    <th>Assessment level</th>
                    <th>Claims</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <strong>{r.name}</strong>
                        {r.simulated && (
                          <>
                            {' '}
                            <Chip tone="sim">Simulated</Chip>
                          </>
                        )}
                        {r.libraryCase && !r.simulated && (
                          <>
                            {' '}
                            <Chip>No boundary uploaded</Chip>
                          </>
                        )}
                      </td>
                      <td>{r.place}</td>
                      <td>{r.treatmentStart}</td>
                      <td>{r.level ?? <span className={styles.tableSub}>{r.levelUnavailable}</span>}</td>
                      <td>
                        {r.claims ? (
                          r.claims.hasClaims ? (
                            <span>
                              {r.claims.total} total · {r.claims.supported} supported · {r.claims.partiallySupported} partly · {r.claims.contradicted}{' '}
                              contradicted · {r.claims.unverified} unverified
                            </span>
                          ) : (
                            <span className={styles.tableSub}>No claims recorded yet</span>
                          )
                        ) : (
                          <span className={styles.tableSub}>{r.claimsUnavailable}</span>
                        )}
                      </td>
                      <td>
                        <Link href={`${base}/${r.slug}/verification`} className={styles.actionLink}>
                          <span>Claims</span>
                          <ChevronRight size={14} />
                        </Link>{' '}
                        <Link href={`${base}/${r.slug}/overview`} className={styles.actionLink}>
                          <span>Overview</span>
                          <ChevronRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
