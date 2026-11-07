/**
 * Donor map model: fetch + validate the boundary GeoJSON the API serves at
 * /cases/{id}/boundary.geojson. No geometry is ever invented.
 */

export type Position = [number, number];

export interface BoundaryFeature {
  type: 'Feature';
  properties: Record<string, unknown> | null;
  geometry: { type: string; coordinates: unknown };
}

export interface BoundaryData {
  type: 'FeatureCollection';
  features: BoundaryFeature[];
}

export interface BoundaryModel {
  data: BoundaryData;
  /** [west, south, east, north] */
  bbox: [number, number, number, number];
  centroid: Position;
  /** Donor weight by feature index, only for features that carry both a donor role and a numeric weight. */
  donorWeights: Array<{ index: number; weight: number; name: string }>;
}

export type BoundaryResult =
  | { kind: 'ok'; model: BoundaryModel }
  | { kind: 'empty'; reason: 'not-found' | 'no-geometry' }
  | { kind: 'error'; message: string };

function collect(coords: unknown, out: Position[]): void {
  if (!Array.isArray(coords)) return;
  if (coords.length >= 2 && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
    out.push([coords[0], coords[1]]);
    return;
  }
  for (const c of coords) collect(c, out);
}

export function modelFromGeoJson(json: unknown): BoundaryResult {
  if (!json || typeof json !== 'object') return { kind: 'empty', reason: 'no-geometry' };
  const obj = json as Record<string, unknown>;
  let features: BoundaryFeature[] = [];
  if (obj.type === 'FeatureCollection' && Array.isArray(obj.features)) {
    features = obj.features as BoundaryFeature[];
  } else if (obj.type === 'Feature') {
    features = [obj as unknown as BoundaryFeature];
  } else if (typeof obj.type === 'string' && 'coordinates' in obj) {
    features = [{ type: 'Feature', properties: null, geometry: obj as unknown as BoundaryFeature['geometry'] }];
  }
  features = features.filter((f) => f && f.geometry && typeof f.geometry.type === 'string');
  const pts: Position[] = [];
  features.forEach((f) => collect(f.geometry.coordinates, pts));
  if (pts.length === 0) return { kind: 'empty', reason: 'no-geometry' };

  const lons = pts.map((p) => p[0]);
  const lats = pts.map((p) => p[1]);
  const bbox: BoundaryModel['bbox'] = [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)];
  const donorWeights = features.flatMap((f, index) => {
    const p = f.properties ?? {};
    const w = p.weight;
    if (p.role === 'donor' && typeof w === 'number' && Number.isFinite(w)) {
      return [{ index, weight: w, name: typeof p.name === 'string' ? p.name : `Donor ${index + 1}` }];
    }
    return [];
  });
  return {
    kind: 'ok',
    model: {
      data: { type: 'FeatureCollection', features },
      bbox,
      centroid: [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2],
      donorWeights,
    },
  };
}

export async function loadBoundary(
  baseUrl: string,
  caseId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<BoundaryResult> {
  let res: Response;
  try {
    res = await fetchImpl(`${baseUrl}/cases/${encodeURIComponent(caseId)}/boundary.geojson`);
  } catch {
    return { kind: 'error', message: `The API at ${baseUrl} could not be reached, so the boundary is not shown.` };
  }
  if (res.status === 404) return { kind: 'empty', reason: 'not-found' };
  if (!res.ok) return { kind: 'error', message: `The API answered ${res.status} for the boundary.` };
  try {
    return modelFromGeoJson(await res.json());
  } catch {
    return { kind: 'error', message: 'The boundary response was not valid GeoJSON.' };
  }
}

/** Opacity 0.15-0.85 scaled to the largest returned weight; never extrapolated. */
export function weightOpacity(weight: number, max: number): number {
  if (!(max > 0)) return 0.15;
  return 0.15 + 0.7 * Math.min(Math.max(weight / max, 0), 1);
}

export function formatBbox(b: BoundaryModel['bbox']): string {
  return `W ${b[0].toFixed(3)}, S ${b[1].toFixed(3)}, E ${b[2].toFixed(3)}, N ${b[3].toFixed(3)}`;
}
