import { Evidence } from './types';
import { CheckTone, NOT_MEASURED, findEvidence } from './evidence';

/**
 * Shared display model for evidence diagnostics panels. Each group is one
 * check (fit gate, placebo, leave-one-out, ...) with a status in words, a
 * plain-language reading and the evidence rows behind it.
 */

export interface DiagnosticRow {
  /** Evidence id the row is read from; opens its provenance. */
  evidenceId: string;
  label: string;
  /** Always carries a unit or an explicit dimension, never a bare number. */
  display: string;
  /** Secondary line: threshold, qualifier or scope of the value. */
  detail?: string;
  item?: Evidence;
}

export interface DiagnosticGroup {
  id: string;
  title: string;
  /** One-sentence plain-language reading of the group. */
  summary: string;
  status: string;
  tone: CheckTone;
  rows: DiagnosticRow[];
}

export function row(
  items: Evidence[],
  evidenceId: string,
  label: string,
  display: (item: Evidence) => string,
  detail?: (item: Evidence) => string | undefined,
): DiagnosticRow {
  const item = findEvidence(items, evidenceId);
  return {
    evidenceId,
    label,
    display: item ? display(item) : NOT_MEASURED,
    detail: item && detail ? detail(item) : undefined,
    item,
  };
}

