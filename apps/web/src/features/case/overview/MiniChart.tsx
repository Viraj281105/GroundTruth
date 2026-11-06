import React from 'react';
import type { Sparkline } from './sparkline';
import { overviewCopy as c } from './copy';
import styles from './overview.module.css';

/** Small observed-vs-counterfactual chart from the same series as the full chart. */
export function MiniChart({ chart }: { chart: Sparkline | null }) {
  if (!chart) return <p className={styles.muted}>{c.chartNone}</p>;
  return (
    <figure className={styles.figure}>
      <svg viewBox={`0 0 ${chart.width} ${chart.height}`} role="img" aria-label={c.chartDesc} className={styles.svg}>
        {chart.treatmentX !== null && (
          <line x1={chart.treatmentX} x2={chart.treatmentX} y1={0} y2={chart.height} className={styles.treat} />
        )}
        <polyline points={chart.synthetic} className={styles.lineSynthetic} fill="none" />
        <polyline points={chart.observed} className={styles.lineObserved} fill="none" />
      </svg>
      <figcaption className={styles.legend}>
        <span className={styles.keyObserved}>{c.chartObserved}</span>
        <span className={styles.keySynthetic}>{c.chartCounterfactual}</span>
      </figcaption>
    </figure>
  );
}
