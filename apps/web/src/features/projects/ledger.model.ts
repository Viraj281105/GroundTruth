import type { ChipTone } from '../../components/ds/Chip';

/** Ledger states exactly as the API's verification returns them. Nothing here is computed by the client. */
export type LedgerStatus = 'empty' | 'verified' | 'failed' | 'legacy_unverifiable';

export interface LedgerStatusText {
  label: string;
  tone: ChipTone;
  /** One plain sentence for a non-technical reader. */
  explain: string;
}

/**
 * Words for a ledger status. "Verified" is only ever shown for the API's `verified`; an empty ledger is
 * described as not sealed yet, never as sealed.
 */
export function ledgerStatusText(status: LedgerStatus): LedgerStatusText {
  switch (status) {
    case 'verified':
      return {
        label: 'Ledger verified',
        tone: 'accent',
        explain: 'Every audit record was recomputed from its stored content and the chain between them is intact.',
      };
    case 'failed':
      return {
        label: 'Integrity check failed',
        tone: 'danger',
        explain: 'A record was changed, removed or reordered after it was written. Do not rely on this ledger until it is investigated.',
      };
    case 'legacy_unverifiable':
      return {
        label: 'Legacy records, not verifiable',
        tone: 'caution',
        explain: 'These records were written before tamper detection existed, so they cannot be checked.',
      };
    default:
      return {
        label: 'Nothing sealed yet',
        tone: 'neutral',
        explain: 'No report has been generated for this project, so there is nothing to verify.',
      };
  }
}

/** A hash for display: the `sha256:` prefix is dropped and the middle elided. Null becomes an em dash. */
export function shortHash(hash: string | null | undefined, keep = 12): string {
  if (!hash) return '—';
  const bare = hash.replace(/^sha256:/, '');
  return bare.length <= keep * 2 + 1 ? bare : `${bare.slice(0, keep)}…${bare.slice(-keep)}`;
}

/** An ISO timestamp as `YYYY-MM-DD HH:MM UTC`; anything unparsable is returned unchanged. */
export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Plain words for a ledger record kind. Unknown kinds are shown as they are, never hidden. */
export function recordKindLabel(kind: string): string {
  switch (kind) {
    case 'report.sealed':
      return 'Report sealed';
    case 'observation.ingested':
      return 'Satellite data stored';
    case 'assessment':
      return 'Assessment recorded';
    default:
      return kind;
  }
}

/**
 * The sealing record the "check a downloaded report" form acts on: the one the user picked while
 * it still exists, otherwise the newest. `records` is oldest first.
 */
export function selectedSealingRecord(chosen: string | null, records: readonly string[]): string {
  if (chosen && records.includes(chosen)) return chosen;
  return records[records.length - 1] ?? '';
}
