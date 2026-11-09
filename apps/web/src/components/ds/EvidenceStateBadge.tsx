import React from 'react';
import styles from './EvidenceStateBadge.module.css';

export type EvidenceState = 'OBSERVED' | 'DERIVED' | 'MODEL_ESTIMATED' | 'INFERRED' | 'UNAVAILABLE';

export const EVIDENCE_STATE_LABELS: Record<EvidenceState, { short: string; long: string; cls: string }> = {
  OBSERVED: { short: 'Observed', long: 'Observed: measured directly from source data', cls: 'observed' },
  DERIVED: { short: 'Derived', long: 'Derived: computed deterministically from observed data', cls: 'derived' },
  MODEL_ESTIMATED: { short: 'Model estimated', long: 'Model estimated: produced by a statistical model with stated assumptions', cls: 'model' },
  INFERRED: { short: 'Inferred', long: 'Inferred: a reasoned conclusion that is not directly measured', cls: 'inferred' },
  UNAVAILABLE: { short: 'Unavailable', long: 'Unavailable: no evidence exists for this yet', cls: 'unavailable' },
};

/** Evidence state marker. Shape (not colour alone) distinguishes the five states. */
export function EvidenceStateBadge({ state, className = '' }: { state: EvidenceState; className?: string }) {
  const info = EVIDENCE_STATE_LABELS[state];
  return (
    <span
      className={`${styles.badge} ${styles[info.cls]} ${className}`.trim()}
      role="img"
      aria-label={`Evidence state: ${info.long}`}
      data-evidence-state={state}
    >
      <span className={styles.mark} aria-hidden="true" />
      <span aria-hidden="true">{info.short}</span>
    </span>
  );
}
