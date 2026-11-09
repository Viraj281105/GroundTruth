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
  return (
    <ol className={styles.recs} aria-label="Recommendations">
      {ordered.map((r) => (
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
      ))}
    </ol>
  );
}
