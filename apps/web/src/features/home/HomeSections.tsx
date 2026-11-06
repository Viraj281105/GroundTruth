import React from 'react';
import { Card, LinkButton, Tooltip } from '../../components/ds';
import { glossary } from '../../lib/glossary';
import type { CaseSummary } from '../../lib/types';
import { CaseCard } from '../cases/CaseCard';
import { homeCopy as c } from './copy';
import styles from './HomeSections.module.css';

export function HowItWorks() {
  return (
    <section className={`gt-container ${styles.section}`} id="how" aria-labelledby="how-title">
      <h2 id="how-title">{c.howTitle}</h2>
      <ol className={styles.steps}>
        {c.steps.map((s, i) => {
          const g = glossary(s.term);
          return (
            <li key={s.term}>
              <Card>
                <span className={styles.num} aria-hidden="true">{i + 1}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                {g && (
                  <p className={styles.term}>
                    <Tooltip text={g.plain}>{g.label}</Tooltip>
                  </p>
                )}
              </Card>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function FeaturedCases({ cases, failed }: { cases: CaseSummary[]; failed: boolean }) {
  return (
    <section className={`gt-container ${styles.section}`} aria-labelledby="featured-title">
      <div className={styles.row}>
        <h2 id="featured-title">{c.featuredTitle}</h2>
        <LinkButton href="/cases" variant="ghost">{c.allCases}</LinkButton>
      </div>
      {failed ? (
        <p role="alert" className={styles.fail}>{c.featuredError}</p>
      ) : (
        <div className={styles.grid}>
          {cases.slice(0, 3).map((x) => <CaseCard key={x.case_id} item={x} />)}
        </div>
      )}
    </section>
  );
}

export function StatusLine() {
  return <p className={`gt-container ${styles.status}`}>{c.status}</p>;
}
