import React from 'react';
import Link from 'next/link';
import { Card, Chip } from '../../components/ds';
import type { CaseSummary } from '../../lib/types';
import { casesCopy as c } from './copy';
import { statusInfo } from './filter';
import styles from './CaseCard.module.css';

export function CaseCard({ item }: { item: CaseSummary }) {
  const s = statusInfo(item.status);
  return (
    <Card tone="interactive" className={styles.card}>
      <div className={styles.chips}>
        <Chip>{item.standard}</Chip>
        <Chip tone={s.tone} dot>{s.label}</Chip>
      </div>
      <h3 className={styles.title}>
        <Link href={`/cases/${item.case_id}`} className={styles.link}>{item.name}</Link>
      </h3>
      <p className={styles.where}>{item.country} · {item.ecosystem}</p>
      <dl className={styles.meta}>
        <div><dt>{c.baseline}</dt><dd>{item.pre_period}</dd></div>
        <div><dt>{c.crediting}</dt><dd>{item.post_period}</dd></div>
      </dl>
    </Card>
  );
}
