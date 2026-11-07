'use client';

import React from 'react';
import { EmptyState, Skeleton } from '../../../components/ds';
import { LinkButton } from '../../../components/ds';
import type { CaseEvidenceState } from './useCaseEvidence';
import { COPY } from './copy';
import styles from './evidence.module.css';

type Ready = Extract<CaseEvidenceState, { status: 'ready' }>;

/** Renders loading, backend-error and no-run states; children get a ready state only. */
export function CaseDataGate({
  state,
  caseId,
  children,
}: {
  state: CaseEvidenceState;
  caseId: string;
  children: (ready: Ready) => React.ReactNode;
}) {
  if (state.status === 'loading') {
    return (
      <div className={styles.stack} aria-busy="true" aria-live="polite">
        <Skeleton height="2rem" width="50%" />
        <Skeleton height="16rem" />
      </div>
    );
  }
  if (state.status === 'error') {
    const f = state.failure;
    return (
      <div role="alert" className={styles.errorBox}>
        <h2 className={styles.errorTitle}>{COPY.errorTitle}</h2>
        <p>{f.message}</p>
        {f.remediation && <p>{f.remediation}</p>}
        {f.code && <p className={styles.code}>{f.code}</p>}
      </div>
    );
  }
  if (state.status === 'no-run') {
    return (
      <EmptyState
        title={COPY.noRunTitle}
        body={COPY.noRunBody}
        action={<LinkButton href={`/cases/${encodeURIComponent(caseId)}/run`}>{COPY.noRunAction}</LinkButton>}
      />
    );
  }
  return <>{children(state)}</>;
}
