import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import { chartSeriesFrom } from '../src/lib/fixtures/simulated-data';
import {
  derivePlaygroundView,
  deriveDonorWeights,
  engineTreatmentYear,
  initialPlaygroundState,
  playgroundReducer,
  reshadeSeries,
  rerunHref,
} from '../src/features/case/playground/playground-model';

const items = KARIBA_COMPLETED.verification.bundle.items;
const series = chartSeriesFrom(KARIBA_COMPLETED);
const engineYear = engineTreatmentYear(items, series) as number;
const years = series.map((p) => p.year);
const base = initialPlaygroundState(engineYear, Math.min(...years), Math.max(...years));

describe('playgroundReducer', () => {
  it('starts at the engine year with nothing excluded', () => {
    expect(base.year).toBe(engineYear);
    expect(base.excluded).toEqual([]);
  });

  it('clamps scrubbed years to the series range and ignores non-numbers', () => {
    expect(playgroundReducer(base, { type: 'setYear', year: 1 }).year).toBe(base.minYear);
    expect(playgroundReducer(base, { type: 'setYear', year: 99999 }).year).toBe(base.maxYear);
    expect(playgroundReducer(base, { type: 'setYear', year: NaN })).toBe(base);
  });

  it('toggles a donor off and back on', () => {
    const off = playgroundReducer(base, { type: 'toggleDonor', id: 'a' });
    expect(off.excluded).toEqual(['a']);
    expect(playgroundReducer(off, { type: 'toggleDonor', id: 'a' }).excluded).toEqual([]);
  });

  it('reset restores the engine specification', () => {
    let s = playgroundReducer(base, { type: 'setYear', year: base.minYear });
    s = playgroundReducer(s, { type: 'toggleDonor', id: 'a' });
    expect(playgroundReducer(s, { type: 'reset' })).toEqual(base);
  });
});

describe('derivePlaygroundView', () => {
  const donors = deriveDonorWeights(items);

  it('shows no re-run need at the engine specification', () => {
    const v = derivePlaygroundView(base, series, donors, items);
    expect(v.changed).toBe(false);
    expect(v.needsRerun).toBe(false);
  });

  it('never invents an estimate for a donor pool the engine did not run', () => {
    const id = donors[0]?.id ?? 'x';
    const v = derivePlaygroundView(playgroundReducer(base, { type: 'toggleDonor', id }), series, donors, items);
    expect(v.needsRerun).toBe(true);
    expect(v.engineEstimate).toBeNull();
    if (donors.length > 0) expect(v.removedWeight).toBe(donors[0].weight);
  });

  it('only shows an estimate for a different year when the engine returned that specification', () => {
    const later = playgroundReducer(base, { type: 'setYear', year: base.maxYear });
    if (later.year !== base.year) {
      const v = derivePlaygroundView(later, series, donors, items);
      expect(v.engineEstimate).toBeNull();
      expect(v.needsRerun).toBe(true);
    }
  });

  it('moves the post-period shading with the scrubbed year', () => {
    const shaded = reshadeSeries(series, base.minYear);
    expect(shaded.filter((p) => p.isPost).length).toBe(series.length - 1);
  });

  it('builds a run link that carries only what changed', () => {
    expect(rerunHref('kariba-redd', base)).toBe('/cases/kariba-redd/run');
    const s = playgroundReducer(playgroundReducer(base, { type: 'setYear', year: base.minYear }), { type: 'toggleDonor', id: 'd1' });
    expect(rerunHref('kariba-redd', s)).toContain('treatment_year=');
    expect(rerunHref('kariba-redd', s)).toContain('exclude_donors=d1');
  });
});
