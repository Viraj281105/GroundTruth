import type { components } from '../../lib/generated/schema';

/** Types come from the generated API schema; nothing here is hand-written API shape. */
export type RegistrySource = components['schemas']['EvidenceSourceResponse'];
export type Registry = components['schemas']['EvidenceRegistryResponse'];

export type ChipTone = 'neutral' | 'accent' | 'caution' | 'danger' | 'sim';
export interface ClassChip {
  key: string;
  label: string;
  tone: ChipTone;
}

const INGESTION_LABELS: Record<string, string> = {
  automated_operational: 'Automated ingestion (operational)',
  manual_staging: 'Manual staging only',
  curated_vector: 'Curated reference data',
  accessible_unvalidated: 'Reachable, not validated',
  scaffolded: 'Scaffolded: no ingestion yet',
  quarantined: 'Quarantined',
  synthetic_simulated: 'Simulated (synthetic)',
};

const VALIDATION_LABELS: Record<string, string> = {
  validated: 'Validated',
  unvalidated: 'Not validated',
  failed: 'Validation failed',
  not_applicable: 'Validation not applicable',
};

const humanize = (v: string): string => {
  const s = v.replace(/_/g, ' ').trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
};

export const ingestionLabel = (mode: string | null | undefined): string => (mode ? (INGESTION_LABELS[mode] ?? humanize(mode)) : 'Unknown');
export const validationLabel = (v: string | null | undefined): string => (v ? (VALIDATION_LABELS[v] ?? humanize(v)) : 'Unknown');

/**
 * The truthful classification chips for one source. "Operational" appears ONLY when the API says
 * `is_operational_integration` is true; blocked sources always say so, with the reason shown on the card.
 */
export function classificationChips(s: RegistrySource): ClassChip[] {
  const chips: ClassChip[] = [];
  if (s.is_operational_integration) chips.push({ key: 'operational', label: 'Operational integration', tone: 'accent' });
  const mode = s.ingestion_mode;
  chips.push({
    key: 'mode',
    label: ingestionLabel(mode),
    tone: mode === 'synthetic_simulated' ? 'sim' : mode === 'quarantined' ? 'danger' : mode === 'automated_operational' ? 'accent' : 'neutral',
  });
  chips.push({
    key: 'validation',
    label: validationLabel(s.validation_status),
    tone: s.validation_status === 'validated' ? 'accent' : s.validation_status === 'failed' ? 'danger' : 'caution',
  });
  chips.push(
    s.blocked_for_production_analysis === false
      ? { key: 'production', label: 'Usable for production analysis', tone: 'accent' }
      : { key: 'production', label: 'Blocked for production analysis', tone: 'caution' },
  );
  return chips;
}

export const shortHash = (h: string | null | undefined): string | null => (typeof h === 'string' && h.length > 0 ? `${h.slice(0, 16)}…` : null);

/** Completeness exactly as measured, or null (never a default like 0 or 100). */
export function completenessOf(s: Pick<RegistrySource, 'completeness_percentage'>): number | null {
  const v = s.completeness_percentage;
  return typeof v === 'number' && Number.isFinite(v) ? Math.min(100, Math.max(0, v)) : null;
}

export function qualityText(s: Pick<RegistrySource, 'quality_measured' | 'data_quality_score' | 'quality_note'>): string {
  if (s.quality_measured && typeof s.data_quality_score === 'number') return `${s.data_quality_score} (measured)`;
  return s.quality_note?.trim() ? `Not measured. ${s.quality_note}` : 'Not measured';
}

export function retrievalText(s: Pick<RegistrySource, 'retrieval_status' | 'retrieval_timestamp' | 'retrieval_provenance'>): string {
  const status = humanize(s.retrieval_status ?? 'not_retrieved');
  const when = s.retrieval_timestamp ? ` · ${s.retrieval_timestamp}` : '';
  const prov = s.retrieval_provenance ? ` · ${s.retrieval_provenance}` : '';
  return `${status}${when}${prov}`;
}

export function coverageText(s: Pick<RegistrySource, 'temporal_coverage_start' | 'temporal_coverage_end'>): string {
  const a = s.temporal_coverage_start || '';
  const b = s.temporal_coverage_end || '';
  return a || b ? `${a || '?'} to ${b || '?'}` : 'Not stated';
}

export const FILTERS = ['all', 'validated', 'integrated', 'accessible', 'discovered', 'quarantined'] as const;
export type Filter = (typeof FILTERS)[number];

export function lifecycleCounts(sources: readonly RegistrySource[]): Record<Filter, number> {
  const out: Record<Filter, number> = { all: sources.length, validated: 0, integrated: 0, accessible: 0, discovered: 0, quarantined: 0 };
  for (const s of sources) {
    if (s.lifecycle !== 'all' && s.lifecycle in out) out[s.lifecycle as Filter] += 1;
  }
  return out;
}

export function filterSources(sources: readonly RegistrySource[], filter: Filter, query: string): RegistrySource[] {
  const q = query.trim().toLowerCase();
  return sources.filter((s) => {
    if (filter !== 'all' && s.lifecycle !== filter) return false;
    if (!q) return true;
    return [s.title, s.provider, s.source_id, s.modality].some((f) => typeof f === 'string' && f.toLowerCase().includes(q));
  });
}

export interface ProjectDocsRow {
  id: string;
  slug: string;
  name: string;
  /** null when the inventory could not be read: shown as "unknown", never as 0. */
  documentsCount: number | null;
}
