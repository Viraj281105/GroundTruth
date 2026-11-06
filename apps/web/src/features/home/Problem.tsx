import React from 'react';
import { Reveal } from '../../components/ds';
import { verra } from './data';
import styles from './Landing.module.css';

export function Problem() {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="problem-title">
      <div className={styles.split}>
        <Reveal variant="left">
          <p className={styles.kicker}>The problem</p>
          <h2 id="problem-title">Climate credits rest on a “what if”.</h2>
          <p className={styles.lead}>
            A carbon-credit project is paid for the climate benefit it says it created. That benefit is a counterfactual:
            the difference from what would have happened anyway. Nobody can observe it, so it has to be estimated, and today the
            project developer usually estimates their own baseline.
          </p>
          <Reveal variant="up" delay={160}>
            <blockquote className={styles.callout}>
              <p>{verra.quote}</p>
              <cite>{verra.source}</cite>
            </blockquote>
          </Reveal>
        </Reveal>
        <Reveal variant="right" delay={120} className={styles.panel}>
          <svg className={styles.svg} viewBox="0 0 400 260" role="img" aria-label="Two paths start together and then diverge. The shaded gap between them is what would have happened anyway.">
            <path className={styles.gapFill} d="M160 150 L370 60 L370 190 L160 150 Z" />
            <line className={styles.marker} x1="160" y1="20" x2="160" y2="220" />
            <path className={styles.axis} d="M20 230 H380" />
            <path className={`${styles.twin} ${styles.draw}`} pathLength={1} d="M20 150 L160 150 L370 190" />
            <path className={`${styles.obs} ${styles.draw}`} pathLength={1} d="M20 150 L160 150 L370 60" />
            <g className={styles.pop}>
              <text className={styles.label} x="166" y="34">Project starts</text>
              <text className={styles.label} x="250" y="40">Claimed path</text>
              <text className={styles.label} x="230" y="212">Would have happened anyway</text>
              <text className={styles.label} x="262" y="132">The gap to be estimated</text>
            </g>
          </svg>
          <span className={styles.sim}>Illustration only, not data</span>
        </Reveal>
      </div>
    </section>
  );
}
