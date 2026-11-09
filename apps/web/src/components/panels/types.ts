import type { components } from '../../lib/generated/schema';

/** Panel prop types are derived from the generated API schemas; never hand-written. */
type S = components['schemas'];
export type AssessmentView = S['AssessmentView'];
export type DimensionView = S['DimensionView'];
export type RecommendationView = S['RecommendationView'];
export type ConclusionView = S['ConclusionView'];
export type AttributionView = S['AttributionView'];
export type ReadinessView = S['ReadinessView'];
export type ReadinessBody = S['ReadinessBody'];
export type ObservationsView = S['ObservationsView'];
export type ClimateView = S['ClimateView'];
export type EvidenceInventoryView = S['EvidenceInventoryView'];
export type VerificationView = S['VerificationView'];
export type PortfolioView = S['PortfolioView'];
export type PortfolioRow = S['PortfolioRow'];
export type ActivityItem = S['ActivityItem'];
export type AccessLevel = S['AssessmentView']['access_level'];

/** Shared prop shape: a payload, or the reason there is none yet. */
export interface PanelProps<T> {
  data?: T | null;
  loading?: boolean;
}

export interface UnavailablePayload {
  status: 'unavailable';
  reason?: string | null;
}

/** True when a payload declares itself unavailable (observations, climate, evidence inventory). */
export function isUnavailable(x: unknown): x is UnavailablePayload {
  return typeof x === 'object' && x !== null && (x as { status?: unknown }).status === 'unavailable';
}
