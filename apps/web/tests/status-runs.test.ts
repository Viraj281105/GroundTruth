import { describe, expect, it } from 'vitest';
import { resultStateCounts, runsPerDay } from '../src/features/status/runs';

describe('runs prep', () => {
  it('groups by UTC day, oldest first, skipping bad dates', () => {
    const out = runsPerDay([
      { created_at: '2026-01-02T10:00:00Z' },
      { created_at: '2026-01-01T23:59:00Z' },
      { created_at: '2026-01-02T01:00:00Z' },
      { created_at: 'nope' },
    ]);
    expect(out).toEqual([{ day: '2026-01-01', count: 1 }, { day: '2026-01-02', count: 2 }]);
  });
  it('drops zero counts', () => {
    expect(resultStateCounts([{ result_state: 'refused' }, { result_state: 'refused' }, { result_state: 'measured' }])).toEqual([
      { state: 'measured', count: 1 },
      { state: 'refused', count: 2 },
    ]);
  });
  it('returns nothing for no runs', () => {
    expect(runsPerDay([])).toEqual([]);
  });
});
