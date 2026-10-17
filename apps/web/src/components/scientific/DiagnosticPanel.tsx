'use client';

import React from 'react';
import { ChevronRight } from 'lucide-react';
import { Evidence } from '../../lib/types';
import { DiagnosticGroup } from '../../lib/diagnostics';
import { Badge } from '../ui/Badge';
import styles from './DiagnosticPanel.module.css';

export interface DiagnosticPanelProps {
  /** Stable id used to label the panel and its groups. */
  id: string;
  title: string;
  description: string;
  groups: DiagnosticGroup[];
  /** Grid columns on desktop; collapses on narrower screens. */
  columns?: 1 | 2 | 3;
  /** Opens the provenance drawer for a row's evidence item. */
  onSelectEvidence: (item: Evidence) => void;
  className?: string;
}

/**
 * A set of evidence diagnostics, one card per check.
 *
 * Each value is read from its evidence item and is one click from its
 * provenance. Status is stated in words as well as tone, so it does not depend
 * on colour, and a failed check is amber — it limits the result, it does not
 * indicate wrongdoing or a malfunction.
 */
export const DiagnosticPanel: React.FC<DiagnosticPanelProps> = ({
  id,
  title,
  description,
  groups,
  columns = 3,
  onSelectEvidence,
  className = '',
}) => {
  return (
    <section className={`${styles.container} ${className}`} aria-labelledby={`${id}-title`}>
      <div className={styles.header}>
        <h4 id={`${id}-title`} className={styles.title}>
          {title}
        </h4>
        <p className={styles.subtitle}>{description} Select a value to see its provenance.</p>
      </div>

      <div className={columns === 1 ? styles.single : `gt-grid-${columns}`}>
        {groups.map((group) => (
          <article key={group.id} className={styles.group} aria-labelledby={`${id}-${group.id}`}>
            <div className={styles.groupHeader}>
              <h5 id={`${id}-${group.id}`} className={styles.groupTitle}>
                {group.title}
              </h5>
              <Badge tone={group.tone} size="sm" variant="subtle">
                {group.status}
              </Badge>
            </div>
            <p className={styles.summary}>{group.summary}</p>
            {group.caveats && group.caveats.length > 0 && (
              <ul className={styles.caveats} aria-label={`${group.title} caveats`}>
                {group.caveats.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}

            <ul className={styles.rows}>
              {group.rows.map((r, idx) => (
                <li key={`${r.evidenceId}-${idx}`}>
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
