import React from 'react';
import styles from './Chip.module.css';

export type ChipTone = 'neutral' | 'accent' | 'caution' | 'danger' | 'sim';

export interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: ChipTone;
  dot?: boolean;
}

/** Small status label. `tone="sim"` is reserved for the simulated-data marker (R7). */
export function Chip({ tone = 'neutral', dot = false, className = '', children, ...rest }: ChipProps) {
  return (
    <span className={`${styles.chip} ${styles[tone]} ${className}`} {...rest}>
      {dot && <span className={styles.dot} aria-hidden="true" />}
      {children}
    </span>
  );
}
