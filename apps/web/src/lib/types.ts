/**
 * Types mirroring the GroundTruth API schemas.
 *
 * Kept in sync with `src/groundtruth/api/schemas.py` and
 * `src/groundtruth/core/evidence.py`. Regenerate from /openapi.json once the
 * frontend build is wired up.
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
