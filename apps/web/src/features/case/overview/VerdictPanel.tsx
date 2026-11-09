import React from 'react';
import { Card, Chip } from '../../../components/ds';
import { RefusalDetails } from '../../../components/ds/RefusalDetails';
import { refusalStageLabel } from '../../../lib/refusal';
import type { OverviewModel } from './model';
import { overviewCopy as c } from './copy';
import { NotStory } from './LensCaption';
import styles from './overview.module.css';

/** The verdict, or the designed explanation when there is none (refused / not yet run). */
export function VerdictPanel({ model }: { model: OverviewModel }) {
  if (model.kind === 'refused' && model.refusal) {
    const r = model.refusal;
    return (
      <Card className={styles.panelCaution} role="status">
        <p className={styles.kicker}>{c.verdictKicker}</p>
        <h2 className={styles.verdictTitle}>
          {c.refusedTitle}
          {r.stage ? `: stopped at ${refusalStageLabel(r.stage)}` : ''}
        </h2>
        <p className={styles.lead}>{c.refusedLead}</p>
        <p>{r.message}</p>
        {r.remediation && (
          <p>
            <strong>{c.refusedFix}.</strong> {r.remediation}
          </p>
        )}
        <RefusalDetails refusal={r} />
      </Card>
    );
  }
  if (model.kind === 'not_run' || !model.verdictLabel) {
    return (
      <Card role="status">
        <p className={styles.kicker}>{c.verdictKicker}</p>
        <h2 className={styles.verdictTitle}>{c.notRunTitle}</h2>
        <p className={styles.lead}>{c.notRunBody}</p>
      </Card>
    );
  }
  const v = c.verdict[model.verdictLabel];
  const tone = v.tone === 'caution' ? styles.panelCaution : v.tone === 'accent' ? styles.panelOk : styles.panelNeutral;
  return (
    <Card className={tone}>
      <p className={styles.kicker}>{c.verdictKicker}</p>
      <h2 className={styles.verdictTitle}>{v.title}</h2>
      <p className={styles.lead}>{v.plain}</p>
      {model.divergenceText && (
        <p>
          <Chip tone={v.tone === 'caution' ? 'caution' : 'neutral'}>
            {c.divergenceLabel}: {model.divergenceText}
          </Chip>
        </p>
      )}
      {model.kind === 'inconclusive' && (
        <div className={styles.callout}>
          <strong>{c.inconclusiveTitle}</strong>
          <p>{c.inconclusiveBody}</p>
        </div>
      )}
      {model.rationale && (
        <NotStory>
          <p>
            <strong>{c.rationaleTitle}.</strong> {model.rationale}
          </p>
        </NotStory>
      )}
    </Card>
  );
}
