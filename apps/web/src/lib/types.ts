/**
 * Types for the GroundTruth API, and the UI helpers built on them.
 *
 * Every backend shape here is GENERATED from the API's OpenAPI schema, never
 * hand-written (issue #17, coordination point C5). The names below are aliases
 * of `./generated/schema.d.ts`, kept so existing imports do not change. After
 * changing an API schema or route, regenerate with `make api-types`; CI fails
 * when the generated files are stale.
 *
 * What remains hand-written in this file is UI vocabulary and helpers, plus the
 * ADR-011 donor types further down, which no endpoint serves yet.
 */

import type { components } from "./generated/schema";

type Schemas = components["schemas"];

/**
 * How an interval should be read. These are not interchangeable.
 *
 * UI vocabulary only: the backend contract types `Confidence.kind` as a free
 * string and documents these four values, so the generated `Confidence.kind` is
 * `string`, not this union.
 */
export type ConfidenceKind =
  | "permutation"
  | "bootstrap"
  | "analytic"
  | "sensitivity-envelope";

/** An interval with its interpretation. `kind` is a string; see `ConfidenceKind`. */
export type Confidence = Schemas["Confidence"];

/** Where a value came from and how it was produced. Never omit this in the UI. */
export type Provenance = Schemas["Provenance"];

export type Evidence = Schemas["Evidence"];

/** Screening outcomes. None of these is a finding of fraud. */
export type VerdictLabel = Schemas["VerdictLabel"];

/** The screening conclusion. Its caveats are always rendered, never collapsed. */
export type VerificationVerdict = Schemas["VerificationVerdict"];

export type EvidenceBundle = Schemas["EvidenceBundle"];

/** A case as listed. `status` is "scaffolded" | "data-wired" | "analysed". */
export type CaseSummary = Schemas["CaseSummary"];

/** A case in full. `known_reference` is third-party, never an input to the estimate. */
export type CaseDetail = Schemas["CaseDetail"];

export type VerificationRequest = Schemas["VerificationRequest"];

export type HealthResponse = Schemas["HealthResponse"];

/**
 * The result of `POST /cases/{id}/verify`. `data_mode` drives the banner.
 *
 * The identity fields (`run_id`, `spec_hash`, `engine_version`,
 * `contract_version`, `duration_ms`) are always present on a real response.
 */
export type VerificationResponse = Schemas["VerificationResponse"];

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
