import React from 'react';
import { EmptyState, Skeleton } from '../ds';
import styles from './panels.module.css';

/** Loading placeholder shared by all panels. */
export function PanelLoading({ label }: { label: string }) {
  return (
    <div className={styles.skeletons} role="status" aria-busy="true" aria-label={`Loading ${label}`}>
      <Skeleton width="40%" height="1.25rem" />
      <Skeleton height="4rem" />
      <Skeleton width="70%" />
    </div>
  );
}

/** "Nothing here" state: says what is missing, not filler. */
export function PanelEmpty({ title, body }: { title: string; body?: string }) {
  return <EmptyState title={title} body={body} />;
}
