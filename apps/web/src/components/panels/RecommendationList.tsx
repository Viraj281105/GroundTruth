import React from 'react';
import { recommendationsFor } from './recommendations.model';
import type { RecommendationView } from './types';
import styles from './panels.module.css';

export function RecommendationList({ recommendations, persona }: { recommendations: readonly RecommendationView[]; persona?: string | null }) {
  if (recommendations.length === 0) {
    return (
      <p className={styles.notice} role="status">
        No recommendations triggered by the available evidence.
      </p>
    );
  }
  const ordered = recommendationsFor(recommendations, persona);
  const initial = ordered.slice(0, 2);
  const extra = ordered.slice(2);
  const renderItem = (r: (typeof ordered)[0]) => (
    <li key={r.id} className={styles.rec} data-recommendation-id={r.id}>
      <span className={styles.pri}>
        <b>{r.priority}</b>
        priority
      </span>
      <div>
        <h4>{r.text}</h4>
        <div className={styles.why}>
          <span>
            <b>Why</b>
            {r.rationale}
          </span>
          {r.evidence_refs.length > 0 && (
            <span className={styles.refs}>
              <b>Evidence</b>
              {r.evidence_refs.map((ref) => (
                <span key={ref} className={styles.ref}>
                  {ref}
                </span>
              ))}
            </span>
          )}
        </div>
      </div>
    </li>
  );

  return (
    <>
      <ol className={styles.recs} aria-label="Recommendations">
        {initial.map(renderItem)}
      </ol>
      {extra.length > 0 && (
        <details className={styles.collapsibleBlock}>
          <summary className={styles.collapsibleSummary}>
            <span>View {extra.length} more recommendation{extra.length > 1 ? 's' : ''}</span>
          </summary>
          <div className={styles.collapsibleContent}>
            <ol className={styles.recs} aria-label="Additional recommendations">
              {extra.map(renderItem)}
            </ol>
          </div>
        </details>
      )}
    </>
  );
}
