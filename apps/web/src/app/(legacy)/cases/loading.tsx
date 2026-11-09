import React from 'react';
import { Skeleton } from '../../../components/ds';
import styles from '../../../features/cases/CasesPage.module.css';

export default function Loading() {
  return (
    <div className={`gt-container ${styles.page}`} role="status" aria-label="Loading cases">
      <Skeleton width="10rem" height="2.5rem" />
      <div style={{ height: 'var(--space-8)' }} />
      <div className={styles.skelGrid}>
        {[0, 1, 2].map((i) => (
          <div key={i} className={styles.skelCard}>
            <Skeleton width="40%" height="1.5rem" />
            <Skeleton width="80%" height="1.5rem" />
            <Skeleton width="60%" />
          </div>
        ))}
      </div>
    </div>
  );
}
