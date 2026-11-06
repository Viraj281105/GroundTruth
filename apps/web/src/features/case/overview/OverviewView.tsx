import React from 'react';
import { Card, LinkButton, Stat, Tooltip } from '../../../components/ds';
import { Lens } from '../../../lib/lens';
import { glossary } from '../../../lib/glossary';
import type { OverviewModel } from './model';
import { MiniChart } from './MiniChart';
import { VerdictPanel } from './VerdictPanel';
import { overviewCopy as c } from './copy';
import styles from './overview.module.css';

/** Hint text plus a glossary tooltip explaining the term in plain language. */
function Hint({ text, id }: { text: string; id: string }) {
  const entry = glossary(id);
  return (
    <>
      {text}
      {entry && (
        <>
          {' '}
          <Tooltip text={entry.plain}>{c.whatIsThis}</Tooltip>
        </>
      )}
    </>
  );
}

export function OverviewView({ caseId, model }: { caseId: string; model: OverviewModel }) {
  const base = `/cases/${encodeURIComponent(caseId)}`;
  const hasResult = model.kind === 'measured' || model.kind === 'inconclusive';
  return (
    <div className={`gt-container ${styles.page}`}>
      <VerdictPanel model={model} />

      {hasResult && (
        <div className={styles.grid}>
          <Card>
            <h2 className={styles.h2}>{c.headlineTitle}</h2>
            {model.headline ? (
              <>
                <p className={styles.plain}>{model.headline.plain}</p>
                <Lens show="explorer">
                  <p className={`${styles.bigNum} num`}>{model.headline.valueText}</p>
                  {model.headline.intervalText && <p className={`${styles.muted} num`}>{model.headline.intervalText}</p>}
                </Lens>
              </>
            ) : (
              <p className={styles.muted}>{c.notMeasured}</p>
            )}
          </Card>
          <Card>
            <h2 className={styles.h2}>{c.chartTitle}</h2>
            <MiniChart chart={model.chart} />
          </Card>
        </div>
      )}

      {hasResult && (
        <Lens show="explorer">
          <section aria-labelledby="facts-h">
            <h2 id="facts-h" className={styles.h2}>
              {c.factsTitle}
            </h2>
            <div className={styles.facts}>
              <Card>
                <Stat label={c.factDonors} value={model.facts.donors} hint={<Hint text={c.factDonorsHint} id="donor-pool" />} />
              </Card>
              <Card>
                <Stat label={c.factFit} value={model.facts.fit} hint={<Hint text={c.factFitHint} id="pre-fit" />} />
              </Card>
              <Card>
                <Stat label={c.factPlacebo} value={model.facts.placebo} hint={<Hint text={c.factPlaceboHint} id="p-value" />} />
              </Card>
            </div>
          </section>
        </Lens>
      )}

      {hasResult && model.caveats.length > 0 && (
        <Card tone="sunken">
          <h2 className={styles.h2}>{c.caveatsTitle}</h2>
          <ul className={styles.list}>
            {model.caveats.map((cv) => (
              <li key={cv}>{cv}</li>
            ))}
          </ul>
        </Card>
      )}

      <Card tone="sunken">
        <h2 className={styles.h2}>{c.meaningTitle}</h2>
        <ul className={styles.list}>
          {c.meaning.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </Card>

      <Lens show="auditor">
        {model.provenance && (
          <Card>
            <h2 className={styles.h2}>{c.provenanceTitle}</h2>
            <dl className={styles.dl}>
              <dt>{c.runId}</dt>
              <dd>{model.provenance.runId}</dd>
              <dt>{c.specHash}</dt>
              <dd>{model.provenance.specHash}</dd>
              <dt>{c.dataMode}</dt>
              <dd>{model.provenance.dataMode}</dd>
              <dt>{c.engineVersion}</dt>
              <dd>{model.provenance.engineVersion}</dd>
              <dt>{c.contractVersion}</dt>
              <dd>{model.provenance.contractVersion}</dd>
              <dt>{c.evidenceCount}</dt>
              <dd>{model.provenance.evidenceCount}</dd>
            </dl>
          </Card>
        )}
      </Lens>

      <section aria-labelledby="next-h">
        <h2 id="next-h" className={styles.h2}>
          {c.nextTitle}
        </h2>
        <div className={styles.actions}>
          <LinkButton href={`${base}/run`} size="lg">
            {c.nextRun}
          </LinkButton>
          <LinkButton href={`${base}/evidence`} variant="secondary" size="lg">
            {c.nextEvidence}
          </LinkButton>
          <LinkButton href={`${base}/method`} variant="ghost" size="lg">
            {c.nextMethod}
          </LinkButton>
        </div>
      </section>
    </div>
  );
}
