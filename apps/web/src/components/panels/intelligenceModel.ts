/**
 * Null-safe model for the intelligence routes.
 *
 * `/intelligence/status` and `/intelligence/research` are typed as open objects in the generated
 * schema, so responses are normalised here. Nothing is invented: a missing field is empty/null, and
 * latency is only ever the API's measured number.
 */

export const INTELLIGENCE_MODES = [
  { value: 'csr_due_diligence', label: 'CSR due diligence' },
  { value: 'environmental_research', label: 'Environmental research' },
  { value: 'policy_news_analysis', label: 'Policy and news analysis' },
  { value: 'proposal_analysis', label: 'Proposal analysis' },
  { value: 'contradiction_detection', label: 'Contradiction detection' },
  { value: 'stakeholder_reports', label: 'Stakeholder reports' },
] as const;
export type IntelligenceModeValue = (typeof INTELLIGENCE_MODES)[number]['value'];

export const STAKEHOLDER_ROLES = [
  { value: 'csr', label: 'CSR / funder' },
  { value: 'auditor', label: 'Auditor' },
  { value: 'ngo', label: 'NGO / implementer' },
] as const;

export type ServiceStatus =
  | { state: 'configured'; model: string; provider: string }
  | { state: 'unavailable'; reason: string };

export interface Fact {
  id: string;
  statement: string;
  source: string;
  kind: string;
  citedByModel: boolean | null;
}
export interface Inference {
  statement: string;
  label: string;
  basedOn: string[];
}
export interface Literature {
  kind: string;
  title: string;
  authors: string;
  venue: string;
  year: string;
  doi: string;
  relevance: string;
}

export type ResearchStatus = 'ok' | 'insufficient_context' | 'unavailable' | 'error';

export interface ResearchView {
  status: ResearchStatus;
  reason: string;
  query: string;
  mode: string;
  model: string;
  /** Milliseconds measured by the server; null when it was not measured. */
  latencyMs: number | null;
  generatedAt: string;
  dataMode: string;
  answer: string | null;
  facts: Fact[];
  inferences: Inference[];
  unsupported: string[];
  missingContext: string[];
  literature: Literature[];
  guardrailNotice: string;
  guardrailDropped: string[];
}

type Obj = Record<string, unknown>;
const obj = (v: unknown): Obj => (v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : {});
const str = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' && Number.isFinite(v) ? String(v) : '');
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.map((x) => str(x)).filter((x) => x !== '') : []);
const arr = (v: unknown): Obj[] => (Array.isArray(v) ? v.map(obj) : []);

export function toServiceStatus(body: unknown): ServiceStatus {
  const b = obj(body);
  if (b.configured === true && b.status === 'configured') return { state: 'configured', model: str(b.model), provider: str(b.provider) };
  return { state: 'unavailable', reason: str(b.reason) || 'The intelligence service did not report that it is configured.' };
}

const STATUSES: readonly string[] = ['ok', 'insufficient_context', 'unavailable', 'error'];

export function toResearch(body: unknown): ResearchView {
  const b = obj(body);
  const status = (STATUSES.includes(str(b.status)) ? str(b.status) : 'error') as ResearchStatus;
  const lat = b.latency_ms;
  const g = obj(b.guardrail);
  return {
    status,
    reason: str(b.reason),
    query: str(b.query),
    mode: str(b.mode),
    model: str(b.model),
    latencyMs: typeof lat === 'number' && Number.isFinite(lat) && lat >= 0 ? lat : null,
    generatedAt: str(b.generated_at),
    dataMode: str(b.data_mode),
    answer: str(b.answer) || null,
    facts: arr(b.retrieved_facts).map((f, i) => ({
      id: str(f.fact_id) || `fact-${i + 1}`,
      statement: str(f.statement),
      source: str(f.source),
      kind: str(f.kind),
      citedByModel: typeof f.cited_by_model === 'boolean' ? f.cited_by_model : null,
    })),
    inferences: arr(b.inferences).map((x) => ({ statement: str(x.statement), label: str(x.label), basedOn: strs(x.based_on) })),
    unsupported: strs(b.unsupported_conclusions),
    missingContext: strs(b.missing_context),
    literature: arr(b.published_literature).map((l) => ({
      kind: str(l.kind),
      title: str(l.title),
      authors: str(l.authors),
      venue: str(l.venue),
      year: str(l.year),
      doi: str(l.doi),
      relevance: str(l.relevance),
    })),
    guardrailNotice: str(g.notice),
    guardrailDropped: strs(g.dropped),
  };
}

/** The measured latency label, or null when the API did not measure one. Never a default number. */
export function latencyLabel(ms: number | null): string | null {
  if (ms === null) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`;
}

export function researchBody(query: string, projectId: string, mode: string, role: string | null) {
  return {
    query: query.trim(),
    project_id: projectId,
    mode: mode as IntelligenceModeValue,
    ...(mode === 'stakeholder_reports' && role ? { stakeholder_role: role } : {}),
  };
}

/** Why a non-ok response is not an answer; the server's own reason wins. */
export function statusMessage(v: Pick<ResearchView, 'status' | 'reason'>): string {
  if (v.reason) return v.reason;
  switch (v.status) {
    case 'insufficient_context':
      return 'This project has too little recorded information to answer that question.';
    case 'unavailable':
      return 'The intelligence service is unavailable right now.';
    case 'error':
      return 'The intelligence service reported an error.';
    default:
      return '';
  }
}

export function httpProblem(status: number): string {
  if (status === 0) return 'The GroundTruth API could not be reached. No answer was produced.';
  if (status === 401) return 'Your session has expired. Sign in again.';
  if (status === 403 || status === 404) return 'This project was not found, or you do not have access to it.';
  if (status === 422) return 'The question or project selection was not accepted. Check that the question is at least 3 characters.';
  if (status === 429) return 'Too many questions in a short time. Wait a minute and try again.';
  return `The intelligence service could not complete the request (HTTP ${status}). No answer was produced.`;
}

export interface ProjectOption {
  id: string;
  name: string;
  simulated: boolean;
}
