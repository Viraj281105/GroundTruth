'use client';

import React from 'react';
import { Card, EmptyState, LinkButton } from '../../../components/ds';
import { NarrativeReport } from '../../../components/scientific/NarrativeReport';
import { LineChart, RangeBar } from '../../../components/charts';
import { Lens } from '../../../lib/lens';
import type { OverviewModel } from '../overview/model';
import { overviewCopy } from '../overview/copy';
import { LensCaption, NotStory, StoryOnly } from '../overview/LensCaption';
import { CopyCitation } from './CopyCitation';
import { PRINT_CSS } from './citation';
import styles from './report.module.css';

export const reportCopy = {
  noRunTitle: 'No report yet',
  noRunBody: 'A narrative report is produced by an analysis run. Run the analysis for this case to generate one.',
  runAction: 'Run analysis',
  citationTitle: 'Cite this report',
  figures: 'Figures for this report',
  noFigures: 'No figures are available for this report: the run returned no effect interval or time series.',
  print: 'Use your browser print dialog (Ctrl or Cmd + P) to save this page as a PDF.',
};

export interface ReportData {
  markdown: string | null;
  generator: string | null;
  citation: string;
  /** Numbers and series for the figure strip; null figures render an honest empty state. */
  overview: OverviewModel | null;
}

function FigureStrip({ overview }: { overview: OverviewModel | null }) {
  const fig = overview?.figures;
  if (!overview || !fig || (!fig.range && !fig.line)) {
    return (
      <Card tone="sunken" role="status">
        <p className={styles.muted}>{reportCopy.noFigures}</p>
      </Card>
    );
  }
  const verdict = overview.verdictLabel ? overviewCopy.verdict[overview.verdictLabel].plain : null;
  return (
    <section aria-label={reportCopy.figures} className={styles.strip}>
      <StoryOnly>
        {verdict && <p className={styles.lead}>{verdict}</p>}
      </StoryOnly>
      <div className={styles.stripGrid}>
        <NotStory>
          {fig.range && (
            <Card>
              <h2 className={styles.h2}>{overviewCopy.headlineTitle}</h2>
              <RangeBar estimate={fig.range.estimate} low={fig.range.low} high={fig.range.high} unit={fig.range.unit} label={`Headline effect with its ${fig.range.kind} interval`} />
            </Card>
          )}
        </NotStory>
        {fig.line && (
          <Card>
            <h2 className={styles.h2}>{overviewCopy.chartTitle}</h2>
            <LineChart series={fig.line.series} refX={fig.line.refX} refLabel="Project start" label={overviewCopy.chartDesc} height={220} />
          </Card>
        )}
      </div>
      <StoryOnly>
        <div className={styles.bigNums}>
          {[
            { label: overviewCopy.headlineTitle, value: overview.headline?.valueText ?? overviewCopy.notMeasured },
            { label: overviewCopy.factFit, value: overview.facts.fit },
            { label: overviewCopy.factPlacebo, value: overview.facts.placebo },
          ].map((n) => (
            <Card key={n.label}>
              <p className={styles.muted}>{n.label}</p>
              <p className={`${styles.bigNum} num`}>{n.value}</p>
            </Card>
          ))}
        </div>
      </StoryOnly>
    </section>
  );
}

export function ReportView({ caseId, report }: { caseId: string; report: ReportData | null }) {
  const c = reportCopy;
  if (!report) {
    return (
      <div className="gt-container" style={{ paddingBlock: 'var(--space-12)' }}>
        <EmptyState
          title={c.noRunTitle}
          body={c.noRunBody}
          action={<LinkButton href={`/cases/${encodeURIComponent(caseId)}/run`}>{c.runAction}</LinkButton>}
        />
      </div>
    );
  }
  return (
    <div className={`gt-container ${styles.page}`}>
      <style>{PRINT_CSS}</style>
      <LensCaption />
      <FigureStrip overview={report.overview} />
      <Lens show="explorer">
        <NarrativeReport markdown={report.markdown} generator={report.generator} />
        <Card tone="sunken">
          <h2 className={styles.h2}>{c.citationTitle}</h2>
          <p className={styles.citation}>{report.citation}</p>
          <div className={styles.actions} data-print="hide">
            <CopyCitation citation={report.citation} />
            <span className={styles.muted}>{c.print}</span>
          </div>
        </Card>
      </Lens>
    </div>
  );
}
