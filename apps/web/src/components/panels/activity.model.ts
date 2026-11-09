import type { ActivityItem } from './types';

export type ActivityKind = 'project' | 'run' | 'export' | 'other';
export interface ActivityRow {
  id: string;
  kind: ActivityKind;
  action: string;
  occurredAt: string;
  outcome: string;
  project: string | null;
  own: boolean;
}

export function activityRows(items: readonly ActivityItem[]): ActivityRow[] {
  return items.map((a) => {
    const head = a.action.split('.')[0];
    return {
      id: a.id,
      kind: head === 'project' || head === 'run' || head === 'export' ? head : 'other',
      action: a.action,
      occurredAt: a.occurred_at,
      outcome: a.outcome,
      project: a.project_name ?? a.project_slug ?? null,
      own: a.own,
    };
  });
}
