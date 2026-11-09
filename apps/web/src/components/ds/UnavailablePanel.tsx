import React from 'react';
import styles from './UnavailablePanel.module.css';
import { EvidenceStateBadge } from './EvidenceStateBadge';

export interface UnavailablePanelProps {
  title: string;
  reason: React.ReactNode;
  evidenceNeeded: React.ReactNode;
  action?: React.ReactNode;
}

/** Honest "we cannot show this yet" panel: says why, and exactly what evidence would unlock it (R5, R6). */
export function UnavailablePanel({ title, reason, evidenceNeeded, action }: UnavailablePanelProps) {
  return (
    <section className={styles.panel} aria-label={`${title} (unavailable)`}>
      <EvidenceStateBadge state="UNAVAILABLE" />
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.reason}>{reason}</p>
      <p className={styles.need}>
        <b>Evidence needed</b> {evidenceNeeded}
      </p>
      {action && <div className={styles.action}>{action}</div>}
    </section>
  );
}
