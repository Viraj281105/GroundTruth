import { API_BASE_URL } from '../../lib/api';
import type { components } from '../../lib/generated/schema';

export type RunItem = components['schemas']['RunItem'];
export type RunListPage = components['schemas']['RunListPage'];

export type RunsResult =
  | { kind: 'ok'; items: RunItem[]; containsSimulated: boolean }
  | { kind: 'not_configured' }
  | { kind: 'unreachable' };

/** GET /runs. 503 means the run store is not configured; anything else that fails is "unreachable". */
export async function fetchRuns(limit = 50): Promise<RunsResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/runs?limit=${limit}`, { headers: { 'Content-Type': 'application/json' } });
    if (res.status === 503) return { kind: 'not_configured' };
    if (!res.ok) return { kind: 'unreachable' };
    const page = (await res.json()) as RunListPage;
    if (!page || !Array.isArray(page.items)) return { kind: 'unreachable' };
    return { kind: 'ok', items: page.items, containsSimulated: Boolean(page.contains_simulated) };
  } catch {
    return { kind: 'unreachable' };
  }
}

export interface DayCount {
  day: string;
  count: number;
}

/** Runs per UTC day, oldest first. Only days that have runs appear; nothing is interpolated. */
export function runsPerDay(items: Pick<RunItem, 'created_at'>[]): DayCount[] {
  const counts = new Map<string, number>();
  for (const it of items) {
    const t = Date.parse(it.created_at);
    if (!Number.isFinite(t)) continue;
    const day = new Date(t).toISOString().slice(0, 10);
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }
  return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, count]) => ({ day, count }));
}

/** Count by result_state, in the order of first appearance in `order`, zero counts dropped. */
export function resultStateCounts(
  items: Pick<RunItem, 'result_state'>[],
  order: RunItem['result_state'][] = ['measured', 'refused', 'failed', 'running', 'queued', 'cancelled'],
): { state: RunItem['result_state']; count: number }[] {
  return order
    .map((state) => ({ state, count: items.filter((i) => i.result_state === state).length }))
    .filter((r) => r.count > 0);
}
