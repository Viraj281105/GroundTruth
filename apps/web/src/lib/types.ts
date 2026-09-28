/**
 * Types mirroring the GroundTruth API schemas.
 *
 * Kept in sync with the API schemas in
 * `packages/groundtruth/src/groundtruth/platform/api/schemas.py` and the evidence
 * objects in `packages/groundtruth/src/groundtruth/contracts/evidence.py`.
 * Regenerate from /openapi.json once the frontend build is wired up.
 */

/** How an interval should be read. These are not interchangeable. */
export type ConfidenceKind =
  | "permutation"
  | "bootstrap"
  | "analytic"
  | "sensitivity-envelope";

export interface Confidence {
  lower: number;
  upper: number;
  level: number;
  kind: ConfidenceKind;
}

/** Where a value came from and how it was produced. Never omit this in the UI. */
export interface Provenance {
  source: string;
  method: string;
  stage: string;
  source_uri: string | null;
  retrieved_at: string | null;
  code_version: string | null;
  parameters: Record<string, unknown>;
  inputs: string[];
  notes: string | null;
}

export interface Evidence {
  id: string;
  label: string;
  value: number | string | boolean;
  unit: string;
  confidence: Confidence | null;
  provenance: Provenance;
  qualifiers: Record<string, unknown>;
}

/** Screening outcomes. None of these is a finding of fraud. */
export type VerdictLabel =
  | "consistent_with_claim"
  | "divergent_from_claim"
  | "inconclusive"
  | "not_assessed";

export interface VerificationVerdict {
  label: VerdictLabel;
  rationale: string;
  divergence_ratio: number | null;
  /** Always rendered with the verdict. Never collapsed by default. */
  caveats: string[];
  supporting_evidence_ids: string[];
}

export interface EvidenceBundle {
  case_id: string;
  schema_version: string;
  items: Evidence[];
  verdict: VerificationVerdict | null;
  warnings: string[];
}

export interface CaseSummary {
  case_id: string;
  name: string;
  country: string;
  standard: string;
  registry_id: string | null;
  ecosystem: string;
  indicator: string;
  pre_period: string;
  post_period: string;
  /** "scaffolded" | "data-wired" | "analysed" */
  status: string;
  has_known_reference: boolean;
}

export interface CaseDetail extends CaseSummary {
  area_ha: number | null;
  donor_search_region: string;
  donor_pool_size: number;
  covariates: string[];
  /** Published third-party findings. Never an input to the estimate. */
  known_reference: Record<string, unknown>;
  notes: string;
}

export interface VerificationRequest {
  synthetic?: boolean;
  true_effect?: number;
  min_donors?: number;
  include_report?: boolean;
}

export interface HealthResponse {
  status: string;
  version: string;
  engine_version: string;
  contract_version: string;
  engine_capabilities: Record<string, boolean>;
  earth_observation_implemented: boolean;
  genai_narration_implemented: boolean;
  cases_available: number;
}

export interface VerificationResponse {
  case_id: string;
  /** "simulated" or "observed". Drives the banner. */
  data_mode: "simulated" | "observed";
  verdict_label: VerdictLabel;
  verdict_rationale: string;
  caveats: string[];
  warnings: string[];
  bundle: EvidenceBundle;
  report_markdown: string | null;
  report_generator: string | null;
  /**
   * Hash of the analysis specification (blake2b hex digest, per
   * `contracts.identifiers.spec_hash`), present on the real API response
   * (`platform/api/schemas.py::VerificationResponse`). Optional here only
   * because the frontend's own simulated fixtures predate this field —
   * never fabricate one when it is absent.
   */
  spec_hash?: string;
}

/** True when the UI must show the persistent simulated-data banner. */
export function isSimulated(response: VerificationResponse): boolean {
  return response.data_mode === "simulated";
}

/**
 * Display styling for a verdict.
 *
 * `inconclusive` is deliberately neutral: it is a legitimate outcome, not an
 * error. `divergent_from_claim` is amber, never alarm-red, because it means
 * "warrants review", not "wrongdoing".
 */
export function verdictTone(
  label: VerdictLabel,
): "positive" | "caution" | "neutral" {
  switch (label) {
    case "consistent_with_claim":
      return "positive";
    case "divergent_from_claim":
      return "caution";
    default:
      return "neutral";
  }
}

/** Format a value with its unit, never as a bare number. */
export function formatEvidence(item: Evidence): string {
  const value =
    typeof item.value === "number"
      ? item.value.toPrecision(4).replace(/\.?0+$/, "")
      : String(item.value);
  return item.unit ? `${value} ${item.unit}` : value;
}

/**
 * Lifecycle state of a verification run.
 *
 * This is distinct from `VerdictLabel`: a run can be `measured` and still
 * carry an `inconclusive` verdict — that is a scientific finding, not the
 * absence of a result. `ResultState` answers "did the pipeline run, and
 * what happened to it", not "what did it conclude".
 *
 * Derived entirely from signals the API already exposes — a request is in
 * flight, a 2xx response with a bundle was received, or `verifyCase`
 * surfaced `isRefusal` (backed by `AnalysisError.is_refusal` /
 * `ErrorCode.is_refusal` in the platform contract) — via `deriveResultState`
 * below. No new backend field is introduced for this.
 */
export type ResultState =
  | "not_started"
  | "running"
  | "measured"
  | "refused"
  | "failed";

export interface ResultStateInputs {
  /** A verification request is currently in flight. */
  isRunning: boolean;
  /** A verification response with an evidence bundle was received. */
  hasResult: boolean;
  /** The run was scientifically refused (e.g. inadequate donor pool, 501/422 is_refusal). */
  isRefused: boolean;
  /** The run failed for a non-scientific reason (network, 5xx, unexpected error). */
  hasError: boolean;
}

/**
 * Resolve the five distinguishable run states from the page's local signals.
 * RULE: the absence of a measurement is a state, never a zero or a guess.
 */
export function deriveResultState({
  isRunning,
  hasResult,
  isRefused,
  hasError,
}: ResultStateInputs): ResultState {
  if (isRunning) return "running";
  if (isRefused) return "refused";
  if (hasError) return "failed";
  if (hasResult) return "measured";
  return "not_started";
}

/** Display styling for a `ResultState`, following the same tone vocabulary as `verdictTone`. */
export function resultStateTone(
  state: ResultState,
): "neutral" | "info" | "positive" | "inconclusive" | "error" {
  switch (state) {
    case "not_started":
      return "neutral";
    case "running":
      return "info";
    case "measured":
      return "positive";
    case "refused":
      return "inconclusive";
    case "failed":
      return "error";
  }
}

/** Human-readable label for a `ResultState`, in the app's existing terse UPPERCASE style. */
export function resultStateLabel(state: ResultState): string {
  switch (state) {
    case "not_started":
      return "NOT STARTED";
    case "running":
      return "RUNNING";
    case "measured":
      return "MEASURED";
    case "refused":
      return "REFUSED";
    case "failed":
      return "FAILED";
  }
}

/**
 * ADR-011 donor-candidate exclusion categories.
 *
 * Mirrors `groundtruth.platform.units.rules.ExclusionCategory` exactly. These
 * are part of the ADR's fixed specification, not measured data — the category
 * *names* are always known, even before any district has ever been screened.
 */
export type DonorExclusionCategory =
  | "empty_after_mask"
  | "ecoregion_share"
  | "area_floor"
  | "area_band"
  | "leakage_belt"
  | "carbon_project";

export const DONOR_EXCLUSION_CATEGORIES: readonly DonorExclusionCategory[] = [
  "empty_after_mask",
  "ecoregion_share",
  "area_floor",
  "area_band",
  "leakage_belt",
  "carbon_project",
];

/**
 * One rung of the ADR-011 search-region ladder, as climbed for one case.
 * Mirrors `groundtruth.platform.units.rules.RungRecord`. Numeric fields are
 * nullable because a rung the ladder never reached has no counts to report.
 */
export interface DonorLadderRung {
  rung: number;
  description: string;
  countries: string[];
  districtsScreened: number | null;
  eligibleCandidates: number | null;
  admittedDonors: number | null;
  exclusionsByCategory: Partial<Record<DonorExclusionCategory, number>> | null;
  satisfiedStoppingRule: boolean | null;
}

/**
 * ADR-011 donor-candidate-generation summary for one case.
 *
 * There is currently no HTTP endpoint serving this: `EarthEngineUnitConstruction`
 * (`platform/units/generator.py`) raises `DataUnavailableError` on every call, so
 * no candidate count has ever been measured for any case (see the ADR-011
 * implementation commit). Every measurement field is therefore nullable, and a
 * `null` must render as "Not measured" — never as zero, and never as though a
 * ladder climb happened when it did not.
 */
export interface DonorCandidateSummary {
  caseId: string;
  caseName: string;
  /** The treated unit's eligible area after the ADR-011 mask, in km². */
  treatedEligibleAreaKm2: number | null;
  /** Which ladder rung was used, or null if the ladder has not been climbed. */
  rungUsed: number | null;
  rungs: DonorLadderRung[];
  /** Eligible candidate count at the rung used. */
  candidateCount: number | null;
  admittedDonorCount: number | null;
  exclusionsByCategory: Partial<Record<DonorExclusionCategory, number>> | null;
  resultState: ResultState;
}
