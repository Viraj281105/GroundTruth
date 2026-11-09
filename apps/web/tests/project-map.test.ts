import { describe, expect, it } from 'vitest';
import { basemapStyle, boundaryUrlFor, donorsUrlFor, fitBoundsFor } from '../src/components/map/geo';

// Extents of cases/boundaries/kariba-redd.geojson (lon 27.6257..31.1451, lat -17.7129..-15.6253).
const W = 27.62576193948661;
const E = 31.14510220919165;
const S = -17.71287498652449;
const N = -15.62525449886945;
const ring = [[W, S], [E, S], [E, N], [W, N], [W, S]];
const polygon = { type: 'Polygon', coordinates: [ring] };

describe('fitBoundsFor', () => {
  it('returns the Kariba bbox for a Polygon', () => {
    expect(fitBoundsFor(polygon)).toEqual([[W, S], [E, N]]);
  });
  it('handles MultiPolygon', () => {
    const mp = { type: 'MultiPolygon', coordinates: [[ring.slice(0, 3).concat([ring[0]])], [[[E, N], [E - 1, N], [E - 1, N - 1], [E, N]]]] };
    expect(fitBoundsFor(mp)).toEqual([[W, S], [E, N]]);
  });
  it('handles Feature and FeatureCollection', () => {
    const f = { type: 'Feature', properties: {}, geometry: polygon };
    expect(fitBoundsFor(f)).toEqual([[W, S], [E, N]]);
    expect(fitBoundsFor({ type: 'FeatureCollection', features: [f] })).toEqual([[W, S], [E, N]]);
  });
  it('throws a clear error on empty geometry', () => {
    expect(() => fitBoundsFor({ type: 'FeatureCollection', features: [] })).toThrow(/no geometry/i);
    expect(() => fitBoundsFor({ type: 'Polygon', coordinates: [] })).toThrow(/no geometry/i);
  });
});

describe('basemapStyle', () => {
  it('is the OpenFreeMap liberty style', () => {
    expect(basemapStyle()).toBe('https://tiles.openfreemap.org/styles/liberty');
  });
});

describe('fitBoundsFor validation', () => {
  it('rejects NaN, Infinity and out-of-range coordinates', () => {
    expect(() => fitBoundsFor({ type: 'Point', coordinates: [NaN, 1] })).toThrow(/non-finite/);
    expect(() => fitBoundsFor({ type: 'Point', coordinates: [1, Infinity] })).toThrow(/non-finite/);
    expect(() => fitBoundsFor({ type: 'Point', coordinates: [10, 95] })).toThrow(/out of range/);
    expect(() => fitBoundsFor({ type: 'Point', coordinates: [190, 10] })).toThrow(/out of range/);
  });
  it('documents: antimeridian-crossing geometry yields a world-wide bbox', () => {
    const g = { type: 'LineString', coordinates: [[179, 0], [-179, 1]] };
    expect(fitBoundsFor(g)).toEqual([[-179, 0], [179, 1]]);
  });
});

describe('project urls', () => {
  it('build encoded project endpoints', () => {
    expect(boundaryUrlFor('a b')).toMatch(/\/projects\/a%20b\/boundary\.geojson$/);
    expect(donorsUrlFor('p1')).toMatch(/\/projects\/p1\/donors\.geojson$/);
  });
});

import { fitBoundsForAll, settleBoundaries } from '../src/components/map/geo';

describe('multi-boundary helpers', () => {
  it('settleBoundaries skips failed (null) boundaries and counts them', () => {
    expect(settleBoundaries([null, polygon, null])).toEqual({ ok: [polygon], failed: 2 });
    expect(settleBoundaries([])).toEqual({ ok: [], failed: 0 });
  });
  it('fitBoundsForAll unions boxes and throws when empty', () => {
    const small = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] };
    expect(fitBoundsForAll([polygon, small])).toEqual([[0, S], [E, 1]]);
    expect(() => fitBoundsForAll([])).toThrow(/no geometry/i);
  });
});
