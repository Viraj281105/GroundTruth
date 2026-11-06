/** Pure scale and binning helpers for the SVG chart kit. No DOM, so they are unit-tested. */

export interface Domain {
  min: number;
  max: number;
}

export function extent(values: readonly number[]): Domain | null {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return null;
  return { min: Math.min(...finite), max: Math.max(...finite) };
}

/** Linear map from a data domain to a pixel range. A zero-width domain maps to the midpoint. */
export function linearScale(domain: Domain, range: [number, number]): (v: number) => number {
  const span = domain.max - domain.min;
  if (span === 0) return () => (range[0] + range[1]) / 2;
  return (v) => range[0] + ((v - domain.min) / span) * (range[1] - range[0]);
}

/** Round-number tick positions covering the domain (about `count` of them). */
export function niceTicks(domain: Domain, count = 5): number[] {
  const span = domain.max - domain.min;
  if (span === 0) return [domain.min];
  const rough = span / Math.max(count - 1, 1);
  const pow = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= rough) ?? 10 * pow;
  const first = Math.ceil(domain.min / step) * step;
  const ticks: number[] = [];
  for (let t = first; t <= domain.max + step * 1e-9; t += step) ticks.push(Number(t.toPrecision(12)));
  return ticks;
}

export interface Bin {
  from: number;
  to: number;
  count: number;
}

/** Equal-width histogram. Every finite value lands in exactly one bin (the max goes in the last). */
export function histogram(values: readonly number[], binCount = 12): Bin[] {
  const d = extent(values);
  if (!d || binCount < 1) return [];
  const width = (d.max - d.min) / binCount || 1;
  const bins: Bin[] = Array.from({ length: binCount }, (_, i) => ({ from: d.min + i * width, to: d.min + (i + 1) * width, count: 0 }));
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    const i = Math.min(Math.floor((v - d.min) / width), binCount - 1);
    bins[i].count += 1;
  }
  return bins;
}

/** SVG path for a polyline; non-finite points break the line instead of drawing garbage. */
export function linePath(points: ReadonlyArray<{ x: number; y: number }>): string {
  let d = '';
  let pen = false;
  for (const p of points) {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) {
      pen = false;
      continue;
    }
    d += `${pen ? 'L' : 'M'}${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    pen = true;
  }
  return d;
}

/** Compact number for axis labels: 1200 -> 1.2k, 0.0312 -> 0.031. */
export function compact(value: number): string {
  if (!Number.isFinite(value)) return '–';
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${(value / 1e3).toFixed(0)}k`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 1) return value.toFixed(2).replace(/\.?0+$/, '');
  return Number(value.toPrecision(2)).toString();
}
