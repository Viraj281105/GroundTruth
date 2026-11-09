import React from 'react';
import { Card, Chip, DataModeBanner, UnavailablePanel } from '../ds';
import { overviewCopy } from '../../features/case/overview/copy';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { readinessItems } from './readiness.model';
import type { PanelProps, VerificationView } from './types';
import styles from './panels.module.css';

type Label = keyof typeof overviewCopy.verdict;
const isLabel = (v: string | null): v is Label => v !== null && Object.prototype.hasOwnProperty.call(overviewCopy.verdict, v);

/**
 * Attribution/verification summary for a project. It reuses the case-overview screening copy
 * (R2 wording) but takes the project `VerificationView`, which the case VerdictPanel cannot.
 */
export function VerdictPanel({ data, loading }: PanelProps<VerificationView>) {
  if (loading) return <PanelLoading label="verification" />;
  if (!data) return <PanelEmpty title="No verification yet" body="Run a verification once the readiness criteria are met." />;
  if (data.status === 'not_estimable' || !isLabel(data.verdict_label)) {
    const unmet = readinessItems(data.readiness).filter((i) => i.state !== 'met' && i.evidenceNeeded);
    return (
      <UnavailablePanel
        title="Screening outcome"
        reason="No completed verification run is available for this project, so no screening outcome is shown."
        evidenceNeeded={unmet.length > 0 ? unmet.map((i) => i.evidenceNeeded).join('; ') : 'A completed real-data verification run.'}
      />
    );
  }
  const v = overviewCopy.verdict[data.verdict_label];
  return (
    <Card className={styles.panel} aria-label="Screening outcome">
      <DataModeBanner mode={data.data_mode} />
      <p className={styles.kicker}>{overviewCopy.verdictKicker}</p>
      <h3 className={styles.title}>{v.title}</h3>
      <p className={styles.lead}>{v.plain}</p>
      {data.verdict_rationale && <p>{data.verdict_rationale}</p>}
      <div className={styles.row}>
        <Chip tone={v.tone === 'caution' ? 'caution' : 'neutral'}>{data.readiness.attribution_ready ? 'Attribution-ready' : 'Not attribution-ready'}</Chip>
        {data.run_id && <Chip>Run {data.run_id}</Chip>}
      </div>
      {data.caveats.length > 0 && (
        <div className={styles.lists}>
          <span className={styles.listLabel}>{overviewCopy.caveatsTitle}</span>
          <ul>
            {data.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {data.warnings.length > 0 && (
        <ul className={styles.muted}>
          {data.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
