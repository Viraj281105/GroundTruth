/**
 * Null-safe model for GET /claims/structured/{project_id}.
 *
 * The generated schema types this response as an open object, so every field is read defensively:
 * a missing or wrongly typed field becomes an empty value, never an exception, and never an invented
 * figure. Values are displayed exactly as the API returns them.
 */

export type ClaimStatus = 'supported' | 'partially_supported' | 'contradicted' | 'unverified';
export const CLAIM_STATUSES: readonly ClaimStatus[] = ['supported', 'partially_supported', 'contradicted', 'unverified'];

export interface StatementView {
  id: string;
  text: string;
  targetMetric: string;
  claimedValue: string;
  observedValue: string;
  status: string;
  rationale: string;
}

export interface GradingView {
  evidenceQuality: string;
  evidenceQualityScore: number | null;
  methodological: string;
  methodologicalScore: number | null;
  causal: string;
  causalScore: number | null;
  overall: string;
  rationale: string[];
}

import type { ClaimSource } from '../../features/projects/claims.model';

export interface ClaimView {
  id: string;
  /** Present for claims promoted from a document or typed in; absent for demo and other claims. */
  source: ClaimSource | null;
  headline: string;
  reasons: string[];
  kind: string;
  title: string;
  definition: string;
  claimedValue: string;
  claimedUnit: string;
  observedValue: string;
  observedUnit: string;
  status: ClaimStatus;
  discrepancyPercentage: number | null;
  statements: StatementView[];
  requiredEvidence: string[];
  availableEvidence: string[];
  supporting: string[];
  contradictory: string[];
  missing: string[];
  methodology: string;
  limitations: string[];
  grading: GradingView;
  correctiveAction: string | null;
}

export interface MissingItem {
  id: string;
  label: string;
  status: string;
  detail: string;
  action: string;
}

export interface PortfolioView {
  projectName: string;
  overallGrade: string;
  dataMode: 'synthetic' | 'observed';
  isDemo: boolean;
  notice: string | null;
  hasClaims: boolean;
  claims: ClaimView[];
  counts: Record<ClaimStatus, number>;
  guardrails: string[];
  missingInformation: MissingItem[];
  nextSteps: string[];
  verifiedAt: string;
}

type Obj = Record<string, unknown>;

const obj = (v: unknown): Obj => (v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Obj) : {});
const str = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' && Number.isFinite(v) ? String(v) : '');
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []);
const list = (v: unknown): Obj[] => (Array.isArray(v) ? v.map(obj) : []);

/** API statuses are upper-case enum values; anything unrecognised is shown as unverified, never as supported. */
export function normalizeStatus(v: unknown): ClaimStatus {
  const s = typeof v === 'string' ? v.toLowerCase() : '';
  return (CLAIM_STATUSES as readonly string[]).includes(s) ? (s as ClaimStatus) : 'unverified';
}

/** "partially_supported" -> "Partially supported". Safe on any input. */
export function humanize(v: unknown): string {
  const s = str(v).replace(/_/g, ' ').trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : '';
}

/** A figure exactly as the API sent it (number or text); empty when absent. */
export function showValue(v: unknown): string {
  if (typeof v === 'number' && Number.isFinite(v)) return v.toLocaleString('en-US', { maximumFractionDigits: 6 });
  return str(v);
}

function toStatement(raw: Obj, i: number): StatementView {
  return {
    id: str(raw.statement_id) || `statement-${i + 1}`,
    text: str(raw.statement_text),
    targetMetric: str(raw.target_metric),
    claimedValue: showValue(raw.claimed_value),
    observedValue: showValue(raw.observed_value),
    status: str(raw.status),
    rationale: str(raw.rationale),
  };
}

function toGrading(raw: unknown): GradingView {
  const g = obj(raw);
  return {
    evidenceQuality: str(g.evidence_quality_grade),
    evidenceQualityScore: num(g.evidence_quality_score),
    methodological: str(g.methodological_suitability_grade),
    methodologicalScore: num(g.methodological_suitability_score),
    causal: str(g.causal_confidence_grade),
    causalScore: num(g.causal_confidence_score),
    overall: str(g.overall_grade),
    rationale: strs(g.scoring_rationale),
  };
}

const nstr = (v: unknown): string | null => (typeof v === 'string' ? v : null);

/** The source block is only trusted when it names the claim's text; anything else is treated as no source. */
export function toSource(raw: unknown): ClaimSource | null {
  const o = obj(raw);
  if (typeof o.statement_text !== 'string' || typeof o.original_text !== 'string') return null;
  return {
    project_claim_id: str(o.project_claim_id),
    document_id: nstr(o.document_id),
    document_name: nstr(o.document_name),
    document_sha256: nstr(o.document_sha256),
    start: num(o.start),
    end: num(o.end),
    original_text: o.original_text,
    original_kind: nstr(o.original_kind),
    original_value: num(o.original_value),
    original_unit: nstr(o.original_unit),
    original_period: nstr(o.original_period),
    statement_text: o.statement_text,
    kind: str(o.kind),
    value: num(o.value),
    unit: nstr(o.unit),
    period: nstr(o.period),
    edited: o.edited === true,
    created_at: nstr(o.created_at),
    updated_at: nstr(o.updated_at),
  };
}

function toClaim(raw: Obj, i: number): ClaimView {
  return {
    id: str(raw.claim_id) || `claim-${i + 1}`,
    source: toSource(raw.source),
    headline: str(raw.headline),
    reasons: strs(raw.reasons),
    kind: str(raw.claim_type),
    title: str(raw.title) || humanize(raw.claim_type) || `Claim ${i + 1}`,
    definition: str(raw.definition),
    claimedValue: showValue(raw.claimed_value),
    claimedUnit: str(raw.claimed_unit),
    observedValue: showValue(raw.observed_value),
    observedUnit: str(raw.observed_unit),
    status: normalizeStatus(raw.status),
    discrepancyPercentage: num(raw.discrepancy_percentage),
    statements: list(raw.decomposed_statements).map(toStatement),
    requiredEvidence: strs(raw.required_evidence),
    availableEvidence: strs(raw.available_evidence),
    supporting: strs(raw.supporting_observations),
    contradictory: strs(raw.contradictory_observations),
    missing: strs(raw.missing_evidence),
    methodology: str(raw.verification_methodology),
    limitations: strs(raw.confidence_and_limitations),
    grading: toGrading(raw.grading),
    correctiveAction: str(raw.corrective_action_request) || null,
  };
}

function toMissing(raw: Obj, i: number): MissingItem {
  return {
    id: str(raw.id) || `missing-${i + 1}`,
    label: str(raw.label) || 'Missing information',
    status: str(raw.status) || 'not_met',
    detail: str(raw.detail),
    action: str(raw.action),
  };
}

/** Normalise the API body. A non-object body yields an empty, honest portfolio rather than throwing. */
export function toPortfolio(body: unknown): PortfolioView {
  const b = obj(body);
  const claims = list(b.claims).map(toClaim);
  const counts: Record<ClaimStatus, number> = { supported: 0, partially_supported: 0, contradicted: 0, unverified: 0 };
  for (const c of claims) counts[c.status] += 1;
  return {
    projectName: str(b.project_name),
    overallGrade: str(b.overall_portfolio_grade),
    dataMode: b.data_mode === 'synthetic' ? 'synthetic' : 'observed',
    isDemo: b.is_demo === true,
    notice: str(b.notice) || null,
    hasClaims: claims.length > 0,
    claims,
    counts,
    guardrails: strs(b.scientific_guardrails),
    missingInformation: list(b.missing_information).map(toMissing),
    nextSteps: strs(b.next_steps),
    verifiedAt: str(b.verification_timestamp),
  };
}

/** Honest message for a failed structured-claims fetch. */
export function claimsProblem(status: number): string {
  if (status === 401) return 'Your session has expired. Sign in again to see this project’s claims.';
  if (status === 404) return 'This project was not found, or you do not have access to its claims.';
  if (status === 403) return 'Your role does not allow viewing claim verification for this project.';
  if (status === 0) return 'The GroundTruth API could not be reached. No claims are shown.';
  return `The claim verification service could not complete the request (HTTP ${status}). No claims are shown.`;
}

export function isSimulated(p: Pick<PortfolioView, 'isDemo' | 'dataMode'>): boolean {
  return p.isDemo || p.dataMode === 'synthetic';
}
