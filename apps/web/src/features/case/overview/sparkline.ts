export interface SparkPoint {
  year: number;
  observed: number;
  synthetic: number;
}

export interface Sparkline {
  width: number;
  height: number;
  observed: string;
  synthetic: string;
  /** x position of the treatment year, or null when it lies outside the series. */
  treatmentX: number | null;
}

const PAD = 4;

/**
 * Two polylines on one shared scale. Points with a non-finite value are
 * dropped, and fewer than two usable points yields null: the caller shows
 * "no time series" rather than an empty or NaN chart.
 */
export function buildSparkline(
  data: readonly SparkPoint[],
  treatmentYear: number | undefined,
  width = 320,
  height = 120,
): Sparkline | null {
  const pts = data.filter((d) => Number.isFinite(d.year) && Number.isFinite(d.observed) && Number.isFinite(d.synthetic));
  if (pts.length < 2) return null;
  const years = pts.map((p) => p.year);
  const values = pts.flatMap((p) => [p.observed, p.synthetic]);
  const [x0, x1] = [Math.min(...years), Math.max(...years)];
  const [y0, y1] = [Math.min(...values), Math.max(...values)];
  const sx = (x: number) => PAD + (x1 === x0 ? 0 : ((x - x0) / (x1 - x0)) * (width - 2 * PAD));
  const sy = (y: number) => height - PAD - (y1 === y0 ? 0.5 : (y - y0) / (y1 - y0)) * (height - 2 * PAD);
  const line = (key: 'observed' | 'synthetic') =>
    pts.map((p) => `${sx(p.year).toFixed(1)},${sy(p[key]).toFixed(1)}`).join(' ');
  const inRange = treatmentYear !== undefined && treatmentYear >= x0 && treatmentYear <= x1;
  return {
    width,
    height,
    observed: line('observed'),
    synthetic: line('synthetic'),
    treatmentX: inRange ? Number(sx(treatmentYear).toFixed(1)) : null,
  };
}
