export interface CurvePoint {
  /** 0..1 along the time axis. */
  x: number;
  /** Observed project path, 0..1 vertical. */
  observed: number;
  /** Synthetic twin path. */
  twin: number;
}

export const INTERVENTION_X = 0.5;

/** Deterministic illustrative curves: identical before the intervention, diverging after. No randomness. */
export function curvePoints(count = 60): CurvePoint[] {
  const n = Math.max(2, Math.floor(count));
  const out: CurvePoint[] = [];
  for (let i = 0; i < n; i++) {
    const x = i / (n - 1);
    const base = 0.42 + 0.1 * x + 0.025 * Math.sin(x * 14);
    const after = Math.max(0, x - INTERVENTION_X) / (1 - INTERVENTION_X);
    const gap = 0.3 * after * after * (3 - 2 * after);
    out.push({ x, observed: base + gap, twin: base });
  }
  return out;
}

export function clamp01(v: number): number {
  return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0;
}

/** Scroll progress through a tall section: 0 when its top meets the viewport top, 1 when its bottom meets the viewport bottom. */
export function scrollProgress(rectTop: number, rectHeight: number, viewportHeight: number): number {
  const span = rectHeight - viewportHeight;
  return span <= 0 ? 1 : clamp01(-rectTop / span);
}

/** How much of the x axis is drawn at a given scroll progress. */
export function revealX(progress: number): number {
  return 0.2 + 0.8 * clamp01(progress);
}
