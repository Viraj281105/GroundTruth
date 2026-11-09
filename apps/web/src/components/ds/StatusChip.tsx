import React from 'react';
import styles from './StatusChip.module.css';

export const DIMENSION_STATUSES = [
  'Improving',
  'Deteriorating',
  'Stable',
  'Mixed spatial performance',
  'Elevated ecological risk',
  'No clear change',
  'Insufficient evidence',
] as const;
export type DimensionStatus = (typeof DIMENSION_STATUSES)[number];

const STYLE: Record<DimensionStatus, string> = {
  Improving: 'improving',
  Deteriorating: 'deteriorating',
  Stable: 'stable',
  'Mixed spatial performance': 'mixed',
  'Elevated ecological risk': 'risk',
  'No clear change': 'noclear',
  'Insufficient evidence': 'insufficient',
};

/**
 * Dimension status chip. Each status has its own glyph and border style, so meaning never rests
 * on colour alone. "Insufficient evidence" is deliberately neutral and dashed: it is never styled
 * like "Improving".
 */
export function StatusChip({ status, className = '' }: { status: DimensionStatus; className?: string }) {
  const key = STYLE[status];
  return (
    <span
      className={`${styles.chip} ${styles[key]} ${className}`.trim()}
      role="img"
      aria-label={`Status: ${status}`}
      data-status-style={key}
    >
      <span className={styles.glyph} aria-hidden="true" />
      <span aria-hidden="true">{status}</span>
    </span>
  );
}
