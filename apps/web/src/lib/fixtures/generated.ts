import { VerificationResponse } from '../types';
import completedJson from './generated/kariba-redd.completed.json';
import refusedAlignmentJson from './generated/kariba-redd.refused-alignment.json';

/**
 * Engine-generated SIMULATED fixtures.
 *
 * The JSON beside this file is written by `apps/web/scripts/generate_fixtures.py`,
 * which runs the real engine on the synthetic fixture provider. Nothing here is
 * hand-typed: regenerate after any engine change rather than editing the JSON.
 *
 * Sections under `not_served_by_api` are intermediate engine values the API
 * does not return yet (counterfactual path, per-candidate donor table, placebo
 * distribution, refusal detail). UI code that reads them must keep working
 * when they are absent from a real response.
 */

export interface GeneratedMeta {
  marker: string;
  scenario: string;
  description: string;
  case_id: string;
  engine_version: string;
  contract_version: string;
  spec_hash: string;
  seed: number;
  true_effect_injected: number;
}

export interface GeneratedDonorCandidate {
  unit_id: string;
  admitted: boolean;
  distance: number;
  exclusion_reason: string | null;
}

export interface GeneratedCompletedFixture {
  _generated: GeneratedMeta;
  verification: VerificationResponse;
  not_served_by_api: {
    counterfactual_path: {
      periods: number[];
      treatment_boundary_period: number;
      observed: number[];
      synthetic: number[];
    };
    donor_pool: GeneratedDonorCandidate[];
    placebo_distribution: {
      statistic: string;
      observed_statistic: number;
      placebo_statistics: number[];
    };
  };
}

/** The HTTP error body `POST /cases/{id}/verify` returns for a refusal. */
export interface RefusalErrorBody {
  detail: {
    code: string;
    message: string;
    stage: string;
    is_refusal: boolean;
    remediation: string | null;
    run_id: string;
  };
}

export interface AlignmentRefusalDetail {
  window: { pre_start: number; pre_end: number; post_start: number; post_end: number };
  n_units_misaligned: number;
  units: { unit_id: string; missing_periods: number[]; non_finite_periods: number[] }[];
}

export interface GeneratedRefusalFixture {
  _generated: GeneratedMeta;
  http_status: number;
  error_body: RefusalErrorBody;
  not_served_by_api: { error_detail: AlignmentRefusalDetail };
}

/**
 * Refuse to load anything that is not unmistakably simulated (R7). The JSON
 * import is untyped at the boundary, so this is the one place it is checked.
 */
function assertSimulated(meta: GeneratedMeta, dataMode?: string): void {
  if (!meta.marker.startsWith('SIMULATED DATA')) {
    throw new Error(`Generated fixture ${meta.scenario} is missing its SIMULATED DATA marker.`);
  }
  if (dataMode !== undefined && dataMode !== 'simulated') {
    throw new Error(`Generated fixture ${meta.scenario} declares data_mode=${dataMode}.`);
  }
}

function loadCompleted(raw: unknown): GeneratedCompletedFixture {
  const fixture = raw as GeneratedCompletedFixture;
  assertSimulated(fixture._generated, fixture.verification.data_mode);
  return fixture;
}

function loadRefusal(raw: unknown): GeneratedRefusalFixture {
  const fixture = raw as GeneratedRefusalFixture;
  assertSimulated(fixture._generated);
  return fixture;
}

export const KARIBA_COMPLETED: GeneratedCompletedFixture = loadCompleted(completedJson);
export const KARIBA_REFUSED_ALIGNMENT: GeneratedRefusalFixture = loadRefusal(refusedAlignmentJson);
