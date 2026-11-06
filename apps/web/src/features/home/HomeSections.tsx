import React from 'react';
import { Card, LinkButton, Tooltip } from '../../components/ds';
import { glossary } from '../../lib/glossary';
import type { CaseSummary } from '../../lib/types';
import { Sparkline } from '../../components/charts';
import { StepArt } from './StepArt';
import type { CaseViz } from '../cases/viz';
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
                <StepArt step={i as 0 | 1 | 2} />
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

export function FeaturedStrip({ name, caseId, viz }: { name: string; caseId: string; viz: CaseViz }) {
  const nums: { k: string; v: string }[] = [];
  if (viz.effect !== null) nums.push({ k: c.stripEffect, v: `${viz.effect.toFixed(3)}${viz.indicator ? ` ${viz.indicator.toUpperCase()}` : ''}` });
  if (viz.donorsAdmitted !== null) nums.push({ k: c.stripDonors, v: viz.donorsCandidates !== null ? `${viz.donorsAdmitted} of ${viz.donorsCandidates}` : String(viz.donorsAdmitted) });
  if (viz.placeboP !== null) nums.push({ k: c.stripP, v: viz.placeboP.toFixed(3) });
  return (
    <section className={`gt-container ${styles.strip}`} aria-labelledby="strip-title">
      <div className={styles.stripBody}>
        <p className={styles.stripKicker}>{c.stripKicker}</p>
        <h2 id="strip-title">{name}</h2>
        <dl className={styles.stripNums}>
          {nums.map((n) => <div key={n.k}><dt>{n.k}</dt><dd className="num">{n.v}</dd></div>)}
        </dl>
        <LinkButton href={`/cases/${caseId}`} variant="secondary">{c.stripOpen}</LinkButton>
      </div>
      <div className={styles.stripChart}>
        <Sparkline values={viz.observed} tone="observed" height={72} label={`Observed series for ${name}, simulated`} />
        <p className={styles.stripNote}>{c.stripNote}</p>
      </div>
    </section>
  );
}

export function FeaturedCases({ cases, failed, series = {} }: { cases: CaseSummary[]; failed: boolean; series?: Record<string, number[]> }) {
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
          {cases.slice(0, 3).map((x) => <CaseCard key={x.case_id} item={x} series={series[x.case_id]} />)}
        </div>
      )}
    </section>
  );
}

export function StatusLine() {
  return <p className={`gt-container ${styles.status}`}>{c.status}</p>;
}
