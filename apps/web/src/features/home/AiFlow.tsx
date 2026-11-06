import React from 'react';
import { Reveal } from '../../components/ds';
import { flowSteps } from './data';
import styles from './Landing.module.css';

export function AiFlow() {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="ai-title">
      <Reveal>
        <h2 id="ai-title">Where AI fits</h2>
        <p className={styles.lead}>
          A statistics engine does all the maths. A language model is only allowed to describe the finished numbers, and a check
          confirms every figure in its text against the evidence. If any figure fails, a plain deterministic report is published instead.
        </p>
      </Reveal>
      <ol className={styles.flow}>
        {flowSteps.map((s, i) => (
          <Reveal as="li" key={s.id} variant="up" delay={i * 80} className={`${styles.node} ${s.id === 'llm' ? styles.nodeAi : ''}`}>
            <strong>{s.label}</strong>
            <span>{s.sub}</span>
          </Reveal>
        ))}
      </ol>
      <Reveal variant="scale" delay={200}><p className={styles.big}>The model never computes a number.</p></Reveal>
    </section>
  );
}
