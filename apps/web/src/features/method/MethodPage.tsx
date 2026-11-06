import React from 'react';
import { Card } from '../../components/ds';
import { GLOSSARY_TERMS, glossary } from '../../lib/glossary';
import { PipelineDiagram } from './PipelineDiagram';
import { METHOD_COPY as C } from './copy';
import styles from './MethodPage.module.css';

export function MethodPage() {
  return (
    <div className={`gt-container ${styles.wrap}`}>
      <header className={styles.prose}>
        <h1 className={styles.title}>{C.title}</h1>
        <p className={styles.lead}>{C.intro}</p>
      </header>

      <PipelineDiagram />

      <section aria-labelledby="steps">
        <h2 id="steps" className={styles.h2}>{C.steps.title}</h2>
        <div className={styles.steps} style={{ marginTop: 'var(--space-5)' }}>
          {C.steps.items.map((s) => (
            <Card key={s.heading}>
              <h3 className={styles.h3}>{s.heading}</h3>
              <p className={styles.p}>{s.body}</p>
            </Card>
          ))}
        </div>
      </section>

      <section aria-labelledby="ai" className={styles.prose}>
        <h2 id="ai" className={styles.h2}>{C.ai.title}</h2>
        <div className={styles.two}>
          <Card>
            <h3 className={styles.h3}>It does</h3>
            <ul className={styles.list}>{C.ai.does.map((t) => <li key={t}>{t}</li>)}</ul>
          </Card>
          <Card>
            <h3 className={styles.h3}>It does not</h3>
            <ul className={styles.list}>{C.ai.doesNot.map((t) => <li key={t}>{t}</li>)}</ul>
          </Card>
        </div>
        <p className={styles.note} role="note">{C.ai.status}</p>
      </section>

      <section aria-labelledby="assumptions" className={styles.prose}>
        <h2 id="assumptions" className={styles.h2}>{C.assumptions.title}</h2>
        <ul className={styles.list}>{C.assumptions.items.map((t) => <li key={t}>{t}</li>)}</ul>
      </section>

      <section aria-labelledby="limits" className={styles.prose}>
        <h2 id="limits" className={styles.h2}>{C.limits.title}</h2>
        <ul className={styles.list}>{C.limits.items.map((t) => <li key={t}>{t}</li>)}</ul>
      </section>

      <section aria-labelledby="glossary" className={styles.prose}>
        <h2 id="glossary" className={styles.h2}>{C.glossary.title}</h2>
        <p className={styles.p}>{C.glossary.intro}</p>
        <dl className={styles.terms}>
          {GLOSSARY_TERMS.map((id) => {
            const e = glossary(id);
            if (!e) return null;
            return (
              <div key={id} id={id} className={styles.term}>
                <dt className={styles.termName}><a href={`#${id}`}>{e.label}</a></dt>
                <dd className={styles.def}><span className={styles.defLabel}>{C.glossary.plain}</span>{e.plain}</dd>
                <dd className={styles.def}><span className={styles.defLabel}>{C.glossary.technical}</span>{e.technical}</dd>
              </div>
            );
          })}
        </dl>
      </section>
    </div>
  );
}
