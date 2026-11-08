import React from 'react';
import Link from 'next/link';
import { getCases, getVisualizationFixture } from '../../lib/api';
import type { CaseSummary } from '../../lib/types';
import { Chip, LinkButton } from '../../components/ds';
import { observedSeriesMap } from '../../features/cases/viz';
import { CasesBrowser } from '../../features/cases/CasesBrowser';
import { casesCopy as c } from '../../features/cases/copy';
import styles from '../../features/cases/CasesPage.module.css';

export const dynamic = 'force-dynamic';

export default async function CasesPage() {
  let cases: CaseSummary[] = [];
  let isDemo = false;
  let failed = false;
  try {
    const res = await getCases();
    cases = res.data;
    isDemo = res.isDemo;
  } catch {
    failed = true;
  }

  return (
    <div className={`gt-container ${styles.page}`}>
      <div className={styles.headerRow}>
        <div>
          <h1>{c.title}</h1>
          <p className={styles.intro}>{c.intro}</p>
        </div>
        <LinkButton href="/cases/new" size="md">
          + Register project
        </LinkButton>
      </div>
      {isDemo && <p className={styles.demo}><Chip tone="sim">Demo mode</Chip> {c.demo}</p>}
      {failed ? (
        <div role="alert" className={styles.error}>
          <h2>{c.errorTitle}</h2>
          <p>{c.errorBody}</p>
          <Link href="/cases" className={styles.retry}>{c.retry}</Link>
        </div>
      ) : (
        <CasesBrowser cases={cases} series={observedSeriesMap(cases.map((x) => x.case_id), getVisualizationFixture)} />
      )}
    </div>
  );
}
