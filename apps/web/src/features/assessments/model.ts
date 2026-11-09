import type { Schemas } from '../../lib/api-client';

type Project = Schemas['ProjectView'];
type Assessment = Schemas['AssessmentView'];

/** Claim counts as GET /claims/structured/{id} reports them (the schema types this body as an open object). */
export interface ClaimSummary {
  total: number;
  supported: number;
  partiallySupported: number;
  contradicted: number;
  unverified: number;
  hasClaims: boolean;
  isDemo: boolean;
}

export interface AssessmentRow {
  id: string;
  slug: string;
  name: string;
  place: string;
  treatmentStart: number;
  simulated: boolean;
  /** No uploaded boundary: a library case with no data of its own. */
  libraryCase: boolean;
  /** "Level 2 · Contextual intelligence" exactly as the API names it; null when the assessment could not be read. */
  level: string | null;
  levelUnavailable: string | null;
  claims: ClaimSummary | null;
  claimsUnavailable: string | null;
}

export interface AssessmentKpis {
  projects: number;
  assessmentsAvailable: number;
  simulatedProjects: number;
  libraryCases: number;
  /** Claims recorded on real (non-simulated) projects only. */
  claimsOnRealProjects: number;
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => v !== null && typeof v === 'object' && !Array.isArray(v);
const count = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0);

/** Null-safe read of the structured-claims body. Anything that is not an object yields null, never zeros presented as data. */
export function claimSummary(body: unknown): ClaimSummary | null {
  if (!isObj(body)) return null;
  const total = count(body.total_claims);
  return {
    total,
    supported: count(body.supported_count),
    partiallySupported: count(body.partially_supported_count),
    contradicted: count(body.contradicted_count),
    unverified: count(body.unverified_count),
    hasClaims: typeof body.has_claims === 'boolean' ? body.has_claims : total > 0,
    isDemo: body.is_demo === true || body.data_mode === 'synthetic',
  };
}

export const isLibraryCase = (p: Pick<Project, 'boundary_sha256'>): boolean => !p.boundary_sha256;

export function toRow(p: Project, assessment: { data: Assessment | null; status: number }, claims: { data: unknown; status: number }): AssessmentRow {
  const summary = claimSummary(claims.data);
  return {
    id: p.id,
    slug: p.slug,
    name: p.name,
    place: [p.ecosystem, p.country].filter(Boolean).join(' · '),
    treatmentStart: p.treatment_start_year,
    simulated: p.data_mode === 'simulated' || summary?.isDemo === true,
    libraryCase: isLibraryCase(p),
    level: assessment.data ? `Level ${assessment.data.level} · ${assessment.data.level_name}` : null,
    levelUnavailable: assessment.data ? null : `The assessment could not be read (HTTP ${assessment.status || 'no response'}).`,
    claims: summary,
    claimsUnavailable: summary ? null : `Claims could not be read (HTTP ${claims.status || 'no response'}).`,
  };
}

/** Counts only: nothing is averaged, scored or sealed here. */
export function kpis(rows: readonly AssessmentRow[]): AssessmentKpis {
  return {
    projects: rows.length,
    assessmentsAvailable: rows.filter((r) => r.level !== null).length,
    simulatedProjects: rows.filter((r) => r.simulated).length,
    libraryCases: rows.filter((r) => r.libraryCase).length,
    claimsOnRealProjects: rows.reduce((n, r) => n + (!r.simulated && r.claims ? r.claims.total : 0), 0),
  };
}
