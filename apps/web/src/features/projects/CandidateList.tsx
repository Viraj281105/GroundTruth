import React from 'react';
import Link from 'next/link';
import { Button, Chip } from '../../components/ds';
import { candidateStatusCopy, isPromoted, type ClaimCandidate, type ClaimKindView, type ProjectClaimView } from './claims.model';
import docStyles from './documents.module.css';
import styles from './claims.module.css';

export const candidateKey = (c: Pick<ClaimCandidate, 'start' | 'end'>) => `${c.start ?? ''}-${c.end ?? ''}`;

export interface CandidateListProps {
  documentId: string;
  candidates: readonly ClaimCandidate[];
  /** Claims already in the project; null when they could not be loaded (then nothing can be added from here). */
  claims: readonly ProjectClaimView[] | null;
  kinds: readonly ClaimKindView[];
  canEdit: boolean;
  blockedReason: string | null;
  /** Keys (start-end) of statements added during this visit. */
  justAdded?: readonly string[];
  verificationHref: string;
  onReview?: (c: ClaimCandidate) => void;
}

/** Statements found in a document. They are text matches, never findings: each can be reviewed and added as a claim. */
export function CandidateList({ documentId, candidates, claims, kinds, canEdit, blockedReason, justAdded = [], verificationHref, onReview }: CandidateListProps) {
  const label = (k: string) => kinds.find((x) => x.kind === k)?.label ?? k;
  return (
    <>
      {!canEdit && (
        <p className={docStyles.muted} data-claim-blocked>
          {blockedReason ?? 'You cannot add claims to this project.'}
        </p>
      )}
      {canEdit && claims === null && <p className={docStyles.muted}>The project’s claims could not be loaded, so statements cannot be added from here right now. Reload the page to try again.</p>}
      <ul className={docStyles.candidates}>
        {candidates.map((c, i) => {
          const s = candidateStatusCopy(c.status);
          const added = justAdded.includes(candidateKey(c));
          const already = !added && claims !== null && isPromoted(documentId, c, claims);
          const hasSpan = typeof c.start === 'number' && typeof c.end === 'number';
          const figure = [c.value !== null && c.value !== undefined ? `${c.value}${c.unit ? ` ${c.unit}` : ''}` : null, c.period].filter(Boolean).join(' · ');
          return (
            <li key={`${c.start ?? i}-${i}`} data-candidate-status={c.status ?? 'extracted'}>
              <div className={styles.chipRow}>
                <strong>{label(c.kind)}</strong>
                <Chip tone={s.tone}>{s.label}</Chip>
                <Chip tone="caution">Not verified</Chip>
              </div>
              {figure && <p className={styles.candidateMeta}>{figure}</p>}
              {c.quote && <p className={docStyles.quote}>&ldquo;{c.quote}&rdquo;</p>}
              {c.reason && <p className={styles.candidateMeta}>{c.reason}</p>}
              {c.evidence_gap && <p className={styles.candidateMeta}>What is missing: {c.evidence_gap}</p>}
              <div className={styles.candidateAction}>
                {added ? (
                  <>
                    <Chip tone="accent">Added to claims</Chip>
                    <Link href={verificationHref} className={styles.link}>
                      See it on the Verification page
                    </Link>
                  </>
                ) : already ? (
                  <>
                    <Chip tone="neutral">Already a claim</Chip>
                    <Link href={verificationHref} className={styles.link}>
                      See it on the Verification page
                    </Link>
                  </>
                ) : (
                  canEdit &&
                  claims !== null &&
                  hasSpan && (
                    <Button size="sm" variant="secondary" onClick={() => onReview?.(c)}>
                      Review and add as claim
                    </Button>
                  )
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}
