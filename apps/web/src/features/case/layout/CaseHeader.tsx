import React from 'react';
import Link from 'next/link';
import { Chip, LinkButton } from '../../../components/ds';
import type { CaseDetail } from '../../../lib/types';
import { CaseTabs } from './CaseTabs';
import { layoutCopy as c } from './copy';
import styles from './layout.module.css';

export function CaseHeader({ detail, isDemo }: { detail: CaseDetail; isDemo: boolean }) {
  const id = encodeURIComponent(detail.case_id);
  return (
    <header className={styles.header}>
      <div className="gt-container">
        <nav aria-label={c.breadcrumbLabel} className={styles.crumbs}>
          <Link href="/cases">{c.breadcrumbRoot}</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{detail.name}</span>
        </nav>
        <div className={styles.titleRow}>
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>{detail.name}</h1>
            <div className={styles.chips}>
              <Chip>{detail.standard}</Chip>
              <Chip tone="accent">{detail.status}</Chip>
              <Chip>{detail.country}</Chip>
              {isDemo && <Chip>{c.demoChip}</Chip>}
            </div>
          </div>
          <LinkButton href={`/cases/${id}/run`} size="lg">
            {c.runAnalysis}
          </LinkButton>
        </div>
        <CaseTabs caseId={detail.case_id} />
      </div>
    </header>
  );
}
