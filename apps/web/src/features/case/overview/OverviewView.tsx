'use client';

import React from 'react';
import { Card, LinkButton, Stat, Tooltip } from '../../../components/ds';
import { BarList, Donut, LineChart, RangeBar } from '../../../components/charts';
import { Lens } from '../../../lib/lens';
import { glossary } from '../../../lib/glossary';
import type { OverviewModel } from './model';
import { VerdictPanel } from './VerdictPanel';
import { LensCaption, NotStory, StoryOnly } from './LensCaption';
import { overviewCopy as c } from './copy';
import { EvidenceScope, SourceBanner } from '../evidence/EvidenceProvenance';
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
  const fig = model.figures;
  const hasResult = model.kind === 'measured' || model.kind === 'inconclusive';
  return (
    <div className={`gt-container ${styles.page}`}>
      <LensCaption />
      <VerdictPanel model={model} />
      {hasResult && <SourceBanner origin="precomputed-fixture" runId={null} />}

      {hasResult && (
        <StoryOnly>
          <section aria-label="Key numbers" className={styles.bigNums}>
            {[
              { label: c.headlineTitle, value: model.headline?.valueText ?? c.notMeasured },
              { label: c.factFit, value: model.facts.fit },
              { label: c.factPlacebo, value: model.facts.placebo },
            ].map((n) => (
              <Card key={n.label} className={styles.bigStat}>
                <p className={styles.muted}>{n.label}</p>
                <p className={`${styles.bigNum} num`}>{n.value}</p>
              </Card>
            ))}
          </section>
        </StoryOnly>
      )}

      {hasResult && (
        <div className={styles.grid}>
          <NotStory>
            <Card>
              <h2 className={styles.h2}>{c.headlineTitle}</h2>
              {model.headline ? (
                <>
                  <p className={styles.plain}>{model.headline.plain}</p>
                  <p className={`${styles.bigNum} num`}>{model.headline.valueText}</p>
                  {fig.range ? (
                    <>
                      <RangeBar estimate={fig.range.estimate} low={fig.range.low} high={fig.range.high} unit={fig.range.unit} label={`Headline effect with its ${fig.range.kind} interval`} />
                      <p className={styles.figCaption}>Zero marks no change. The bar is the {fig.range.kind} range.</p>
                    </>
                  ) : (
                    model.headline.intervalText && <p className={`${styles.muted} num`}>{model.headline.intervalText}</p>
                  )}
                </>
              ) : (
                <p className={styles.muted}>{c.notMeasured}</p>
              )}
            </Card>
          </NotStory>
          <Card>
            <h2 className={styles.h2}>{c.chartTitle}</h2>
            {fig.line ? (
              <LineChart series={fig.line.series} refX={fig.line.refX} refLabel="Project start" label={c.chartDesc} height={260} />
            ) : (
              <p className={styles.muted}>{c.chartNone}</p>
            )}
          </Card>
        </div>
      )}

      {hasResult && (fig.fit || fig.placebo || fig.donors.length > 0) && (
        <Lens show="explorer">
          <div className={styles.grid}>
            {(fig.fit || fig.placebo) && (
              <Card>
                <h2 className={styles.h2}>{c.checksTitle}</h2>
                <div className={styles.donuts}>
                  {fig.fit && <Donut value={fig.fit.value} max={fig.fit.max} tone={fig.fit.tone} caption={fig.fit.caption} label={`Pre-period error ${fig.fit.value} against a gate of ${fig.fit.max}`} />}
                  {fig.placebo && <Donut value={fig.placebo.value} max={fig.placebo.max} tone={fig.placebo.tone} caption={fig.placebo.caption} label={`Placebo p-value ${fig.placebo.value}`} />}
                </div>
              </Card>
            )}
            {fig.donors.length > 0 && (
              <Card>
                <h2 className={styles.h2}>{c.donorsTitle}</h2>
                <BarList items={fig.donors} label="Largest donor weights in the comparison" />
              </Card>
            )}
          </div>
        </Lens>
      )}

      {hasResult && fig.timeline.length > 0 && (
        <Lens show="explorer">
          <Card>
            <h2 className={styles.h2}>{c.timelineTitle}</h2>
            <ul className={styles.timeline}>
              {fig.timeline.map((t) => (
                <li key={`${t.year}${t.title}`}>
                  <span className={styles.tlYear}>{t.year}</span>
                  <strong>{t.title}</strong>
                  <Lens show="auditor">
                    <span className={styles.muted}> {t.description}</span>
                  </Lens>
                </li>
              ))}
            </ul>
          </Card>
        </Lens>
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

      {hasResult && <EvidenceScope caseId={caseId} withReconciliation />}

      <NotStory>
        <Card tone="sunken">
          <h2 className={styles.h2}>{c.meaningTitle}</h2>
          <ul className={styles.list}>
            {c.meaning.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </Card>
      </NotStory>

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
        {fig.rows.length > 0 && (
          <Card>
            <h2 className={styles.h2}>{c.rawTitle}</h2>
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Evidence id</th>
                    <th>Value</th>
                    <th>Stage</th>
                    <th>Method</th>
                  </tr>
                </thead>
                <tbody>
                  {fig.rows.map((r) => (
                    <tr key={r.id}>
                      <td><code>{r.id}</code></td>
                      <td className="num">{r.value}</td>
                      <td>{r.stage}</td>
                      <td><code>{r.method}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
