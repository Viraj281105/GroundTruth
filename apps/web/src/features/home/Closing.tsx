import React from 'react';
import { LinkButton, Reveal } from '../../components/ds';
import { faqs, notYet, works } from './data';
import styles from './Landing.module.css';

export function HonestStatus() {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="status-title">
      <Reveal><h2 id="status-title">Honest status</h2></Reveal>
      <div className={styles.cols}>
        <Reveal variant="left" className={styles.col}>
          <h3>What works today</h3>
          <ul>{works.map((w) => <li key={w}>{w}</li>)}</ul>
        </Reveal>
        <Reveal variant="right" delay={80} className={styles.col}>
          <h3>What is not built yet</h3>
          <ul>{notYet.map((w) => <li key={w}>{w}</li>)}</ul>
        </Reveal>
      </div>
      <p className={styles.simNote}>
        Simulated data: no real project has been analysed. Every result in the product comes from a deterministic simulated
        fixture and is labelled as such.
      </p>
    </section>
  );
}

export function Faq() {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="faq-title">
      <Reveal><h2 id="faq-title">Questions</h2></Reveal>
      <div className={styles.faq}>
        {faqs.map((f, i) => (
          <Reveal key={f.q} delay={i * 60}>
            <details><summary>{f.q}</summary><p>{f.a}</p></details>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section className="gt-container" aria-labelledby="cta-title">
      <Reveal variant="scale" className={styles.cta}>
        <h2 id="cta-title">See the gap for yourself</h2>
        <p className={styles.lead} style={{ marginInline: 'auto' }}>Sign in to open a workspace, or read how the method works.</p>
        <div className={styles.ctaActions}>
          <LinkButton href="/login?next=%2Fapp" size="lg">Sign in to your workspace</LinkButton>
          <LinkButton href="/method" variant="secondary" size="lg">Read how it works</LinkButton>
        </div>
      </Reveal>
    </section>
  );
}
