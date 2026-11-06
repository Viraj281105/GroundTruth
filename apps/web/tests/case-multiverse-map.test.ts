import { describe, expect, it } from 'vitest';
import { KARIBA_COMPLETED } from '../src/lib/fixtures/generated';
import { deriveSpecCurve } from '../src/lib/spec-curve';
import { NO_FILTER, countByDimension, dimensionsOf, filterSpecs } from '../src/features/case/robustness/spec-filter';
import { loadBoundary, modelFromGeoJson, weightOpacity } from '../src/features/case/map/map-model';

import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import { DonorMapView } from '../src/features/case/map/DonorMap';

describe('DonorMapView', () => {
  it('shows a designed empty state, not a map, when the boundary is 404', () => {
    const html = renderToStaticMarkup(React.createElement(DonorMapView, { result: { kind: 'empty', reason: 'not-found' } }));
    expect(html).toMatch(/No project boundary has been published/);
  });
  it('shows a visible error when the API is unreachable', () => {
    const html = renderToStaticMarkup(React.createElement(DonorMapView, { result: { kind: 'error', message: 'down' } }));
    expect(html).toMatch(/role="alert"/);
  });
});

const curve = deriveSpecCurve(KARIBA_COMPLETED.verification.bundle.items);

describe('spec-curve filtering', () => {
  it('returns every specification with no filter', () => {
    expect(filterSpecs(curve!.estimates, NO_FILTER)).toHaveLength(curve!.estimates.length);
  });

  it('filters to one analytic choice and keeps the centre as the reference', () => {
    const dim = dimensionsOf(curve!.estimates)[0];
    const out = filterSpecs(curve!.estimates, { dimension: dim, flipsOnly: false });
    expect(out.every((s) => s.dimension === dim || s.isCentre)).toBe(true);
    expect(out.filter((s) => !s.isCentre)).toHaveLength(countByDimension(curve!.estimates)[dim]);
  });

  it('flips-only returns only sign-flipping specifications', () => {
    const out = filterSpecs(curve!.estimates, { dimension: null, flipsOnly: true });
    expect(out.every((s) => s.flipsSign)).toBe(true);
  });
});

describe('boundary loading', () => {
  const resp = (status: number, body?: unknown) =>
    (async () => new Response(body === undefined ? null : JSON.stringify(body), { status })) as unknown as typeof fetch;

  it('renders the empty state when the boundary is 404', async () => {
    expect(await loadBoundary('http://x', 'c', resp(404))).toEqual({ kind: 'empty', reason: 'not-found' });
  });

  it('reports an unreachable API as an error, not an empty state', async () => {
    const failing = (async () => {
      throw new Error('down');
    }) as unknown as typeof fetch;
    expect((await loadBoundary('http://x', 'c', failing)).kind).toBe('error');
  });

  it('computes bbox and centroid from geometry', () => {
    const r = modelFromGeoJson({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 4], [0, 4], [0, 0]]] } }],
    });
    expect(r.kind).toBe('ok');
    if (r.kind === 'ok') {
      expect(r.model.bbox).toEqual([0, 0, 2, 4]);
      expect(r.model.centroid).toEqual([1, 2]);
      expect(r.model.donorWeights).toEqual([]);
    }
  });

  it('only shades donors that carry a role and a numeric weight', () => {
    const poly = { type: 'Point', coordinates: [1, 1] };
    const r = modelFromGeoJson({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: { role: 'project' }, geometry: poly },
        { type: 'Feature', properties: { role: 'donor', weight: 0.3, name: 'd' }, geometry: poly },
        { type: 'Feature', properties: { role: 'donor' }, geometry: poly },
      ],
    });
    expect(r.kind === 'ok' && r.model.donorWeights).toEqual([{ index: 1, weight: 0.3, name: 'd' }]);
    expect(weightOpacity(0.3, 0.3)).toBeCloseTo(0.85);
  });

  it('treats empty geometry as an empty state', () => {
    expect(modelFromGeoJson({ type: 'FeatureCollection', features: [] })).toEqual({ kind: 'empty', reason: 'no-geometry' });
  });
});
