/** Pure map helpers (no WebGL), unit-testable under jsdom. */

export const BASEMAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/liberty';

import { getPublicApiUrl } from '../../lib/api';

export function boundaryUrlFor(projectId: string): string {
  return `${getPublicApiUrl()}/projects/${encodeURIComponent(projectId)}/boundary.geojson`;
}

export function donorsUrlFor(projectId: string): string {
  return `${getPublicApiUrl()}/projects/${encodeURIComponent(projectId)}/donors.geojson`;
}

export function basemapStyle(): string {
  return BASEMAP_STYLE_URL;
}

type Bounds = [[number, number], [number, number]];

function walk(coords: unknown, acc: { pts: number; w: number; s: number; e: number; n: number }): void {
  if (!Array.isArray(coords)) return;
  if (coords.length >= 2 && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
    const [x, y] = coords as number[];
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new Error('Invalid GeoJSON: non-finite coordinate');
    }
    if (x < -180 || x > 180 || y < -90 || y > 90) {
      throw new Error(`Invalid GeoJSON: coordinate out of range (${x}, ${y})`);
    }
    acc.pts += 1;
    acc.w = Math.min(acc.w, x);
    acc.e = Math.max(acc.e, x);
    acc.s = Math.min(acc.s, y);
    acc.n = Math.max(acc.n, y);
    return;
  }
  for (const c of coords) walk(c, acc);
}

function visit(node: unknown, acc: Parameters<typeof walk>[1]): void {
  if (!node || typeof node !== 'object') return;
  const o = node as Record<string, unknown>;
  if (o.type === 'FeatureCollection' && Array.isArray(o.features)) {
    o.features.forEach((f) => visit(f, acc));
  } else if (o.type === 'Feature') {
    visit(o.geometry, acc);
  } else if (o.type === 'GeometryCollection' && Array.isArray(o.geometries)) {
    o.geometries.forEach((g) => visit(g, acc));
  } else if ('coordinates' in o) {
    walk(o.coordinates, acc);
  }
}

/**
 * [[west, south], [east, north]] of any GeoJSON; throws on no geometry, non-finite or
 * out-of-range coordinates. Known limitation: geometry crossing the antimeridian yields a
 * world-wide bbox (west -180ish .. east 180ish) because no wrap-around handling is done.
 */
export function fitBoundsFor(geojson: unknown): Bounds {
  const acc = { pts: 0, w: Infinity, s: Infinity, e: -Infinity, n: -Infinity };
  visit(geojson, acc);
  if (acc.pts === 0) throw new Error('Cannot fit bounds: GeoJSON contains no geometry');
  return [[acc.w, acc.s], [acc.e, acc.n]];
}

/** Splits per-boundary fetch results (null = failed) into the usable GeoJSON and a failure count. */
export function settleBoundaries(results: readonly unknown[]): { ok: unknown[]; failed: number } {
  const ok = results.filter((r) => r !== null && r !== undefined);
  return { ok, failed: results.length - ok.length };
}

/** Union bbox of several GeoJSON documents; throws if none has geometry. */
export function fitBoundsForAll(docs: readonly unknown[]): Bounds {
  const bs = docs.map((d) => fitBoundsFor(d));
  if (bs.length === 0) throw new Error('Cannot fit bounds: GeoJSON contains no geometry');
  return [
    [Math.min(...bs.map((b) => b[0][0])), Math.min(...bs.map((b) => b[0][1]))],
    [Math.max(...bs.map((b) => b[1][0])), Math.max(...bs.map((b) => b[1][1]))],
  ];
}
