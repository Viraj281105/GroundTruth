import type { BarItem } from '../../components/charts';
import type { StageView } from '../../lib/jobs';
import { stageLabel } from './machine';

function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/**
 * Bars for stages that reported a finished duration. A stage without one (pending,
 * active, skipped) is left out: no duration is estimated.
 */
export function stageDurationBars(stages: readonly StageView[]): BarItem[] {
  return stages
    .filter((s) => typeof s.duration_ms === 'number' && Number.isFinite(s.duration_ms) && s.duration_ms >= 0)
    .map((s) => ({
      label: stageLabel(s.name, s.label),
      value: s.duration_ms as number,
      tone: s.state === 'failed' ? ('caution' as const) : ('accent' as const),
      display: formatMs(s.duration_ms as number),
    }));
}
