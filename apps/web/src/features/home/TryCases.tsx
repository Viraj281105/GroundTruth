import React from 'react';
import { LinkButton, Reveal } from '../../components/ds';
import { CaseCard } from '../cases/CaseCard';
import type { CaseSummary } from '../../lib/types';
import styles from './Landing.module.css';

export function TryCases({ cases, failed, series }: { cases: CaseSummary[]; failed: boolean; series: Record<string, number[]> }) {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="try-title">
      <Reveal className={styles.row}>
        <h2 id="try-title">Try a case</h2>
        <LinkButton href="/cases" variant="ghost">All cases</LinkButton>
      </Reveal>
      <p className={styles.lead}>Simulated data: open a benchmark case to see the twin, the gap and the stress tests.</p>
      {failed ? (
        <p role="alert" className={styles.fail}>Cases could not be loaded right now, so none are shown. Try again shortly.</p>
      ) : cases.length === 0 ? (
        <p className={styles.fail}>No cases are available yet.</p>
      ) : (
        <div className={styles.grid}>
          {cases.slice(0, 3).map((x, i) => (
            <Reveal key={x.case_id} delay={i * 80}><CaseCard item={x} series={series[x.case_id]} /></Reveal>
          ))}
        </div>
      )}
    </section>
  );
}
