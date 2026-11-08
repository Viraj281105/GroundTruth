import React from 'react';
import { Chip } from '../../../components/ds';
import {
  EVIDENCE_KINDS,
  RECONCILIATION,
  scopeFor,
  SOURCE_COPY,
  type EvidenceKind,
  type EvidenceOrigin,
} from './provenance';
import styles from './provenance.module.css';

const KIND_TONE = { 'real-observation': 'accent', 'synthetic-benchmark': 'sim', 'derived-analysis': 'neutral' } as const;

/** A small label naming the kind of data a section shows. */
export function KindBadge({ kind }: { kind: EvidenceKind }) {
  return (
    <Chip tone={KIND_TONE[kind]} title={EVIDENCE_KINDS[kind].meaning} data-evidence-kind={kind}>
      {EVIDENCE_KINDS[kind].label}
    </Chip>
  );
}

/** Banner above an evidence screen: precomputed synthetic benchmark, or a fresh run. */
export function SourceBanner({ origin, runId }: { origin: EvidenceOrigin; runId: string | null }) {
  const fresh = origin === 'fresh-run';
  return (
    <aside className={styles.banner} role="note" data-evidence-origin={origin}>
      <div className={styles.bannerHead}>
        <KindBadge kind="synthetic-benchmark" />
        {fresh && <KindBadge kind="derived-analysis" />}
        <strong>{fresh ? SOURCE_COPY.freshTitle : SOURCE_COPY.fixtureTitle}</strong>
      </div>
      <p>{fresh ? SOURCE_COPY.freshBody : SOURCE_COPY.fixtureBody}</p>
      {fresh && runId && (
        <p>
          {SOURCE_COPY.runLabel}: <code>{runId}</code>
        </p>
      )}
    </aside>
  );
}

/** Shown in place of a chart the API cannot serve for a fresh run. Never draws a substitute. */
export function VizLimitation() {
  return (
    <p className={styles.limit} role="note" data-viz-unavailable="true">
      {SOURCE_COPY.freshVizLimit}
    </p>
  );
}

/** What is real, what is synthetic, and what is not claimed. Used on every evidence-bearing screen. */
export function EvidenceScope({ caseId, withReconciliation = false }: { caseId: string; withReconciliation?: boolean }) {
  return (
    <section className={styles.scope} aria-label="What this evidence is and is not" data-evidence-scope="true">
      <h2 className={styles.scopeTitle}>What this evidence is and is not</h2>
      <ul className={styles.scopeList}>
        {scopeFor(caseId).map((row) => (
          <li key={row.statement}>
            <Chip
              tone={
                row.kind === 'real-observation' ? 'accent' : row.kind === 'synthetic-benchmark' ? 'sim' : 'caution'
              }
            >
              {row.badge}
            </Chip>
            <span>{row.statement}</span>
          </li>
        ))}
      </ul>
      {withReconciliation && caseId === 'kariba-redd' && (
        <details className={styles.recon}>
          <summary>Why some numbers differ between audit documents</summary>
          <dl>
            {RECONCILIATION.map((r) => (
              <div key={r.id}>
                <dt>{r.label}</dt>
                <dd>{r.explanation}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </section>
  );
}
