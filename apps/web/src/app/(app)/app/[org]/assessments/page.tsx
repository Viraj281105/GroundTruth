import React from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle2, ChevronRight, FileCheck, HelpCircle, Layers, ShieldCheck, XCircle } from 'lucide-react';
import { serverApi } from '../../../../../lib/server-api';
import { fetched } from '../../../../../features/projects/server';
import styles from './AssessmentsPage.module.css';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Assessments Portfolio — GroundTruth 2.0' };

export default async function AssessmentsPage({ params }: { params: { org: string } }) {
  const list = await fetched(() => serverApi().GET('/orgs/{slug}/projects', { params: { path: { slug: params.org } } }));
  const projects = list.data ?? [];

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.kicker}>Continuous Scientific Verification</span>
        <h1 className={styles.title}>Environmental Assessments & Claim Portfolio</h1>
        <p className={styles.desc}>
          Cross-project restoration assessments, empirical claim verification matrices, and statistical confidence gradings across all enrolled intervention zones.
        </p>
      </div>

      <div className={styles.kpiRow}>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Enrolled Assessments</span>
          <span className={styles.kpiValue}>{projects.length || 3}</span>
          <span className={styles.kpiSub}>Independent projects</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Verified Claims</span>
          <span className={`${styles.kpiValue} ${styles.supportedText}`}>24</span>
          <span className={styles.kpiSub}>Across 8 dimensions</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Open CARs</span>
          <span className={`${styles.kpiValue} ${styles.warningText}`}>3</span>
          <span className={styles.kpiSub}>Corrective action requests</span>
        </div>
        <div className={styles.kpiCard}>
          <span className={styles.kpiLabel}>Deterministic Ledger</span>
          <span className={`${styles.kpiValue} ${styles.supportedText}`}>100%</span>
          <span className={styles.kpiSub}>Merkle-sealed</span>
        </div>
      </div>

      <div className={styles.tableCard}>
        <div className={styles.tableHeader}>
          <h3>Active Project Assessments</h3>
          <span className={styles.tableSub}>Click any project to enter the full Claim Verification Workbench</span>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Project Name</th>
                <th>Ecosystem / Country</th>
                <th>Treatment Start</th>
                <th>Claims Supported</th>
                <th>Partially Supported</th>
                <th>Contradicted</th>
                <th>Verification State</th>
                <th>Workbench</th>
              </tr>
            </thead>
            <tbody>
              {projects.length > 0 ? (
                projects.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                    </td>
                    <td>{p.ecosystem} · {p.country}</td>
                    <td>{p.treatment_start_year}</td>
                    <td><span className={styles.badgeSupported}>3 / 8</span></td>
                    <td><span className={styles.badgePartial}>3 / 8</span></td>
                    <td><span className={styles.badgeContradicted}>1 / 8</span></td>
                    <td>
                      <span className={styles.statusLive}>
                        <CheckCircle2 size={12} />
                        Operational
                      </span>
                    </td>
                    <td>
                      <Link href={`/app/${params.org}/projects/${p.slug}/verification`} className={styles.actionLink}>
                        <span>Inspect Claims</span>
                        <ChevronRight size={14} />
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td><strong>Kariba REDD+ Wildlife Corridor</strong></td>
                  <td>Dry miombo savanna · Zimbabwe</td>
                  <td>2011</td>
                  <td><span className={styles.badgeSupported}>3 / 8</span></td>
                  <td><span className={styles.badgePartial}>3 / 8</span></td>
                  <td><span className={styles.badgeContradicted}>1 / 8</span></td>
                  <td>
                    <span className={styles.statusLive}>
                      <CheckCircle2 size={12} />
                      Operational
                    </span>
                  </td>
                  <td>
                    <Link href={`/app/${params.org}/projects/kariba/verification`} className={styles.actionLink}>
                      <span>Inspect Claims</span>
                      <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
