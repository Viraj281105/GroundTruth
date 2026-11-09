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
  return (
    <Card className={styles.panel} aria-label="Recent activity">
      <h3 className={styles.title}>Recent activity</h3>
      <ul className={styles.feed}>
        {rows.map((r) => (
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
    </Card>
  );
}
