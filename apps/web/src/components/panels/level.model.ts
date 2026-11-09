export const LEVEL_NAMES = [
  'Not assessable',
  'Basic monitoring',
  'Contextual intelligence',
  'Comparative intelligence',
  'Attribution assessment',
  'Verified impact',
] as const;

export type StepState = 'reached' | 'current' | 'missing';
export interface LadderStep {
  level: number;
  name: string;
  state: StepState;
}

/**
 * The six-step level ladder. The current step shows the name the API sent (including any
 * " (simulated)" suffix); steps above it are "missing" so no view implies a higher level.
 */
export function levelLadder(level: number, levelName: string): { badge: string; level: number; steps: LadderStep[] } {
  const lv = Number.isFinite(level) ? Math.min(5, Math.max(0, Math.floor(level))) : 0;
  return {
    badge: `Level ${lv} · ${levelName}`,
    level: lv,
    steps: LEVEL_NAMES.map((name, i) => ({
      level: i,
      name: i === lv ? levelName : name,
      state: i < lv ? 'reached' : i === lv ? 'current' : 'missing',
    })),
  };
}
