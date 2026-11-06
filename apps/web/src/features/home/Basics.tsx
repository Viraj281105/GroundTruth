import React from 'react';
import { CountUp, Reveal } from '../../components/ds';
import { buildFacts } from './data';
import styles from './Landing.module.css';

/** A hand-drawn-in divider line between sections. */
export function Divider() {
  return (
    <Reveal variant="fade" className="gt-container">
      <svg className={styles.divider} viewBox="0 0 400 24" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path className={styles.draw} pathLength={1} d="M2 12 C60 2 120 22 200 12 S340 2 398 12" />
      </svg>
    </Reveal>
  );
}

export function TrustFacts({ caseCount }: { caseCount: number | null }) {
  return (
    <section className="gt-container" aria-label="Facts about GroundTruth">
      <ul className={styles.facts}>
        {buildFacts(caseCount).map((f, i) => (
          <Reveal as="li" key={f.id} delay={i * 80} className={styles.fact}>
            <span className={`num ${styles.factNum}`}><CountUp value={f.value} /></span>
            <span className={styles.factLabel}>{f.label}</span>
            <span className={styles.factNote}>{f.note}</span>
          </Reveal>
        ))}
      </ul>
    </section>
  );
}
