import { isNum } from './format';
import type { ObservationsView } from './types';

export interface SeriesPoint {
  year: number;
  value: number;
  evidenceState: ObservationsView['points'][number]['evidence_state'];
  sensor: string;
  clearPixelFraction: number | null;
  nScenes: number | null;
  aoiCoveragePct: number | null;
  /** null when redacted for the caller's access level. */
  sceneIds: string[] | null;
  scenesSha256: string | null;
}

/**
 * Real points only. A point with no finite value, or in the UNAVAILABLE state, is dropped and its
 * year reported as a gap (together with any year missing between the first and last point). Gaps
 * are never interpolated or filled.
 */
export function seriesPoints(o: Pick<ObservationsView, 'status' | 'points'>): { points: SeriesPoint[]; gaps: number[] } {
  if (o.status === 'unavailable') return { points: [], gaps: [] };
  const points: SeriesPoint[] = [];
  const gapYears = new Set<number>();
  const seen = new Set<number>();
  for (const p of o.points ?? []) {
    seen.add(p.year);
    if (!isNum(p.value) || p.evidence_state === 'UNAVAILABLE') {
      gapYears.add(p.year);
      continue;
    }
    points.push({
      year: p.year,
      value: p.value,
      evidenceState: p.evidence_state,
      sensor: p.sensor,
      clearPixelFraction: isNum(p.clear_pixel_fraction) ? p.clear_pixel_fraction : null,
      nScenes: isNum(p.n_scenes) ? p.n_scenes : null,
      aoiCoveragePct: isNum(p.aoi_coverage_pct) ? p.aoi_coverage_pct : null,
      sceneIds: Array.isArray(p.scene_ids) ? p.scene_ids : null,
      scenesSha256: p.scenes_sha256 ?? null,
    });
  }
  points.sort((a, b) => a.year - b.year);
  if (points.length > 0) {
    const lo = points[0].year;
    const hi = points[points.length - 1].year;
    for (let y = lo; y <= hi; y++) if (!seen.has(y)) gapYears.add(y);
  }
  return { points, gaps: [...gapYears].sort((a, b) => a - b) };
}
