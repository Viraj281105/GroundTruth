import { serverApi } from '../../lib/server-api';
import type { components } from '../../lib/generated/schema';
import { isLibraryCase, pickProject } from './derive';

type S = components['schemas'];
export type OrgType = S['OrgView']['type'];
export type Project = S['ProjectView'];

/** One panel's data, or the honest reason it is missing. A failing endpoint degrades only its own panel. */
export type Panel<T> = { status: 'ok'; data: T } | { status: 'unavailable'; reason: string };

type Client = ReturnType<typeof serverApi>;
const INDICATORS = ['ndvi', 'evi', 'ndmi', 'nbr'] as const;

async function load<T>(label: string, run: () => Promise<{ data?: T; response: Response }>): Promise<Panel<T>> {
  try {
    const res = await run();
    if (res.data !== undefined && res.data !== null) return { status: 'ok', data: res.data };
    return { status: 'unavailable', reason: `${label} could not be loaded (API status ${res.response?.status ?? 'unknown'}).` };
  } catch {
    return { status: 'unavailable', reason: `${label} could not be loaded (the API could not be reached).` };
  }
}

export interface ProjectScope {
  /** All projects the org can see; the switcher lists them. */
  projects: Project[];
  selected: Project | null;
  /** True for scaffolded library cases: no boundary, no data. Project-level panels are not fetched. */
  libraryCase: boolean;
}

export interface NgoData {
  kind: 'ngo';
  orgSlug: string;
  orgType: OrgType;
  /** `reference` orgs get the NGO layout, read-only. */
  readOnly: boolean;
  projects: Panel<Project[]>;
  scope: ProjectScope | null;
  assessment: Panel<S['AssessmentView']> | null;
  readiness: Panel<S['ReadinessView']> | null;
  series: Panel<S['ObservationsView'][]> | null;
  climate: Panel<S['ClimateView']> | null;
  activity: Panel<S['ActivityItem'][]>;
}

export interface FunderData {
  kind: 'funder';
  orgSlug: string;
  portfolio: Panel<S['PortfolioView']>;
  activity: Panel<S['ActivityItem'][]>;
}

export interface AuditorData {
  kind: 'auditor';
  orgSlug: string;
  projects: Panel<Project[]>;
  scope: ProjectScope | null;
  assessment: Panel<S['AssessmentView']> | null;
  inventory: Panel<S['EvidenceInventoryView']> | null;
  readiness: Panel<S['ReadinessView']> | null;
  verification: Panel<S['VerificationView']> | null;
  climate: Panel<S['ClimateView']> | null;
  observations: Panel<S['ObservationsView']> | null;
  activity: Panel<S['ActivityItem'][]>;
}

export interface GovernmentClimateEntry {
  project: Project;
  climate: Panel<S['ClimateView']>;
}

export interface GovernmentData {
  kind: 'government';
  orgSlug: string;
  projects: Panel<Project[]>;
  portfolio: Panel<S['PortfolioView']>;
  /** Accessible OBSERVED projects with a boundary; simulated and library cases are excluded. */
  climate: GovernmentClimateEntry[];
}

export type DashboardData = NgoData | FunderData | AuditorData | GovernmentData;

export interface LoadOptions {
  /** `?project=<slug>` search param. */
  project?: string | null;
}

function scopeFor(projects: Panel<Project[]>, requested?: string | null): ProjectScope | null {
  if (projects.status !== 'ok') return null;
  const selected = pickProject(projects.data, requested);
  return { projects: projects.data, selected, libraryCase: selected ? isLibraryCase(selected) : false };
}

const projectsOf = (c: Client, slug: string) => load('The project list', () => c.GET('/orgs/{slug}/projects', { params: { path: { slug } } }));
const activityOf = (c: Client, slug: string) => load('Recent activity', () => c.GET('/orgs/{slug}/activity', { params: { path: { slug } } }));
const portfolioOf = (c: Client, slug: string) => load('The portfolio', () => c.GET('/orgs/{slug}/portfolio', { params: { path: { slug } } }));
const pid = (id: string) => ({ params: { path: { project_id: id } } });

/**
 * Fetches only what the persona's dashboard needs. `client` is injectable for tests; production uses
 * the cookie-forwarding `serverApi()`. Never throws: each failure becomes that panel's `unavailable`.
 */
export async function loadDashboardData(orgSlug: string, orgType: OrgType, opts: LoadOptions = {}, client?: Client): Promise<DashboardData> {
  const c = client ?? serverApi();
  if (orgType === 'funder') {
    const [portfolio, activity] = await Promise.all([portfolioOf(c, orgSlug), activityOf(c, orgSlug)]);
    return { kind: 'funder', orgSlug, portfolio, activity };
  }
  if (orgType === 'government') {
    const [projects, portfolio] = await Promise.all([projectsOf(c, orgSlug), portfolioOf(c, orgSlug)]);
    const eligible = projects.status === 'ok' ? projects.data.filter((p) => p.data_mode === 'observed' && !isLibraryCase(p)) : [];
    const climate = await Promise.all(
      eligible.map(async (project) => ({ project, climate: await load('Climate', () => c.GET('/projects/{project_id}/climate', pid(project.id))) })),
    );
    return { kind: 'government', orgSlug, projects, portfolio, climate };
  }
  if (orgType === 'auditor') {
    const [projects, activity] = await Promise.all([projectsOf(c, orgSlug), activityOf(c, orgSlug)]);
    const scope = scopeFor(projects, opts.project);
    const sel = scope?.selected;
    if (!sel || scope.libraryCase) {
      return { kind: 'auditor', orgSlug, projects, scope, assessment: null, inventory: null, readiness: null, verification: null, climate: null, observations: null, activity };
    }
    const [assessment, inventory, readiness, verification, climate, observations] = await Promise.all([
      load('The assessment', () => c.GET('/projects/{project_id}/assessment', pid(sel.id))),
      load('The evidence inventory', () => c.GET('/projects/{project_id}/evidence-inventory', pid(sel.id))),
      load('Readiness', () => c.GET('/projects/{project_id}/readiness', pid(sel.id))),
      load('The verification result', () => c.GET('/projects/{project_id}/verification', pid(sel.id))),
      load('Climate', () => c.GET('/projects/{project_id}/climate', pid(sel.id))),
      load('Observations', () => c.GET('/projects/{project_id}/observations', { params: { path: { project_id: sel.id }, query: { indicator: 'ndvi' } } })),
    ]);
    return { kind: 'auditor', orgSlug, projects, scope, assessment, inventory, readiness, verification, climate, observations, activity };
  }
  // ngo and reference share the NGO layout.
  const [projects, activity] = await Promise.all([projectsOf(c, orgSlug), activityOf(c, orgSlug)]);
  const scope = scopeFor(projects, opts.project);
  const base = { kind: 'ngo' as const, orgSlug, orgType, readOnly: orgType === 'reference', projects, scope, activity };
  const sel = scope?.selected;
  if (!sel || scope.libraryCase) return { ...base, assessment: null, readiness: null, series: null, climate: null };
  const [assessment, readiness, climate, ...obs] = await Promise.all([
    load('The assessment', () => c.GET('/projects/{project_id}/assessment', pid(sel.id))),
    load('Readiness', () => c.GET('/projects/{project_id}/readiness', pid(sel.id))),
    load('Climate', () => c.GET('/projects/{project_id}/climate', pid(sel.id))),
    ...INDICATORS.map((indicator) =>
      load(`The ${indicator.toUpperCase()} series`, () => c.GET('/projects/{project_id}/observations', { params: { path: { project_id: sel.id }, query: { indicator } } })),
    ),
  ]);
  const ok = obs.flatMap((o) => (o.status === 'ok' ? [o.data] : []));
  const series: Panel<S['ObservationsView'][]> = ok.length > 0 ? { status: 'ok', data: ok } : { status: 'unavailable', reason: 'Observation series could not be loaded from the API.' };
  return { ...base, assessment, readiness, series, climate };
}
