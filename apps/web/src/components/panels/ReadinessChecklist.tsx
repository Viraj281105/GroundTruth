import React from 'react';
import { Card } from '../ds';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { readinessItems } from './readiness.model';
import type { PanelProps, ReadinessBody } from './types';
import styles from './panels.module.css';

const MARK = { met: '✓', not_met: '✕', unavailable: '?' } as const;

export function ReadinessChecklist({ data, loading }: PanelProps<ReadinessBody>) {
  if (loading) return <PanelLoading label="readiness" />;
  if (!data) return <PanelEmpty title="Readiness not computed" body="Readiness is computed from the project's stored evidence." />;
  const items = readinessItems(data);
  return (
    <Card className={styles.panel} aria-label="Attribution readiness">
      <div className={styles.head}>
        <h3 className={styles.title}>Attribution readiness</h3>
        <span className={styles.muted}>{data.attribution_ready ? 'Ready for attribution' : 'Not ready for attribution'}</span>
      </div>
      {items.length === 0 ? (
        <p className={styles.notice}>No readiness criteria were reported.</p>
      ) : (
        <ul className={styles.checks}>
          {items.map((i) => (
            <li key={i.id} className={`${styles.check} ${styles[i.state]}`} data-criterion-state={i.state}>
              <span className={styles.checkMark} aria-hidden="true">
                {MARK[i.state] ?? '?'}
              </span>
              <div className={styles.stack}>
                <div>
                  <strong>{i.name}</strong> <span className={styles.muted}>{i.stateLabel}</span>
                </div>
                <span className={styles.muted}>
                  Observed {i.observed}; required {i.required}
                </span>
                {i.state !== 'met' && i.evidenceNeeded && (
                  <span className={styles.need}>
                    <b>Evidence needed</b>
                    {i.evidenceNeeded}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
