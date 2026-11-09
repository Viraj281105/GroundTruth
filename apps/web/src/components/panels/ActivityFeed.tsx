import React from 'react';
import { Card, Chip } from '../ds';
import { PanelEmpty, PanelLoading } from './PanelStates';
import { activityRows } from './activity.model';
import type { ActivityItem } from './types';
import styles from './panels.module.css';

export function ActivityFeed({ items, loading }: { items?: readonly ActivityItem[] | null; loading?: boolean }) {
  if (loading) return <PanelLoading label="activity" />;
  if (!items || items.length === 0) return <PanelEmpty title="No recent activity" body="Project, run and export events appear here." />;
  const rows = activityRows(items);
  const initialCount = 4;
  const initialRows = rows.slice(0, initialCount);
  const remainingRows = rows.slice(initialCount);
  return (
    <Card className={styles.panel} aria-label="Recent activity">
      <div className={styles.head}>
        <h3 className={styles.title}>Recent activity</h3>
        <span className={styles.muted}>{rows.length} total events</span>
      </div>
      <ul className={styles.feed}>
        {initialRows.map((r) => (
          <li key={r.id} className={styles.feedItem} data-activity-kind={r.kind}>
            <div className={styles.stack}>
              <span className={styles.row}>
                <span className={styles.mono}>{r.action}</span>
                <Chip tone={r.outcome === 'success' ? 'neutral' : 'caution'}>{r.outcome}</Chip>
                {!r.own && <Chip>Shared project</Chip>}
              </span>
              {r.project && <span className={styles.muted}>{r.project}</span>}
            </div>
            <time className={styles.when} dateTime={r.occurredAt}>
              {r.occurredAt.slice(0, 16).replace('T', ' ')} UTC
            </time>
          </li>
        ))}
      </ul>
      {remainingRows.length > 0 && (
        <details className={styles.collapsibleBlock}>
          <summary className={styles.collapsibleSummary}>
            <span>View older events ({remainingRows.length} more)</span>
          </summary>
          <div className={styles.collapsibleContent}>
            <ul className={styles.feed}>
              {remainingRows.map((r) => (
                <li key={r.id} className={styles.feedItem} data-activity-kind={r.kind}>
                  <div className={styles.stack}>
                    <span className={styles.row}>
                      <span className={styles.mono}>{r.action}</span>
                      <Chip tone={r.outcome === 'success' ? 'neutral' : 'caution'}>{r.outcome}</Chip>
                      {!r.own && <Chip>Shared project</Chip>}
                    </span>
                    {r.project && <span className={styles.muted}>{r.project}</span>}
                  </div>
                  <time className={styles.when} dateTime={r.occurredAt}>
                    {r.occurredAt.slice(0, 16).replace('T', ' ')} UTC
                  </time>
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </Card>
  );
}
