import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MOCK_CASE_DETAILS, MOCK_VERIFICATION_RESULTS } from '../src/lib/fixtures/simulated-data';
import { buildFigures, donorWeightBars, effectRange, fitFigure, keyTimeline, lineFigure, placeboFigure } from '../src/features/case/overview/figures';
import { buildMethodModel, shortSource, stageSummary } from '../src/features/case/method/model';
import { stageDurationBars } from '../src/features/run/durations';
import { PipelineLadder } from '../src/features/case/method/PipelineLadder';
import type { StageView } from '../src/lib/jobs';

const fixture = MOCK_VERIFICATION_RESULTS['kariba-redd'];
const items = fixture.verification.bundle.items;

describe('figure data prep', () => {
  it('reads the effect interval only when returned', () => {
    const r = effectRange(items);
    expect(r).not.toBeNull();
    expect(r!.low).toBeLessThanOrEqual(r!.estimate);
    expect(effectRange([])).toBeNull();
    expect(effectRange(undefined)).toBeNull();
  });
  it('gives donuts and donor bars only from evidence present', () => {
    expect(fitFigure(items)?.max).toBeGreaterThan(0);
    expect(placeboFigure(items)?.caption).toContain('rank');
    expect(fitFigure([])).toBeNull();
    expect(placeboFigure([])).toBeNull();
    const bars = donorWeightBars(items);
    expect(bars.length).toBeGreaterThan(0);
    expect(bars.length).toBeLessThanOrEqual(8);
    expect([...bars].sort((a, b) => b.value - a.value)).toEqual(bars);
    expect(donorWeightBars([])).toEqual([]);
  });
  it('builds a line only with two finite points and keeps the treatment marker in range', () => {
    expect(lineFigure([], 2011)).toBeNull();
    const l = lineFigure(fixture.chartSeries, 2011);
    expect(l?.series).toHaveLength(2);
    expect(l?.refX).toBe(2011);
    expect(lineFigure(fixture.chartSeries, 1900)?.refX).toBeUndefined();
  });
  it('sorts and limits the timeline, empty when absent', () => {
    expect(keyTimeline(undefined)).toEqual([]);
    const t = keyTimeline(fixture.timeline, 3);
    expect(t).toHaveLength(3);
    expect(t[0].year).toBeLessThanOrEqual(t[1].year);
  });
  it('buildFigures carries every raw evidence row for the auditor table', () => {
    expect(buildFigures(fixture, 2011).rows).toHaveLength(items.length);
  });
});

describe('method summaries', () => {
  const model = buildMethodModel(MOCK_CASE_DETAILS['kariba-redd'], items, []);
  it('counts evidence per stage and source consistently', () => {
    const total = stageSummary(model.stages).reduce((n, s) => n + s.items, 0);
    expect(total).toBe(items.length);
    expect(model.sourceCounts.reduce((n, s) => n + s.count, 0)).toBe(items.length);
  });
  it('shortens sources', () => {
    expect(shortSource('https://registry.verra.org/app/x')).toBe('registry.verra.org');
    expect(shortSource('groundtruth.platform.datasets.synthetic')).toBe('datasets.synthetic');
  });
  it('renders the ladder without NaN', () => {
    const html = renderToStaticMarkup(<PipelineLadder stages={stageSummary(model.stages)} />);
    expect(html).toContain('Evidence ladder');
    expect(html).not.toContain('NaN');
  });
});

describe('stage durations', () => {
  const st = (name: string, state: StageView['state'], duration_ms: number | null): StageView =>
    ({ name, label: name, state, started_at: null, finished_at: null, duration_ms, elapsed_ms: null }) as StageView;
  it('includes only stages with a reported duration', () => {
    const bars = stageDurationBars([st('ingest', 'done', 1500), st('fit', 'active', null), st('report', 'pending', null)]);
    expect(bars).toHaveLength(1);
    expect(bars[0].display).toBe('1.5 s');
  });
});
