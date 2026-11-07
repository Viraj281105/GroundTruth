import React from 'react';
import styles from './Card.module.css';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** `raised` is the default surface; `sunken` is for nested/inset content; `interactive` adds hover lift. */
  tone?: 'raised' | 'sunken' | 'interactive';
  padded?: boolean;
}

export function Card({ tone = 'raised', padded = true, className = '', ...rest }: CardProps) {
  return <div className={`${styles.card} ${styles[tone]} ${padded ? styles.padded : ''} ${className}`} {...rest} />;
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: React.ReactNode }) {
  return (
    <div className={styles.stat}>
      <div className={styles.statLabel}>{label}</div>
      <div className={`${styles.statValue} num`}>{value}</div>
      {hint && <div className={styles.statHint}>{hint}</div>}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className={styles.empty} role="status">
      <h3>{title}</h3>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ width = '100%', height = '1rem', radius }: { width?: string; height?: string; radius?: string }) {
  return <span className={styles.skeleton} style={{ width, height, borderRadius: radius }} aria-hidden="true" />;
}
