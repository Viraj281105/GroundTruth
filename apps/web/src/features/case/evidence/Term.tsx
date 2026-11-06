'use client';

import React from 'react';
import { Tooltip } from '../../../components/ds';
import { glossary } from '../../../lib/glossary';
import { useLens } from '../../../lib/lens';
import styles from './evidence.module.css';

/** A glossary term with a hover/focus explanation matched to the current lens. */
export function Term({ id, children }: { id: string; children?: React.ReactNode }) {
  const { lens } = useLens();
  const entry = glossary(id);
  if (!entry) return <>{children}</>;
  return (
    <Tooltip text={lens === 'story' ? entry.plain : entry.technical}>
      <span className={styles.term}>{children ?? entry.label}</span>
    </Tooltip>
  );
}

export function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: React.ReactNode;
  lead?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className={styles.section} aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className={styles.sectionTitle}>
        {title}
      </h2>
      {lead && <p className={styles.lead}>{lead}</p>}
      {children}
    </section>
  );
}
