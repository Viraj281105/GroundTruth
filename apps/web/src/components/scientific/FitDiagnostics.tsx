'use client';

import React from 'react';
import { ChevronRight } from 'lucide-react';
import { Evidence } from '../../lib/types';
import { deriveFitDiagnostics } from '../../lib/fit-diagnostics';
import { Badge } from '../ui/Badge';
import styles from './FitDiagnostics.module.css';

export interface FitDiagnosticsProps {
  items: Evidence[];
  /** Opens the provenance drawer for a row's evidence item. */
  onSelectEvidence: (item: Evidence) => void;
  className?: string;
}

/**
 * Pre-treatment fit, convex-hull containment and period coverage.
 *
 * Each value is read from its evidence item and is one click from its
 * provenance. Status is stated in words as well as tone, so it does not depend
 * on colour, and a failed check is amber — it limits the result, it does not
 * indicate wrongdoing or a malfunction.
 */
export const FitDiagnostics: React.FC<FitDiagnosticsProps> = ({
  items,
  onSelectEvidence,
  className = '',
}) => {
  const groups = deriveFitDiagnostics(items);

  return (
    <section className={`${styles.container} ${className}`} aria-labelledby="fit-diagnostics-title">
      <div className={styles.header}>
        <h4 id="fit-diagnostics-title" className={styles.title}>
          Fit &amp; identification diagnostics
        </h4>
        <p className={styles.subtitle}>
          Conditions the counterfactual must meet before its post-treatment gap can be read as an
          effect. Select a value to see its provenance.
        </p>
      </div>

      <div className="gt-grid-3">
        {groups.map((group) => (
          <article key={group.id} className={styles.group} aria-labelledby={`fit-group-${group.id}`}>
            <div className={styles.groupHeader}>
              <h5 id={`fit-group-${group.id}`} className={styles.groupTitle}>
                {group.title}
              </h5>
              <Badge tone={group.tone} size="sm" variant="subtle">
                {group.status}
              </Badge>
            </div>
            <p className={styles.summary}>{group.summary}</p>

            <ul className={styles.rows}>
              {group.rows.map((r) => (
                <li key={r.evidenceId}>
                  {r.item ? (
                    <button
                      type="button"
                      className={styles.row}
                      onClick={() => r.item && onSelectEvidence(r.item)}
                      aria-label={`${r.label}: ${r.display}${r.detail ? `, ${r.detail}` : ''}. Show provenance.`}
                    >
                      <span className={styles.rowLabel}>{r.label}</span>
                      <span className={styles.rowValue}>{r.display}</span>
                      {r.detail && <span className={styles.rowDetail}>{r.detail}</span>}
                      <ChevronRight size={14} className={styles.rowIcon} aria-hidden="true" />
                    </button>
                  ) : (
                    <div className={`${styles.row} ${styles.rowMissing}`}>
                      <span className={styles.rowLabel}>{r.label}</span>
                      <span className={styles.rowValue}>{r.display}</span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
};
