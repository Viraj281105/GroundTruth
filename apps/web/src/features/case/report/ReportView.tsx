import React from 'react';
import { Card, EmptyState, LinkButton } from '../../../components/ds';
import { NarrativeReport } from '../../../components/scientific/NarrativeReport';
import { CopyCitation } from './CopyCitation';
import { PRINT_CSS } from './citation';
import styles from './report.module.css';

export const reportCopy = {
  noRunTitle: 'No report yet',
  noRunBody: 'A narrative report is produced by an analysis run. Run the analysis for this case to generate one.',
  runAction: 'Run analysis',
  citationTitle: 'Cite this report',
  print: 'Use your browser print dialog (Ctrl or Cmd + P) to save this page as a PDF.',
};

export interface ReportData {
  markdown: string | null;
  generator: string | null;
  citation: string;
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
      <NarrativeReport markdown={report.markdown} generator={report.generator} />
      <Card tone="sunken">
        <h2 className={styles.h2}>{c.citationTitle}</h2>
        <p className={styles.citation}>{report.citation}</p>
        <div className={styles.actions} data-print="hide">
          <CopyCitation citation={report.citation} />
          <span className={styles.muted}>{c.print}</span>
        </div>
      </Card>
    </div>
  );
}
