import type { components } from '../../lib/generated/schema';

type S = components['schemas'];
type Project = S['ProjectView'];
type Row = S['PortfolioRow'];

/** A boundary-less project is a scaffolded library case: it has no geometry and no observations. */
export function isLibraryCase(p: Pick<Project, 'boundary_sha256'>): boolean {
  return !p.boundary_sha256;
}

/**
 * The shell banner is raised only when a displayed project is simulated AND is a real, bounded project.
 * Library cases carry no data at all, so they never trigger the synthetic-output banner.
 */
export function dataModeFor(projects: readonly Pick<Project, 'data_mode' | 'boundary_sha256'>[]): 'observed' | 'simulated' {
  return projects.some((p) => p.data_mode === 'simulated' && !isLibraryCase(p)) ? 'simulated' : 'observed';
}

/**
 * Picks the project to show: the requested slug when accessible, else the first observed project with a
 * boundary (a simulated one is never the default over real data), else the first with a boundary, else the first.
 */
export function pickProject(projects: readonly Project[], requested?: string | null): Project | null {
  if (projects.length === 0) return null;
  const asked = requested ? projects.find((p) => p.slug === requested) : undefined;
  const real = projects.find((p) => !isLibraryCase(p) && p.data_mode !== 'simulated');
  return asked ?? real ?? projects.find((p) => !isLibraryCase(p)) ?? projects[0] ?? null;
}

export interface AttentionItem {
  id: string;
  name: string;
  slug: string;
  /** Review prompts phrased as questions to look at; never findings against a project. */
  reasons: string[];
}

/** Needs-attention review list from REAL portfolio fields only. Simulated rows are never listed. */
export function needsAttention(rows: readonly Row[]): AttentionItem[] {
  const out: AttentionItem[] = [];
  for (const r of rows) {
    if (r.data_mode === 'simulated') continue;
    const reasons: string[] = [];
    if (r.degraded) {
      reasons.push(`Assessment unavailable${r.degraded_reason ? ` (${r.degraded_reason})` : ''}. This warrants review.`);
    } else {
      if (r.assessment_level <= 1) reasons.push(`The reported assessment level is ${r.assessment_level} (${r.level_name}).`);
      if (r.attribution_verdict === null || r.attribution_verdict === 'Inconclusive') {
        reasons.push(
          r.attribution_verdict === null
            ? 'No attribution result is reported for this project.'
            : 'Attribution is reported as inconclusive: the available evidence does not currently allow attribution to be assessed.',
        );
      }
      if (r.top_recommendation) reasons.push(`Suggested review step: ${r.top_recommendation.text}`);
    }
    if (reasons.length > 0) out.push({ id: r.project.id, name: r.project.name, slug: r.project.slug, reasons });
  }
  return out;
}

export interface ClimateHeadline {
  year: number;
  annualRainfallMm: number;
  drought: string;
}

/** Latest year that has a served annual rainfall; the classification is the API's, never recomputed. */
export function climateHeadline(c: S['ClimateView'] | null | undefined): ClimateHeadline | null {
  if (!c || c.status === 'unavailable') return null;
  const years = [...(c.years ?? [])].filter((y) => typeof y.annual_rainfall_mm === 'number' && Number.isFinite(y.annual_rainfall_mm));
  years.sort((a, b) => b.year - a.year);
  const y = years[0];
  if (!y || y.annual_rainfall_mm === null) return null;
  return { year: y.year, annualRainfallMm: y.annual_rainfall_mm, drought: y.drought_classification };
}

export interface DataQuality {
  coverage: { min: number; max: number } | null;
  missingClimateMonths: number | null;
  sensors: string[];
}

/** Data-quality summary from served fields only. */
export function dataQuality(
  obs: S['ObservationsView'] | null | undefined,
  climate: S['ClimateView'] | null | undefined,
  inventory: S['EvidenceInventoryView'] | null | undefined,
): DataQuality {
  const cov = (obs && obs.status !== 'unavailable' ? obs.points : [])
    .map((p) => p.aoi_coverage_pct)
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const sensors = new Set<string>();
  for (const i of inventory && inventory.status !== 'unavailable' ? inventory.indicators : []) for (const s of i.sensors ?? []) sensors.add(s);
  return {
    coverage: cov.length ? { min: Math.min(...cov), max: Math.max(...cov) } : null,
    missingClimateMonths: climate && climate.status !== 'unavailable' ? (climate.missing_months ?? []).length : null,
    sensors: [...sensors].sort(),
  };
}

/** Projects whose boundaries the government map may draw: observed AND bounded. Simulated are never drawn. */
export function mappableProjects<P extends Pick<Project, 'data_mode' | 'boundary_sha256'>>(projects: readonly P[]): P[] {
  return projects.filter((p) => p.data_mode === 'observed' && !isLibraryCase(p));
}
