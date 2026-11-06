'use client';

import React from 'react';
import { useLens } from '../../../lib/lens';
import type { Lens } from '../../../lib/lens-core';
import { Donut } from '../../../components/charts';
import type { VerificationFixtureData } from '../../../lib/fixtures/simulated-data';
import type { Evidence } from '../../../lib/types';
import { fitDonut, pDonut, type StoryNumber } from './viz-model';
import styles from './viz.module.css';

const LEVELS: Record<Lens, { name: string; shows: string }> = {
  story: { name: 'Story', shows: 'one chart, one sentence and three numbers.' },
  explorer: { name: 'Explorer', shows: 'adds donor weights, the placebo spread, fit checks and the playground.' },
  auditor: { name: 'Auditor', shows: 'adds the residual series, per-donor tables, provenance ids and raw numbers.' },
};

/** States the current detail level and what it reveals; the switch itself lives in the header. */
export function LensCaption() {
  const { lens } = useLens();
  const l = LEVELS[lens];
  return (
    <p className={styles.caption} role="status">
      <strong>{l.name} view</strong> <span>shows {l.shows}</span>
    </p>
  );
}

export function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className={styles.card}>
      <h3 className={styles.cardTitle}>{title}</h3>
      {children}
      {note && <p className={styles.cardNote}>{note}</p>}
    </div>
  );
}

export function BigNumbers({ numbers }: { numbers: StoryNumber[] }) {
  if (numbers.length === 0) return <p className={styles.cardNote}>Headline numbers are not available for this analysis.</p>;
  return (
    <div className={styles.big}>
      {numbers.map((n) => (
        <div key={n.label} className={styles.bigItem}>
          <span className={styles.bigValue}>{n.value}</span>
          <span className={styles.bigLabel}>{n.label}</span>
          {n.note && <span className={styles.cardNote}>{n.note}</span>}
        </div>
      ))}
    </div>
  );
}

export function FitAndPDonuts({ items, viz }: { items: Evidence[]; viz: VerificationFixtureData | null }) {
  const fit = fitDonut(items);
  const p = pDonut(items, viz?.placebos);
  if (!fit && !p) return <p className={styles.cardNote}>Fit and placebo summaries are not available for this analysis.</p>;
  return (
    <div className={styles.donuts}>
      {fit && (
        <Donut
          value={fit.value}
          max={fit.gate}
          tone={fit.passes ? 'accent' : 'caution'}
          label={`Pre-period error ${fit.value} against the engine gate of ${fit.gate}`}
          caption={`Pre-period error vs gate ${fit.gate} (lower is better)`}
        />
      )}
      {p && (
        <Donut
          value={p.p}
          max={1}
          tone={p.significant === false ? 'caution' : 'accent'}
          label={`Placebo p-value ${p.p}`}
          caption={p.level === undefined ? 'Placebo p-value' : `Placebo p-value (level ${p.level})`}
        />
      )}
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = { baseline: 'Baseline', crediting: 'Crediting', sensor: 'Sensor', disturbance: 'Disturbance' };

export function TimelineStrip({ events }: { events: VerificationFixtureData['timeline'] }) {
  if (events.length === 0) return <p className={styles.cardNote}>No timeline events were provided.</p>;
  return (
    <ol className={styles.strip} aria-label="Project timeline">
      {[...events]
        .sort((a, b) => a.year - b.year)
        .map((e) => (
          <li key={`${e.year}-${e.title}`} className={styles.stripItem}>
            <span className={styles.stripYear}>{e.year}</span>
            <strong>{e.title}</strong>
            <span>{TYPE_LABEL[e.type] ?? e.type}</span>
          </li>
        ))}
    </ol>
  );
}
