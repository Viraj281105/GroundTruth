import { formatValue } from './format';
import type { ReadinessBody } from './types';

export type CriterionState = 'met' | 'not_met' | 'unavailable';
export interface ReadinessItem {
  id: string;
  name: string;
  state: CriterionState;
  stateLabel: string;
  observed: string;
  required: string;
  evidenceNeeded: string;
}

const LABEL: Record<CriterionState, string> = { met: 'Met', not_met: 'Not met', unavailable: 'Unavailable' };

type CriterionLike = Omit<ReadinessBody['criteria'][number], 'required' | 'observed_value'> & { required?: unknown; observed_value?: unknown };

export function readinessItems(r: { criteria: readonly CriterionLike[]; attribution_ready?: boolean }): ReadinessItem[] {
  return (r.criteria ?? []).map((c) => ({
    id: c.id,
    name: c.name,
    state: c.status,
    stateLabel: LABEL[c.status] ?? c.status,
    observed: formatValue(c.observed_value),
    required: formatValue(c.required),
    evidenceNeeded: c.evidence_needed ?? '',
  }));
}
